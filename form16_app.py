import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="Form 16A TDS Extractor", layout="centered")

# Dark UI Styling
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
    footer {visibility: visible;}
    footer:after {
        content: 'Published by JamesCurator | Final Code Version';
        display: block;
        text-align: center;
        color: gray;
        padding: 10px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📄 Form 16A TDS Data Extractor")
st.info("This enhanced extractor is designed for merged Form 16A PDFs, accurately reading data across multiple pages for each certificate.")

uploaded_file = st.file_uploader("Upload your merged Form 16A PDF", type="pdf")

def extract_form16a_data_final(pdf_file):
    """
    Extracts TDS data from a merged PDF containing multiple Form 16A certificates.
    
    This function dynamically identifies each certificate, handles data spanning
    multiple pages, and correctly associates payment amounts with TDS deposited
    by using table structures and serial numbers.
    """
    all_records = []
    with pdfplumber.open(pdf_file) as pdf:
        # Step 1: Find the start page of each Form 16A certificate
        start_page_indices = []
        for i, page in enumerate(pdf.pages):
            text = page.extract_text(x_tolerance=2) or ""
            # Use a unique combination of text to identify the start of a new certificate
            if "Certificate under section 203" in text and "FORM NO. 16A" in text:
                start_page_indices.append(i)

        if not start_page_indices:
            st.error("Could not find any valid Form 16A start pages. Please check the PDF.")
            return pd.DataFrame()

        # Step 2: Process each certificate as a "block" of pages
        for i, start_index in enumerate(start_page_indices):
            end_index = start_page_indices[i + 1] if i + 1 < len(start_page_indices) else len(pdf.pages)
            
            # --- A. Extract Header Information from the first page of the block ---
            header_page = pdf.pages[start_index]
            header_text = header_page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            
            # Use robust regex anchored to labels
            deductor_name = (re.search(r"Name and address of the deductor\n(.*?)\n", header_text) or re.search(r"Name and address of the deductor\s*(.*?)\s*PAN", header_text)).group(1).strip()
            deductee_name = (re.search(r"Name and address of the deductee\n(.*?)\n", header_text) or re.search(r"Name and address of the deductee\s*(.*?)\s*Assessment Year", header_text)).group(1).strip()
            pan_match = re.search(r"PAN of the deductee\s*\n\s*([A-Z]{5}[0-9]{4}[A-Z])", header_text) or re.search(r"PAN of the deductee\s*([A-Z]{5}[0-9]{4}[A-Z])", header_text)
            pan = pan_match.group(1) if pan_match else "Unknown"
            quarter_match = re.search(r"Quarter\s*\n\s*(Q[1-4]|0[1-4])", header_text)
            quarter = f"Q{quarter_match.group(1).lstrip('0')}" if quarter_match else "Unknown"

            # --- B. Extract Transactional Data from all pages in the block ---
            payments_dict = {}
            challans_dict = {}

            for page_num in range(start_index, end_index):
                page = pdf.pages[page_num]
                tables = page.extract_tables({
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                })

                for table in tables:
                    if not table or not table[0]: continue
                    header_row_text = ' '.join(filter(None, table[0]))

                    # Identify and process "Summary of payment" table
                    if "Amount paid/credited" in header_row_text and "Date of payment/credit" in header_row_text:
                        for row in table[1:]:
                            try:
                                sl_no = row[0].strip()
                                if sl_no and sl_no.isdigit():
                                    payments_dict[sl_no] = {
                                        'amount_paid': float(row[1].replace(',', '')),
                                        'payment_date': row[4]
                                    }
                            except (ValueError, IndexError):
                                continue # Skip malformed rows

                    # Identify and process "Details of tax deducted... through challan" table
                    if "Tax deposited in respect" in header_row_text and "BSR Code" in header_row_text:
                        for row in table[1:]:
                             try:
                                sl_no = row[0].strip()
                                if sl_no and sl_no.isdigit():
                                    # Handle cases where value might be None or empty
                                    tax_val_str = row[1] or "0"
                                    challans_dict[sl_no] = {
                                        'tds_amount': float(tax_val_str.replace(',', ''))
                                    }
                             except (ValueError, IndexError):
                                 continue # Skip malformed rows
            
            # --- C. Merge payment and challan data and create final records ---
            for sl_no, payment_info in payments_dict.items():
                challan_info = challans_dict.get(sl_no, {'tds_amount': 0.0}) # Default to 0 if no matching challan
                
                try:
                    rate = round((challan_info['tds_amount'] / payment_info['amount_paid']) * 100, 2) if payment_info['amount_paid'] > 0 else 0.0
                except ZeroDivisionError:
                    rate = 0.0
                
                all_records.append({
                    "Quarter": quarter,
                    "Date of Deduction": payment_info['payment_date'],
                    "Deductee Name": deductee_name,
                    "PAN": pan,
                    "Taxable Value": payment_info['amount_paid'],
                    "Rate (%)": f"{rate:.2f}",
                    "TDS Amount": challan_info['tds_amount'],
                    "Deductor Name": deductor_name
                })

    return pd.DataFrame(all_records)


# --- Main Application Logic ---
if uploaded_file:
    if st.button("▶️ Extract Data"):
        with st.spinner("Analyzing document structure and extracting data... Please wait."):
            df = extract_form16a_data_final(uploaded_file)

        if df.empty:
            st.error("❌ No valid TDS data was extracted. The PDF might be password-protected or in an unsupported format.")
        else:
            st.success("✅ Extraction Complete! Found {} records.".format(len(df)))
            
            # Ensure consistent column order
            display_columns = ["Quarter", "Date of Deduction", "Deductee Name", "PAN",
                               "Taxable Value", "Rate (%)", "TDS Amount", "Deductor Name"]
            df = df[display_columns]
            
            st.dataframe(df.style.format({
                "Taxable Value": "{:,.2f}",
                "TDS Amount": "{:,.2f}"
            }))

            # --- Download Button ---
            @st.cache_data
            def convert_df_to_excel(dataframe):
                buffer = BytesIO()
                dataframe.to_excel(buffer, index=False, sheet_name='TDS_Extracted_Data')
                return buffer.getvalue()

            excel_bytes = convert_df_to_excel(df)
            st.download_button(
                label="📥 Download as Excel File",
                data=excel_bytes,
                file_name="Form16A_TDS_Extracted.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
