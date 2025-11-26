import os
import glob
import sqlite3
import json
import pandas as pd
import google.generativeai as genai
import pytesseract
import easyocr
from pdf2image import convert_from_path
from PIL import Image
from dateutil import parser

# --- CONFIGURATION ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

reader = easyocr.Reader(["en"])

# --- HELPER: SAFE FLOAT CONVERSION ---
def safe_float(value):
    """
    Safely converts strings like '$1,200.50', 'None', or 'null' to float.
    Returns 0.0 on failure.
    """
    if value is None:
        return 0.0
    try:
        # Convert to string, clean common currency symbols
        s = str(value).replace(",", "").replace("$", "").strip()
        if not s or s.lower() == "none" or s.lower() == "null":
            return 0.0
        return float(s)
    except:
        return 0.0

# --- OCR & EXTRACTION ---
def run_ocr(path):
    print(f"Processing OCR for: {os.path.basename(path)}")
    try:
        text = ""
        if path.lower().endswith(".pdf"):
            try:
                pages = convert_from_path(path) 
                for p in pages:
                    text += pytesseract.image_to_string(p)
            except:
                pass 
        else:
            img = Image.open(path)
            text += pytesseract.image_to_string(img)
            
        if len(text.strip()) < 20:
            result = reader.readtext(path, detail=0)
            text = " ".join(result)
        return text
    except Exception as e:
        # Don't crash here, just log and return empty
        print(f"  > OCR Warning: {e}")
        return ""

def extract_with_gemini(ocr_text):
    prompt = f"""
    Extract invoice data into JSON.
    Fields: invoice_number, invoice_date, due_date, vendor_name, customer_name, subtotal, tax, total, currency.
    Line Items: description, quantity, unit_price, amount.
    
    STRICT JSON OUTPUT ONLY.
    Text: {ocr_text[:3000]}...
    """
    try:
        response = model.generate_content(prompt)
        output = response.text.strip()
        if output.startswith("```"):
            output = output.split("```")[1].replace("json", "").strip()
        return output
    except Exception as e:
        print(f"  > Gemini Warning: {e}")
        return "{}"

def safe_extract_json(ocr_text):
    if not ocr_text.strip(): return {}
    try:
        return json.loads(extract_with_gemini(ocr_text))
    except:
        return {}

def normalize(json_data):
    if isinstance(json_data, list): json_data = json_data[0] if json_data else {}
    
    # 1. Normalize Header using safe_float
    header = {
        "invoice_number": str(json_data.get("invoice_number", "UNKNOWN")),
        "invoice_date": str(json_data.get("invoice_date", "")),
        "due_date": str(json_data.get("due_date", "")),
        "vendor_name": str(json_data.get("vendor_name", "")),
        "customer_name": str(json_data.get("customer_name", "")),
        "subtotal": safe_float(json_data.get("subtotal")),
        "total": safe_float(json_data.get("total")),
        "tax": safe_float(json_data.get("tax")),
        "currency": str(json_data.get("currency", "USD"))
    }
    df_inv = pd.DataFrame([header])
    
    # 2. Normalize Items
    items = json_data.get("line_items", [])
    if items:
        for i in items:
            i["invoice_number"] = header["invoice_number"]
            # Clean item numbers too
            i["quantity"] = safe_float(i.get("quantity"))
            i["unit_price"] = safe_float(i.get("unit_price"))
            i["amount"] = safe_float(i.get("amount"))
            
        df_items = pd.DataFrame(items)
    else:
        df_items = pd.DataFrame()
        
    return df_inv, df_items

# --- DYNAMIC DATABASE SAVING ---
def smart_save_table(df, table_name, conn):
    if df.empty: return

    try:
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        existing_cols = [row[1] for row in cursor.fetchall()]

        if not existing_cols:
            df.to_sql(table_name, conn, if_exists='append', index=False)
            return

        new_cols = [col for col in df.columns if col not in existing_cols]

        for col in new_cols:
            # Add missing columns safely
            try:
                conn.execute(f"ALTER TABLE {table_name} ADD COLUMN \"{col}\" TEXT")
            except:
                pass # Column might have been added by another thread/process
        
        df.to_sql(table_name, conn, if_exists='append', index=False)
        
    except Exception as e:
        print(f"  > DB Save Warning on {table_name}: {e}")

def save_to_db(df_inv, df_items):
    conn = sqlite3.connect("invoices.db")
    smart_save_table(df_inv, "invoices", conn)
    smart_save_table(df_items, "line_items", conn)
    conn.close()
    print("  > Saved to DB.")

# --- MAIN ---
def process_local_folder(folder_path="invoices"):
    search_str = os.path.join(folder_path, "*.pdf")
    files = glob.glob(search_str)
    print(f"Found {len(files)} files in '{folder_path}'")

    for i, path in enumerate(files):
        print(f"\n[{i+1}/{len(files)}] Processing {os.path.basename(path)}...")
        
        # --- GLOBAL ERROR HANDLER ---
        # This ensures that NO error (OCR, PDF, JSON, DB) stops the script.
        try:
            text = run_ocr(path)
            if not text: 
                print("  > Skipping: No text found.")
                continue
                
            data = safe_extract_json(text)
            if not data: 
                print("  > Skipping: JSON extraction failed.")
                continue
                
            df_inv, df_items = normalize(data)
            save_to_db(df_inv, df_items)
            
        except Exception as e:
            print(f"  ! CRITICAL ERROR on this file: {e}")
            print("  ! Skipping and moving to next file...")
            continue

    print("\nDone!")

if __name__ == "__main__":
    process_local_folder("invoices")