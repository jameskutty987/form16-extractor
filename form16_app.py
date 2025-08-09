import streamlit as st
import pdfplumber
import pandas as pd
import re
import io

# ==============================
# Streamlit Page Config
# ==============================
st.set_page_config(page_title="Form 16 TDS Extractor", page_icon="📄", layout="wide")
st.markdown(
    """
    <style>
    body {
        background-color: #0e1117;
        color: #00ff99;
    }
    .stButton>button {
        background-color: #00ff99;
        color: black;
        font-weight: bold;
    }
    .stDownloadButton>button {
        background-color: #00ff99;
        color: black;
        font-weight: bold;
    }
    footer {
        visibility: hidden;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("Form 16 Merged PDF → Excel Extractor")
st.markdown("**Upload a merged Form 16 PDF file and get TDS data in Excel**")

uploaded_file = st.file_uploader("Upload Merged Form 16 PDF", type=["pdf"])

if uploaded_file:
    run_process = st.button("Run Extraction")
    if run_process:
        with pdfplumber.open(uploaded_file) as pdf:
            data_rows = []

            # Process in 3-page blocks
            for start in range(0, len(pdf.pages), 3):
                page1 = pdf.pages[start]
                page2 = pdf.pages[start + 1] if start + 1 < len(pdf.pages) else None

                text1 = page1.extract_text().splitlines()
                text2 = page2.extract_text().splitlines() if page2 else []

                # Deductee Name
                deductee_name = ""
                for i, line in enumerate(text1):
                    if "Name and address of the deductee" in line:
                        deductee_name = text1[i + 1].strip()
                        break

                # PAN of Deductee
                pan_number = ""
                for i, line in enumerate(text1):
                    if "PAN of the deductee" in line:
                        candidate = text1[i + 1].strip()
                        if re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", candidate):
                            pan_number = candidate
                        break

                # Deductor Name
                deductor_name = ""
                for i, line in enumerate(text1):
                    if "Name and address of the deductor" in line:
                        deductor_name = text1[i + 1].strip()
                        break

                # Quarter
                quarter = ""
                for line in text1:
                    if re.search(r"Quarter\s*[:\-]?\s*(Q[1-4])", line, re.IGNORECASE):
                        quarter = re.search(r"(Q[1-4])", line, re.IGNORECASE).group(1)
                        break

                # Function to extract TDS rows from a page
                def extract_tds_rows(lines):
                    tds_entries = []
                    for line in lines:
                        # Match: Date | Taxable Value | Rate% | TDS Amount
                        match = re.match(r"(\d{2}-\d{2}-\d{4})\s+([\d,]+\.\d{2})\s+([\d\.]+)\s+([\d,]+\.\d{2})", line)
                        if match:
                            date = match.group(1)
                            taxable_value = match.group(2).replace(",", "")
                            rate = match.group(3)
                            tds_amount = match.group(4).replace(",", "")
                            tds_entries.append((date, taxable_value, rate, tds_amount))
                    return tds_entries

                # Combine TDS from page 1 and page 2
                tds_rows = extract_tds_rows(text1) + extract_tds_rows(text2)

                for row in tds_rows:
                    data_rows.append({
                        "Quarter": quarter,
                        "Date of Deduction": row[0],
                        "Deductee Name": deductee_name,
                        "PAN": pan_number,
                        "Taxable Value": row[1],
                        "Rate (%)": row[2],
                        "TDS Amount": row[3],
                        "Deductor Name": deductor_name
                    })

        if data_rows:
            df = pd.DataFrame(data_rows)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df.to_excel(writer, index=False)
            st.success("✅ Extraction complete!")
            st.dataframe(df)
            st.download_button("Download Excel", data=output.getvalue(), file_name="tds_data.xlsx")

        else:
            st.error("No valid TDS data found in your file.")

st.markdown("<hr><p style='text-align:center; color:gray;'>Published by JamesCurator</p>", unsafe_allow_html=True)
