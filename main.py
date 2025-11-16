import os
import re
import requests
import uuid
import pytesseract
import google.generativeai as genai
import pandas as pd
import sqlite3
from pdf2image import convert_from_path
from PIL import Image
import easyocr
import json
from dateutil import parser

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
model = genai.GenerativeModel("gemini-2.5-flash")

def extract_file_links(drive_folder_url):
    if "folders" not in drive_folder_url:
        raise ValueError("Not a valid Google Drive folder link")
    folder_id = drive_folder_url.split("/")[-1]
    view_url = f"https://drive.google.com/embeddedfolderview?id={folder_id}#grid"
    html = requests.get(view_url).text
    file_ids = re.findall(r'data-id="([a-zA-Z0-9_-]+)"', html)
    if not file_ids:
        file_ids = re.findall(r'href="https://drive\.google\.com/file/d/([a-zA-Z0-9_-]+)', html)
    if not file_ids:
        file_ids = re.findall(r'"([a-zA-Z0-9_-]{20,})"', html)
    print(f"Found {len(file_ids)} files")
    return [f"https://drive.google.com/uc?export=download&id={fid}" for fid in file_ids]

def download_file(url, out_folder="invoices"):
    os.makedirs(out_folder, exist_ok=True)
    match = re.search(r"id=([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError("Could not extract file ID from URL: " + url)
    file_id = match.group(1)
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    r = requests.get(download_url)
    file_path = os.path.join(out_folder, f"{file_id}.pdf")
    with open(file_path, "wb") as f:
        f.write(r.content)
    return file_path

reader = easyocr.Reader(["en"])

def run_ocr(path):
    try:
        text = ""
        if path.endswith(".pdf"):
            pages = convert_from_path(path)
            for p in pages:
                text += pytesseract.image_to_string(p)
        else:
            img = Image.open(path)
            text += pytesseract.image_to_string(img)
        if len(text.strip()) < 20:
            result = reader.readtext(path, detail=0)
            text = " ".join(result)
        return text
    except Exception as e:
        print("OCR failed:", e)
        return ""

def extract_with_gemini(ocr_text):
    prompt = f"""
    Extract the following invoice text into structured JSON.

    STRICT RULES:
    - Only output VALID JSON.
    - No markdown, no comments.
    - Must be JSON object.
    - Include "line_items" as array.

    Text:
    {ocr_text}
    """
    response = model.generate_content(prompt)
    output = response.text.strip()
    if output.startswith("```"):
        output = output.split("```")[1]
        output = output.replace("json", "").strip()
    return output

def safe_extract_json(ocr_text):
    try:
        out = extract_with_gemini(ocr_text)
        return json.loads(out)
    except:
        print("LLM failed. Retrying…")
        try:
            out = extract_with_gemini(ocr_text)
            return json.loads(out)
        except Exception as e:
            print("LLM extraction failed completely:", e)
            return {}

def clean_fields(data):
    for key in ["invoice_date", "due_date"]:
        try:
            data[key] = str(parser.parse(data[key]).date())
        except:
            data[key] = None
    for key in ["subtotal", "tax", "total"]:
        try:
            data[key] = float(str(data[key]).replace(",", ""))
        except:
            data[key] = 0.0
    return data

def normalize(json_data):
    if isinstance(json_data, list):
        json_data = json_data[0] if json_data else {}
    json_data = clean_fields(json_data)
    invoice = {
        "invoice_number": json_data.get("invoice_number", ""),
        "invoice_date": json_data.get("invoice_date", ""),
        "due_date": json_data.get("due_date", ""),
        "vendor_name": json_data.get("vendor_name", ""),
        "vendor_address": json_data.get("vendor_address", ""),
        "customer_name": json_data.get("customer_name", ""),
        "customer_address": json_data.get("customer_address", ""),
        "subtotal": json_data.get("subtotal", 0),
        "tax": json_data.get("tax", 0),
        "total": json_data.get("total", 0),
        "currency": json_data.get("currency", ""),
        "confidence": min(0.99, len(str(json_data)) / 5000)
    }
    df_inv = pd.DataFrame([invoice])
    items = json_data.get("line_items", [])
    for item in items:
        item["invoice_number"] = invoice["invoice_number"]
    df_items = pd.DataFrame(items) if items else pd.DataFrame(columns=["invoice_number"])
    return df_inv, df_items

def init_db():
    conn = sqlite3.connect("invoices.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            invoice_number TEXT PRIMARY KEY,
            invoice_date TEXT,
            due_date TEXT,
            vendor_name TEXT,
            vendor_address TEXT,
            customer_name TEXT,
            customer_address TEXT,
            subtotal REAL,
            tax REAL,
            total REAL,
            currency TEXT,
            confidence REAL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS line_items (
            invoice_number TEXT,
            description TEXT,
            quantity REAL,
            unit_price REAL,
            amount REAL
        )
    """)
    conn.commit()
    conn.close()

def save_to_db(df_inv, df_items):
    conn = sqlite3.connect("invoices.db")
    df_inv.to_sql("invoices", conn, if_exists="append", index=False)
    allowed_cols = ["invoice_number", "description", "quantity", "unit_price", "amount"]
    for col in df_items.columns:
        if col not in allowed_cols:
            df_items = df_items.drop(columns=[col], errors="ignore")
    for col in allowed_cols:
        if col not in df_items.columns:
            df_items[col] = None
    df_items = df_items[allowed_cols]
    df_items.to_sql("line_items", conn, if_exists="append", index=False)
    conn.close()

def evaluate_extraction(gt_folder="ground_truth", pred_folder="output_json"):
    scores = []
    for fname in os.listdir(gt_folder):
        if not fname.endswith(".json"):
            continue
        gt = json.load(open(f"{gt_folder}/{fname}"))
        pred_path = f"{pred_folder}/{fname.replace('.json', '')}_predicted.json"
        if not os.path.exists(pred_path):
            continue
        pred = json.load(open(pred_path))
        fields = ["invoice_number", "invoice_date", "vendor_name", "total"]
        correct = 0
        for f in fields:
            if str(gt.get(f)).strip() == str(pred.get(f)).strip():
                correct += 1
        accuracy = correct / len(fields)
        scores.append(accuracy)
    return sum(scores) / len(scores) if scores else 0

def process_folder(drive_link):
    init_db()
    print("Fetching files from Google Drive...")
    files = extract_file_links(drive_link)
    for f in files:
        print("\nProcessing:", f)
        path = download_file(f)
        text = run_ocr(path)
        data = safe_extract_json(text)
        df_inv, df_items = normalize(data)
        save_to_db(df_inv, df_items)
    print("\nAll invoices processed successfully!")

if __name__ == "__main__":
    process_folder("https://drive.google.com/drive/folders/1smMAVwDrBAzt01ynQ0J8QJjG37fGz92P")
