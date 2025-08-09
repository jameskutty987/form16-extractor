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
        for form_start in range(0, len(pdf.pages), 3):

            # ---------- PAGE 1 ----------
            page1 = pdf.pages[form_start]
            words1 = page1.extract_words()
            text1 = page1.extract_text()
            if not text1:
                continue

            current_pan = "Unknown"
            current_deductee = "Unknown"
            current_deductor = "Unknown"

            # PAN
            for w in words1:
                if 265 < w["top"] < 275 and 455 < w["x0"] < 510 and re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", w["text"]):
                    current_pan = w["text"]
                    break

            # Deductee Name
            name_band = [w for w in words1 if 185 < w["top"] < 195 and 300 < w["x0"] < 540]
            name_band_sorted = sorted(name_band, key=lambda x: x["x0"])
            combined = " ".join([w["text"] for w in name_band_sorted]).strip()
            current_deductee = combined[:40] if combined else "Unknown"

            # Deductor Name
            for i, line in enumerate(text1.splitlines()):
                if "Name and address of the deductor" in line:
                    for j in range(i + 1, len(text1.splitlines())):
                        val = text1.splitlines()[j].strip()
                        if val:
                            current_deductor = val
                            break

            # Quarter
            match = re.search(r"Summary of tax deducted.*?\nQ([1-4])", text1, re.DOTALL)
            quarter = f"Q{match.group(1)}" if match else "Unknown"

            # Payments & Challans from Page 1
            payments = re.findall(r"(\d{4,6}\.\d{2})\s+194\w+\s+(\d{2}-\d{2}-\d{4})", text1)
            challans = re.findall(r"(\d{3,5}\.\d{2})\s+051\d+\s+(\d{2}-\d{2}-\d{4})", text1)

            for i in range(min(len(payments), len(challans))):
                taxable_val, pay_date = payments[i]
                tds_val, tds_date = challans[i]
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

            # ---------- PAGE 2 ----------
            if form_start + 1 < len(pdf.pages):
                page2 = pdf.pages[form_start + 1]
                words2 = page2.extract_words()
                text2 = page2.extract_text()

                if text2:
                    for w in words2:
                        # Extract TDS Amount from fixed column (~ x0 between 120-160)
                        if 120 < w["x0"] < 160 and re.fullmatch(r"\d+\.\d{2}", w["text"]):
                            tds_val = w["text"]

                            # Find date in same row (~ x0 between 320-380)
                            row_top = w["top"]
                            date_match = [d["text"] for d in words2 if abs(d["top"] - row_top) < 3 and 320 < d["x0"] < 380 and re.fullmatch(r"\d{2}-\d{2}-\d{4}", d["text"])]
                            pay_date = date_match[0] if date_match else "Unknown"

                            # Reverse taxable value estimation (optional, using 10% default if unknown)
                            try:
                                rate_guess = 10.0
                                taxable_val = round(float(tds_val) * (100 / rate_guess), 2)
                            except:
                                taxable_val = 0.0

                            rows.append({
                                "Quarter": quarter,
                                "Date of Deduction": pay_date,
                                "Deductee Name": current_deductee,
                                "PAN": current_pan,
                                "Taxable Value": f"{taxable_val:.2f}",
                                "Rate (%)": f"{rate_guess:.2f}",
                                "TDS Amount": tds_val,
                                "Deductor Name": current_deductor
                            })

    return pd.DataFrame(rows)


# ---------- APP LOGIC ----------
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
