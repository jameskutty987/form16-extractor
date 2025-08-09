import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

# --- Page Configuration and UI Styling ---
st.set_page_config(page_title="Form 16A TDS Extractor", layout="centered")

st.markdown("""
    <style>
    body, .stApp {
        background-color: #0f0f0f;
        color: #00ff88;
        font-family: 'Segoe UI', sans-serif;
    }
    .stButton>button, .stDownloadButton>button {
        background-color: #00ff88;
        color: black;
        font-weight: bold;
        border-radius: 8px;
    }
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

st.title("📄 Form 16A TDS Extractor (Coordinate-Based)")
st.warning("This version uses hardcoded coordinates for extraction, tailored to the specific format of your PDF.")


def extract_data_with_coordinates(pdf_file):
    """
    Final extractor using coordinate-based logic as requested.
    It finds each certificate and then uses fixed coordinates and simple regex
    to pull data from all pages of that certificate.
    """
    all_records = []
    
    try:
        with pdfplumber.open(pdf_file) as pdf:
            # Step 1: Robustly find the start page of each Form 16A certificate.
            start_page_indices = [i for i, page in enumerate(pdf.pages) if "Certificate under section 203" in (page.extract_text() or "") and "FORM NO. 16A" in (page.extract_text() or "")]

            if not start_page_indices:
                st.error("Error: No valid Form 16A start pages were found.")
                return pd.DataFrame()

            # Step 2: Process each certificate as a "block" of pages.
            for i, start_index in enumerate(start_page_indices):
                end_index = start_page_indices[i + 1] if i + 1 < len(start_page_indices) else len(pdf.pages)
                
                # --- Section A: Extract Header Info from the First Page using Coordinate Logic ---
                header_page = pdf.pages[start_index]
                header_words = header_page.extract_words(x_tolerance=2)
                header_text = header_page.extract_text(x_tolerance=2)
                
                current_pan = "Unknown PAN"
                current_deductee = "Unknown Deductee"
                current_deductor = "Unknown Deductor"
                
                # Using the exact coordinate logic from your first script for PAN
                for w in header_words:
                    if 280 < w["top"] < 295 and 350 < w["x0"] < 500 and re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", w["text"]):
                        current_pan = w["text"]
                        break
                
                # Using a coordinate band for Deductee Name
                name_words = [w["text"] for w in header_words if 220 < w["top"] < 240 and 20 < w["x0"] < 300]
                if name_words:
                    current_deductee = " ".join(name_words)

                # Using simple regex for other header info
                deductor_match = re.search(r"Name and address of the deductor\n(.*?)\n", header_text)
                if deductor_match:
                    current_deductor = deductor_match.group(1).strip()
                
                quarter_match = re.search(r"Quarter\s*\n\s*(Q[1-4]|0[1-4])", header_text)
                quarter = f"Q{quarter_match.group(1).lstrip('0')}" if quarter_match else "N/A"

                # --- Section B: Find all transactions across ALL pages of this certificate ---
                all_payments = []
                all_challans = []

                for page_num in range(start_index, end_index):
                    page_text = pdf.pages[page_num].extract_text(x_tolerance=2) or ""
                    
                    # Using the simple regex from your first script to find numbers
                    # Pattern: A number with .00, then 194(any letter), then a date
                    payments_on_page = re.findall(r"(\d+\.\d{2})\s+194\w+\s+(\d{2}-\d{2}-\d{4})", page_text)
                    all_payments.extend(payments_on_page)
                    
                    # Pattern: A number with .00, then a 7-digit BSR code, then a date
                    challans_on_page = re.findall(r"(\d+\.\d{2})\s+\d{7}\s+(\d{2}-\d{2}-\d{4})", page_text)
                    all_challans.extend(challans_on_page)

                # --- Section C: Pair up the collected payments and challans ---
                # This assumes the number of payments matches the number of challans for the certificate.
                num_transactions = min(len(all_payments), len(all_challans))
                for j in range(num_transactions):
                    taxable_val, pay_date = all_payments[j]
                    tds_val, _ = all_challans[j]
                    
                    try:
                        rate = round((float(tds_val) / float(taxable_val)) * 100, 2) if float(taxable_val) > 0 else 0.0
                    except (ValueError, ZeroDivisionError):
                        rate = 0.0
                    
                    all_records.append({
                        "Quarter": quarter,
                        "Date of Deduction": pay_date,
                        "Deductee Name": current_deductee,
                        "PAN": current_pan,
                        "Taxable Value": float(taxable_val),
                        "Rate (%)": f"{rate:.2f}",
                        "TDS Amount": float(tds_val),
                        "Deductor Name": current_deductor
                    })

    except Exception as e:
        st.error(f"An unexpected error occurred: {e}")
        return pd.DataFrame()
        
    return pd.DataFrame(all_records)


# --- Main Application Flow ---
uploaded_file = st.file_uploader("Upload Merged Form 16A PDF", type="pdf")

if uploaded_file is not None:
    if st.button("▶️ Extract Using Coordinates"):
        with st.spinner("Processing PDF with coordinate-based logic..."):
            extracted_df = extract_data_with_coordinates(uploaded_file)

        if not extracted_df.empty:
            st.success(f"✅ Extraction Complete! Found {len(extracted_df)} records.")
            
            st.dataframe(extracted_df.style.format({
                "Taxable Value": "₹{:,.2f}",
                "TDS Amount": "₹{:,.2f}"
            }))

            @st.cache_data
            def convert_df_to_excel(df):
                buffer = BytesIO()
                df.to_excel(buffer, index=False, sheet_name='TDS_Data')
                return buffer.getvalue()

            excel_data = convert_df_to_excel(extracted_df)

            st.download_button(
                label="📥 Download Excel",
                data=excel_data,
                file_name="Form16A_Coordinate_Extract.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Extraction ran but no transaction data was found. The PDF layout might not match the hardcoded coordinates.")
