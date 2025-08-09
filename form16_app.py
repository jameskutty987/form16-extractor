import streamlit as st
import pdfplumber
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="Form 16 TDS Extractor", layout="centered")

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
        content: 'Published by JamesCurator';
        display: block;
        text-align: center;
        color: gray;
        padding: 10px;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📄 Form 16 TDS Data Extractor")

uploaded_file = st.file_uploader("Upload merged Form 16 PDF", type="pdf")

def extract_form16_data(pdf_file):
    rows = []
    with pdfplumber.open(pdf_file) as pdf:
        for block_start in range(0, len(pdf.pages), 3):
            # -------- Process Page 1 --------
            page1 = pdf.pages[block_start]
            words = page1.extract_words()
            text = page1.extract_text() or ""
            if not text.strip():
                continue

            current_pan = "Unknown"
            current_deductee = "Unknown"
            current_deductor = "Unknown"

            # PAN from page1
            for w in words:
                if 265 < w["top"] < 275 and 455 < w["x0"] < 510 and re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", w["text"]):
                    current_pan = w["text"]
                    break

            # Deductee name from page1
            name_band = [w for w in words if 185 < w["top"] < 195 and 300 < w["x0"] < 540]
            name_band_sorted = sorted(name_band, key=lambda x: x["x0"])
            combined = " ".join([w["text"] for w in name_band_sorted]).strip()
            if combined:
                current_deductee = combined[:40]

            # Deductor name from page1
            for i, line in enumerate(text.splitlines()):
                if "Name and address of the deductor" in line:
                    for j in range(i + 1, len(text.splitlines())):
                        val = text.splitlines()[j].strip()
                        if val:
                            current_deductor = val
                            break

            # Quarter
            match = re.search(r"Summary of tax deducted.*?\nQ([1-4])", text, re.DOTALL)
            quarter = f"Q{match.group(1)}" if match else "Unknown"

            # Extract TDS rows from page1
            payments = re.findall(r"(\d{4,6}\.\d{2})\s+194\w+\s+(\d{2}-\d{2}-\d{4})", text)
            challans = re.findall(r"(\d{3,5}\.\d{2})\s+051\d+\s+(\d{2}-\d{2}-\d{4})", text)
            for i in range(min(len(payments), len(challans))):
                taxable_val, pay_date = payments[i]
                tds_val, _ = challans[i]
                try:
                    rate = round((float(tds_val) / float(taxable_val)) * 100, 2)
                except:
                    rate = 0.0
                rows.append({
                    "Quarter": quarter,
                    "Date of Deduction": pay_date,
                    "Deductee Name": current_deductee,
                    "PAN": current_pan,
                    "Taxable Value": taxable_val,
                    "Rate (%)": f"{rate:.2f}",
                    "TDS Amount": tds_val,
                    "Deductor Name": current_deductor
                })

            # -------- Process Page 2 (if exists) --------
            page2_index = block_start + 1
            if page2_index < len(pdf.pages):
                page2 = pdf.pages[page2_index]
                text2 = page2.extract_text() or ""
                if "115" in text2:  # crude check if 115 TDS table is present
                    payments2 = re.findall(r"(\d{4,6}\.\d{2})\s+115\w*\s+(\d{2}-\d{2}-\d{4})", text2)
                    challans2 = re.findall(r"(\d{3,5}\.\d{2})\s+051\d+\s+(\d{2}-\d{2}-\d{4})", text2)
                    for i in range(min(len(payments2), len(challans2))):
                        taxable_val, pay_date = payments2[i]
                        tds_val, _ = challans2[i]
                        try:
                            rate = round((float(tds_val) / float(taxable_val)) * 100, 2)
                        except:
                            rate = 0.0
                        rows.append({
                            "Quarter": quarter,
                            "Date of Deduction": pay_date,
                            "Deductee Name": current_deductee,
                            "PAN": current_pan,
                            "Taxable Value": taxable_val,
                            "Rate (%)": f"{rate:.2f}",
                            "TDS Amount": tds_val,
                            "Deductor Name": current_deductor
                        })

    return pd.DataFrame(rows)

# App logic
if uploaded_file and st.button("▶️ Extract"):
    with st.spinner("Extracting data..."):
        df = extract_form16_data(uploaded_file)

    if df.empty:
        st.error("❌ No TDS data found.")
    else:
        df = df[["Quarter", "Date of Deduction", "Deductee Name", "PAN", "Taxable Value", "Rate (%)", "TDS Amount", "Deductor Name"]]
        st.success("✅ Extraction Complete. Preview Below:")
        st.dataframe(df)

        # Download Excel
        buffer = BytesIO()
        df.to_excel(buffer, index=False)
        st.download_button("📥 Download Excel", buffer.getvalue(), "Form16_TDS_Extracted.xlsx")
