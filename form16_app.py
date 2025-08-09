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

st.title("📄 Form 16A TDS Extractor (Original Logic)")
st.info("This extractor uses the original coordinate-based logic to ensure data is correctly associated across pages.")

def extract_data_with_original_logic(pdf_file):
    """
    Final extractor using the user's original coordinate-based logic for Page 1
    and extending it to Page 2, ensuring header data is carried over correctly.
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
                
                # --- PROCESS PAGE 1 ---
                page1 = pdf.pages[start_index]
                words1 = page1.extract_words(x_tolerance=2)
                text1 = page1.extract_text(x_tolerance=2) or ""

                # Initialize variables for header info for this certificate
                current_pan = "Unknown"
                current_deductee = "Unknown"
                current_deductor = "Unknown"
                quarter = "Unknown"

                # --- Using your EXACT original coordinates for PAN ---
                for w in words1:
                    # NOTE: Using the coordinates from your first script
                    if 265 < w["top"] < 275 and 455 < w["x0"] < 510 and re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", w["text"]):
                        current_pan = w["text"]
                        break
                
                # --- Using your EXACT original coordinates for Deductee Name ---
                name_band = [w for w in words1 if 185 < w["top"] < 195 and 300 < w["x0"] < 540]
                if name_band:
                    # Sort words by their horizontal position (x0) to form the name correctly
                    name_band_sorted = sorted(name_band, key=lambda x: x["x0"])
                    combined_name = " ".join([w["text"] for w in name_band_sorted]).strip()
                    current_deductee = combined_name

                # Using simple regex for other details from Page 1
                deductor_match = re.search(r"Name and address of the deductor\n(.*?)\n", text1)
                if deductor_match:
                    current_deductor = deductor_match.group(1).strip()
                
                quarter_match = re.search(r"Quarter\s*\n\s*(Q[1-4]|0[1-4])", text1)
                if quarter_match:
                    quarter = f"Q{quarter_match.group(1).lstrip('0')}"

                # Find and process transactions on Page 1
                payments1 = re.findall(r"(\d{2,}\.\d{2})\s+194\w+\s+(\d{2}-\d{2}-\d{4})", text1)
                challans1 = re.findall(r"(\d{2,}\.\d{2})\s+\d{7}\s+(\d{2}-\d{2}-\d{4})", text1)
                
                for j in range(min(len(payments1), len(challans1))):
                    taxable_val, pay_date = payments1[j]
                    tds_val, _ = challans1[j]
                    rate = round((float(tds_val) / float(taxable_val)) * 100, 2) if float(taxable_val) > 0 else 0.0
                    all_records.append({
                        "Quarter": quarter, "Date of Deduction": pay_date, "Deductee Name": current_deductee,
                        "PAN": current_pan, "Taxable Value": float(taxable_val), "Rate (%)": f"{rate:.2f}",
                        "TDS Amount": float(tds_val), "Deductor Name": current_deductor
                    })

                # --- PROCESS PAGE 2 (if it exists for this certificate) ---
                if start_index + 1 < end_index:
                    page2 = pdf.pages[start_index + 1]
                    text2 = page2.extract_text() or ""
                    
                    payments2 = re.findall(r"(\d{2,}\.\d{2})\s+194\w+\s+(\d{2}-\d{2}-\d{4})", text2)
                    challans2 = re.findall(r"(\d{2,}\.\d{2})\s+\d{7}\s+(\d{2}-\d{2}-\d{4})", text2)
                    
                    # Associate these transactions with the headers found on Page 1
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
        st.error(f"An unexpected error occurred: {e}")
        return pd.DataFrame()
        
    return pd.DataFrame(all_records)


# --- Main Application Flow ---
uploaded_file = st.file_uploader("Upload Merged Form 16A PDF", type="pdf")

if uploaded_file is not None:
    if st.button("▶️ Extract Data"):
        with st.spinner("Processing with original coordinate logic..."):
            extracted_df = extract_data_with_original_logic(uploaded_file)

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
                label="📥 Download as Excel File",
                data=excel_data,
                file_name="Form16A_Final_Extract.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Extraction ran but no data was found. The PDF layout might not match the hardcoded coordinates and structure.")
