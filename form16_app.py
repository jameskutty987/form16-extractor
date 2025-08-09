import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

# --- 1. Professional UI Configuration ---
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
        padding: 10px 20px;
    }
    .st-emotion-cache-1jicfl2 { /* Targets the file uploader box */
        border-color: #00ff88;
    }
    h1 {
        border-bottom: 2px solid #00ff88;
        padding-bottom: 10px;
    }
    footer {visibility: visible;}
    footer:after {
        content: 'Created by JAMESKUTTY';
        display: block;
        text-align: center;
        color: gray;
        padding-top: 20px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("Form 16A TDS Extractor")

# --- 2. Core Extraction Logic ---
def extract_data_final(pdf_file):
    """
    Final extractor using a hybrid of original logic and robust page handling.
    """
    all_records = []
    
    try:
        with pdfplumber.open(pdf_file) as pdf:
            # Robustly find the start page of each Form 16A certificate
            start_page_indices = [i for i, page in enumerate(pdf.pages) if "Certificate under section 203" in (page.extract_text() or "") and "FORM NO. 16A" in (page.extract_text() or "")]

            if not start_page_indices:
                st.error("Error: Could not find any valid Form 16A certificates in the PDF.")
                return pd.DataFrame()

            for i, start_index in enumerate(start_page_indices):
                end_index = start_page_indices[i + 1] if i + 1 < len(start_page_indices) else len(pdf.pages)
                
                # --- PROCESS PAGE 1 ---
                page1 = pdf.pages[start_index]
                words1 = page1.extract_words(x_tolerance=2)
                text1 = page1.extract_text(x_tolerance=2) or ""

                current_pan = "Unknown"
                current_deductee = "Unknown"
                current_deductor = "Unknown"
                quarter = "Unknown"

                # Your original coordinate logic for PAN
                for w in words1:
                    if 265 < w["top"] < 275 and 455 < w["x0"] < 510 and re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", w["text"]):
                        current_pan = w["text"]
                        break
                
                # Your original coordinate logic for Deductee Name
                name_band = sorted([w for w in words1 if 185 < w["top"] < 195 and 300 < w["x0"] < 540], key=lambda x: x["x0"])
                current_deductee = " ".join([w["text"] for w in name_band]).strip() or "Unknown"

                # Your original logic for Deductor Name
                for line_idx, line in enumerate(text1.splitlines()):
                    if "Name and address of the deductor" in line:
                        for next_line in text1.splitlines()[line_idx + 1:]:
                            if next_line.strip():
                                current_deductor = next_line.strip()
                                break
                        break

                # Your original logic for Quarter
                quarter_match = re.search(r"Summary of tax deducted.*?\nQ([1-4])", text1, re.DOTALL)
                if quarter_match:
                    quarter = f"Q{quarter_match.group(1)}"

                # --- Transaction Extraction (using your original TDS regex) ---
                payments1 = re.findall(r"(\d{2,}\.\d{2})\s+194\w+\s+(\d{2}-\d{2}-\d{4})", text1)
                challans1 = re.findall(r"(\d{2,}\.\d{2})\s+051\d+\s+(\d{2}-\d{2}-\d{4})", text1)
                
                for j in range(min(len(payments1), len(challans1))):
                    taxable_val, pay_date = payments1[j]
                    tds_val, _ = challans1[j]
                    rate = round((float(tds_val) / float(taxable_val)) * 100, 2) if float(taxable_val) > 0 else 0.0
                    all_records.append({
                        "Quarter": quarter, "Date of Deduction": pay_date, "Deductee Name": current_deductee,
                        "PAN": current_pan, "Taxable Value": float(taxable_val), "Rate (%)": f"{rate:.2f}",
                        "TDS Amount": float(tds_val), "Deductor Name": current_deductor
                    })

                # --- PROCESS PAGE 2 (if it exists) using Page 1 Headers ---
                if start_index + 1 < end_index:
                    page2 = pdf.pages[start_index + 1]
                    text2 = page2.extract_text() or ""
                    
                    payments2 = re.findall(r"(\d{2,}\.\d{2})\s+194\w+\s+(\d{2}-\d{2}-\d{4})", text2)
                    challans2 = re.findall(r"(\d{2,}\.\d{2})\s+051\d+\s+(\d{2}-\d{2}-\d{4})", text2)
                    
                    for j in range(min(len(payments2), len(challans2))):
                        taxable_val, pay_date = payments2[j]
                        tds_val, _ = challans2[j]
                        rate = round((float(tds_val) / float(taxable_val)) * 100, 2) if float(taxable_val) > 0 else 0.0
                        all_records.append({
                            "Quarter": quarter, "Date of Deduction": pay_date, "Deductee Name": current_deductee,
                            "PAN": current_pan, "Taxable Value": float(taxable_val), "Rate (%)": f"{rate:.2f}",
                            "TDS Amount": float(tds_val), "Deductor Name": current_deductor
                        })

    except Exception as e:
        st.error(f"An unexpected error occurred during processing: {e}")
        return pd.DataFrame()
        
    return pd.DataFrame(all_records)

# --- 3. Main Application Flow ---
uploaded_file = st.file_uploader("Upload Merged Form 16A PDF File", type="pdf")

if uploaded_file is not None:
    if st.button("Extract Data"):
        with st.spinner("Processing PDF..."):
            extracted_df = extract_data_final(uploaded_file)

        if not extracted_df.empty:
            st.success(f"Extraction Complete! Found {len(extracted_df)} total records.")
            
            st.dataframe(extracted_df.style.format({
                "Taxable Value": "₹{:,.2f}",
                "TDS Amount": "₹{:,.2f}"
            }))

            # Use st.cache_data for efficient download preparation
            @st.cache_data
            def convert_df_to_excel(df):
                buffer = BytesIO()
                df.to_excel(buffer, index=False, sheet_name='TDS_Data')
                return buffer.getvalue()

            excel_data = convert_df_to_excel(extracted_df)

            st.download_button(
                label="Download as Excel File",
                data=excel_data,
                file_name="TDS_Data_Extract.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Extraction complete, but no transaction data was found. Please verify the PDF format.")
