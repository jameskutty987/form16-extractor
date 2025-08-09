def extract_form16a_data_final(pdf_file):
    """
    Extracts TDS data from a merged PDF containing multiple Form 16A certificates.
    
    This function dynamically identifies each certificate, handles data spanning
    multiple pages, and correctly associates payment amounts with TDS deposited
    by using table structures and serial numbers.
    
    This version includes safety checks to prevent AttributeErrors during regex matching.
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
            
            # --- A. Extract Header Information (with safety checks) ---
            header_page = pdf.pages[start_index]
            header_text = header_page.extract_text(x_tolerance=2, y_tolerance=3) or ""
            
            # Safely extract Deductor Name
            deductor_match = re.search(r"Name and address of the deductor\n(.*?)\n", header_text) or re.search(r"Name and address of the deductor\s*(.*?)\s*PAN", header_text)
            deductor_name = deductor_match.group(1).strip() if deductor_match else "Unknown Deductor"

            # Safely extract Deductee Name
            deductee_match = re.search(r"Name and address of the deductee\n(.*?)\n", header_text) or re.search(r"Name and address of the deductee\s*(.*?)\s*Assessment Year", header_text)
            deductee_name = deductee_match.group(1).strip() if deductee_match else "Unknown Deductee"

            # Safely extract PAN
            pan_match = re.search(r"PAN of the deductee\s*\n\s*([A-Z]{5}[0-9]{4}[A-Z])", header_text) or re.search(r"PAN of the deductee\s*([A-Z]{5}[0-9]{4}[A-Z])", header_text)
            pan = pan_match.group(1) if pan_match else "Unknown PAN"

            # Safely extract Quarter
            quarter_match = re.search(r"Quarter\s*\n\s*(Q[1-4]|0[1-4])", header_text) or re.search(r"Period\s*\nFrom\s*To\s*\n\d{2}-\w{3}-\d{4}\s*\d{2}-\w{3}-\d{4}\s*(Q[1-4])", header_text)
            quarter = f"Q{quarter_match.group(1).lstrip('0')}" if quarter_match else "Unknown Quarter"


            # --- B. Extract Transactional Data from all pages in the block ---
            payments_dict = {}
            challans_dict = {}

            for page_num in range(start_index, end_index):
                page = pdf.pages[page_num]
                # Enhanced table settings for better parsing
                tables = page.extract_tables({
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "text",
                    "keep_blank_chars": True
                })

                for table in tables:
                    if not table or not table[0]: continue
                    # Clean up header text by removing None and joining
                    header_row_text = ' '.join(filter(None, table[0])).replace('\n', ' ')

                    # Identify and process "Summary of payment" table
                    if "Amount paid/credited" in header_row_text and "Date of payment/credit" in header_row_text:
                        for row in table[1:]:
                            try:
                                sl_no = row[0].strip() if row[0] else ""
                                amount_str = row[1].strip() if row[1] else "0"
                                date_str = row[4].strip() if row[4] else ""
                                if sl_no.isdigit():
                                    payments_dict[sl_no] = {
                                        'amount_paid': float(amount_str.replace(',', '')),
                                        'payment_date': date_str
                                    }
                            except (ValueError, IndexError):
                                continue # Skip malformed rows

                    # Identify and process "Details of tax deducted... through challan" table
                    if "Tax deposited in respect" in header_row_text and "BSR Code" in header_row_text:
                        for row in table[1:]:
                             try:
                                sl_no = row[0].strip() if row[0] else ""
                                tax_val_str = row[1].strip() if row[1] else "0"
                                if sl_no.isdigit():
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
