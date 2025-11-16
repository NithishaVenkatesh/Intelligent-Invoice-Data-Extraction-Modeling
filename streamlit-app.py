import streamlit as st
import sqlite3
import pandas as pd
import json

# ----------------------------------------------------------
# IMPORT FUNCTIONS FROM main.py OR pipeline.py
# ----------------------------------------------------------
import importlib.util
import sys
import os

main_path = os.path.join(os.path.dirname(__file__), "main.py")
spec = importlib.util.spec_from_file_location("main", main_path)
main = importlib.util.module_from_spec(spec)
sys.modules["main"] = main
spec.loader.exec_module(main)

normalize = main.normalize
save_to_db = main.save_to_db

# ----------------------------------------------------------
# Streamlit Page Settings
# ----------------------------------------------------------
st.set_page_config(page_title="Invoice Dashboard", layout="wide")
st.title("📄 Invoice Database Viewer")

# ----------------------------------------------------------
# Database Connection
# ----------------------------------------------------------
def get_connection():
    return sqlite3.connect("invoices.db", check_same_thread=False)

def load_invoices():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM invoices", conn)
    conn.close()
    return df

def load_line_items(invoice_number=None):
    conn = get_connection()
    if invoice_number:
        df = pd.read_sql_query(
            "SELECT * FROM line_items WHERE invoice_number = ?",
            conn, params=[invoice_number]
        )
    else:
        df = pd.read_sql_query("SELECT * FROM line_items", conn)
    conn.close()
    return df

# ==========================================================
# 1️⃣ VIEW ALL INVOICES
# ==========================================================
st.header("📌 All Invoices")

df_inv = load_invoices()

if df_inv.empty:
    st.warning("No invoices found in the database.")
else:
    st.dataframe(df_inv, use_container_width=True)
    st.download_button(
        "Download All Invoices (CSV)",
        df_inv.to_csv(index=False),
        file_name="all_invoices.csv",
    )

st.markdown("---")

# ==========================================================
# 2️⃣ SEARCH BY VENDOR
# ==========================================================
st.header("🔍 Search by Vendor")

vendor_name = st.text_input("Enter vendor name to search")

if vendor_name:
    query = f"%{vendor_name}%"
    conn = get_connection()
    df_vendor = pd.read_sql_query(
        "SELECT * FROM invoices WHERE vendor_name LIKE ?",
        conn,
        params=[query]
    )
    conn.close()

    if df_vendor.empty:
        st.warning("No invoices found for this vendor.")
    else:
        st.dataframe(df_vendor, use_container_width=True)

st.markdown("---")

# ==========================================================
# 3️⃣ FILTER BY DATE RANGE
# ==========================================================
st.header("📅 Filter by Invoice Date Range")

col1, col2 = st.columns(2)
start_date = col1.date_input("Start Date")
end_date = col2.date_input("End Date")

if st.button("Apply Date Filter"):
    conn = get_connection()
    df_date = pd.read_sql_query(
        """
        SELECT * FROM invoices
        WHERE DATE(invoice_date) BETWEEN DATE(?) AND DATE(?)
        """,
        conn,
        params=[str(start_date), str(end_date)]
    )
    conn.close()

    if df_date.empty:
        st.warning("No invoices in this date range.")
    else:
        st.dataframe(df_date, use_container_width=True)

st.markdown("---")

# ==========================================================
# 4️⃣ VIEW LINE ITEMS
# ==========================================================
st.header("📦 Line Items Viewer")

df_lines = load_line_items()

if df_lines.empty:
    st.warning("No line items found.")
else:
    st.dataframe(df_lines, use_container_width=True)

    st.download_button(
        "Download Line Items (CSV)",
        df_lines.to_csv(index=False),
        file_name="line_items.csv",
    )
