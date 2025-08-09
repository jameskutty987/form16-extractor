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
        for base_page in range(0, len(pdf.pages), 3):

            # ----------- PAGE 1 -----------
            page1 = pdf.pages[base_page]
            words1 = page1.extract_words()
            text1 = page1.extract_text() or ""

            current_pan = "Unknown"
            current_deductee = "Unknown"
            current_deductor = "Unknown"

            # PAN from Page 1 coordinates
            for w in words1:
                if 265 < w["top"] < 275 and 455 < w["x0"] < 510 and re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", w["text"]):
                    current_pan = w["text"]
                    break

            # Deductee Name from Page 1
            name_band = [w for w in words1 if 185 < w["top"] < 195 and 300 < w["x0"] < 540]
            name_band_sorted = sorted(name_band, key=lambda x: x["x0"])
            combined = " ".join([w["text"] for w in name_band_sorted]).strip()
            current_deductee = combined[:40] if combined else "Unknown"

            # Deductor Name from Page 1
            for i, line in enumerate(text1.splitlines()):
                if "Name and address of the deductor" in line:
                    for j in range(i + 1, len(text1.splitlines())):
                        val = text1.splitlines()[j].strip()
                        if val:
                            current_deductor = val
                            break

            # Quarter from Page 1
            match = re.search(r"Summary of tax deducted.*?\nQ([1-4])", text1, re.DOTALL)
            quarter = f"Q{match.group(1)}" if match else "Unknown"

            # Extract TDS & Taxable from Page 1 text
            payments1 = re.findall(r"(\d{4,6}\.\d{2})\s+194\w+\s+(\d{2}-\d{2}-\d{4})", text1)
            challans1 = re.findall(r"(\d{3,5}\.\d{2})\s+051\d+\s+(\d{2}-\d{2}-\d{4})", text1)

            for i in range(min(len(payments1), len(challans1))):
                taxable_val, pay_date = payments1[i]
                tds_val, _ = challans1[i]
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

            # ----------- PAGE 2 -----------
            if base_page + 1 < len(pdf.pages):
                page2 = pdf.pages[base_page + 1]
                text2 = page2.extract_text() or ""

                # Extract from Page 2 only if numbers exist
                payments2 = re.findall(r"(\d{4,6}\.\d{2})\s+194\w+\s+(\d{2}-\d{2}-\d{4})", text2)
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
                        "Deductee Name": current_deductee,  # From page 1
                        "PAN": current_pan,  # From page 1
                        "Taxable Value": taxable_val,
                        "Rate (%)": f"{rate:.2f}",
                        "TDS Amount": tds_val,
                        "Deductor Name": current_deductor  # From page 1
                    })

    return pd.DataFrame(rows)


# App logic
if uploaded_file and st.button("▶️ Extract"):
    with st.spinner("Extracting data..."):
        df = extract_form16_data(uploaded_file)

    if df.empty:
        st.error("❌ No TDS data found.")
    else:
        df = df[["Quarter", "Date of Deduction", "Deductee Name", "PAN",
                 "Taxable Value", "Rate (%)", "TDS Amount", "Deductor Name"]]
        st.success("✅ Extraction Complete. Preview Below:")
        st.dataframe(df)

        buffer = BytesIO()
        df.to_excel(buffer, index=False)
        st.download_button("📥 Download Excel",
                           buffer.getvalue(),
                           "Form16_TDS_Extracted.xlsx")
