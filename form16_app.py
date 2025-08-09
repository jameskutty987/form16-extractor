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

st.title("📄 Form 16A TDS Data Extractor")
st.info("Upload a merged PDF containing one or more Form 16A certificates. The extractor will read all transactions and generate a downloadable Excel file.")

# --- Core Extraction Logic ---
def extract_data_from_pdf(pdf_file):
    """
    Extracts TDS data from a merged PDF of Form 16A certificates.
    This version is stabilized to prevent crashes and correctly parse table data.
    """
    all_final_records = []
    
    try:
        with pdfplumber.open(pdf_file) as pdf:
            # Step 1: Find the start page of each Form 16A certificate
            start_page_indices = [i for i, page in enumerate(pdf.pages) if "Certificate under section 203" in (page.extract_text() or "") and "FORM NO. 16A" in (page.extract_text() or "")]

            if not start_page_indices:
                st.error("Error: No valid Form 16A start pages were found in the document.")
                return pd.DataFrame()

            # Step 2: Process each certificate as a "block" of pages
            for i, start_index in enumerate(start_page_indices):
                end_index = start_page_indices[i + 1] if i + 1 < len(start_page_indices) else len(pdf.pages)
                
                header_page = pdf.pages[start_index]
                header_text = header_page.extract_text(x_tolerance=2, y_tolerance=3) or ""
                
                # --- Section A: Safely extract all header info ONCE per certificate ---
                deductor_match = re.search(r"Name and address of the deductor\n(.*?)\n", header_text)
                deductor_name = deductor_match.group(1).strip() if deductor_match else "Unknown Deductor"
                
                deductee_match = re.search(r"Name and address of the deductee\n(.*?)\n", header_text)
                deductee_name = deductee_match.group(1).strip() if deductee_match else "Unknown Deductee"

                pan_match = re.search(r"PAN of the deductee\s*\n\s*([A-Z]{5}[0-9]{4}[A-Z])", header_text)
                pan = pan_match.group(1).strip() if pan_match else "Unknown PAN"
                
                quarter_match = re.search(r"Quarter\s*\n\s*(Q[1-4]|0[1-4])", header_text)
                quarter = f"Q{quarter_match.group(1).lstrip('0')}" if quarter_match else "N/A"

                # --- Section B: Extract transaction data from all pages in the block ---
                payments = {}
                challans = {}

                for page_num in range(start_index, end_index):
                    page = pdf.pages[page_num]
                    tables = page.extract_tables() # Use simplified, robust default extraction

                    for table in tables:
                        if not table or not table[0]: continue
                        header = ' '.join(filter(None, table[0])).replace('\n', ' ')

                        # Look for payment table
                        if "Amount paid/credited" in header:
                            for row in table[1:]:
                                try:
                                    if row and len(row) > 4 and row[0] and row[0].strip().isdigit():
                                        sl_no = row[0].strip()
                                        payments[sl_no] = {
                                            'amount_paid': float(str(row[1]).replace(',', '')),
                                            'payment_date': str(row[4])
                                        }
                                except (ValueError, TypeError):
                                    continue
                        
                        # Look for challan (TDS) table
                        if "Tax deposited in respect" in header and "BSR Code" in header:
                             for row in table[1:]:
                                 try:
                                    if row and len(row) > 1 and row[0] and row[0].strip().isdigit():
                                        sl_no = row[0].strip()
                                        challans[sl_no] = {
                                            'tds_amount': float(str(row[1]).replace(',', ''))
                                        }
                                 except (ValueError, TypeError):
                                     continue
                
                # --- Section C: Merge and store records for this certificate ---
                for sl_no, payment_data in payments.items():
                    challan_data = challans.get(sl_no, {'tds_amount': 0.0})
                    
                    try:
                        rate = round((challan_data['tds_amount'] / payment_data['amount_paid']) * 100, 2) if payment_data['amount_paid'] else 0.0
                    except ZeroDivisionError:
                        rate = 0.0
                    
                    all_final_records.append({
                        "Quarter": quarter,
                        "Date of Deduction": payment_data['payment_date'],
                        "Deductee Name": deductee_name,
                        "PAN": pan,
                        "Taxable Value": payment_data['amount_paid'],
                        "Rate (%)": f"{rate:.2f}",
                        "TDS Amount": challan_data['tds_amount'],
                        "Deductor Name": deductor_name
                    })

    except Exception as e:
        st.error(f"An unexpected error occurred during PDF processing: {e}")
        return pd.DataFrame()
        
    return pd.DataFrame(all_final_records)


# --- Main Application Flow ---
uploaded_file = st.file_uploader(" ", type="pdf")

if uploaded_file is not None:
    if st.button("▶️ Extract TDS Data"):
        with st.spinner("Analyzing document and extracting all transactions..."):
            extracted_df = extract_data_from_pdf(uploaded_file)

        if not extracted_df.empty:
            st.success(f"✅ Extraction Complete! Found {len(extracted_df)} records.")
            
            # Display formatted DataFrame
            st.dataframe(extracted_df.style.format({
                "Taxable Value": "₹{:,.2f}",
                "TDS Amount": "₹{:,.2f}"
            }))

            # Prepare data for download
            @st.cache_data
            def convert_df_to_excel(df):
                buffer = BytesIO()
                df.to_excel(buffer, index=False, sheet_name='TDS_Extracted_Data')
                return buffer.getvalue()

            excel_data = convert_df_to_excel(extracted_df)

            st.download_button(
                label="📥 Download as Excel File",
                data=excel_data,
                file_name="Form16A_TDS_Extracted.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            # This message will show if the function runs but finds nothing
            st.warning("Extraction ran successfully, but no valid transaction data was found. Please check if the PDF is a standard Form 16A.")
