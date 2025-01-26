import re
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

import pdfplumber
import spacy
from dateutil import parser as date_parser

# Initialize Logging
logging.basicConfig(
    filename='parser_debug.log',
    filemode='w',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Load spaCy Model
try:
    nlp = spacy.load('en_core_web_lg')  # Using larger model for better NER
    logging.info("spaCy model loaded successfully.")
except Exception as e:
    logging.error(f"Failed to load spaCy model: {e}")
    raise e

# Define Header Synonyms
HEADER_SYNONYMS = {
    "date": ["DATE", "TRANSACTION DATE", "VALUE DATE", "DATE OF TRANSACTION"],
    "description": ["DESCRIPTION", "DETAILS", "TRANSACTION DETAILS", "PARTICULARS"],
    "debit": ["DEBIT", "WITHDRAWAL", "DR"],
    "credit": ["CREDIT", "DEPOSIT", "CR"],
    "balance": ["BALANCE", "AVAILABLE BALANCE", "CLOSING BALANCE"]
}

# Regex Pattern for IFSC Code
IFSC_PATTERN = re.compile(r'\b[A-Z]{4}0[A-Z0-9]{6}\b')

def detect_ifsc_code(text: str) -> Optional[str]:
    match = IFSC_PATTERN.search(text)
    if match:
        return match.group(0)
    return None

def parse_date(date_str: str) -> Optional[str]:
    try:
        date = date_parser.parse(date_str, dayfirst=True).date()
        return date.strftime("%d-%m-%Y")  # Format as DD-MM-YYYY
    except (ValueError, TypeError):
        return None

def parse_amount(amount_str: str) -> str:
    try:
        # Remove any non-numeric characters except dot and comma
        cleaned = re.sub(r'[^\d.,]', '', amount_str)
        # Ensure commas are preserved for formatting
        return cleaned
    except Exception:
        return ""

def map_headers(headers: List[str]) -> Dict[str, int]:
    mapped = {}
    for idx, header in enumerate(headers):
        header_clean = header.strip().upper()
        for key, synonyms in HEADER_SYNONYMS.items():
            if any(syn in header_clean for syn in synonyms):
                mapped[key] = idx
                logging.debug(f"Header '{header}' mapped to field '{key}' at index {idx}.")
                break
    logging.info(f"Final Header Mapping: {mapped}")
    return mapped

def extract_metadata(text: str) -> Dict[str, str]:
    doc = nlp(text)
    metadata = {
        "BankName": "Unknown Bank",
        "AccountHolder": "NA",
        "AccountNumber": "NA",
        "IFSCCode": "NA",
        "TransactionFrom": "NA",
        "TransactionTo": "NA",
        "ClearedBalance": "NA"
    }

    # Extract Entities
    for ent in doc.ents:
        if ent.label_ == "ORG" and metadata["BankName"] == "Unknown Bank":
            metadata["BankName"] = ent.text
            logging.debug(f"NER detected BankName: {ent.text}")
        elif ent.label_ in ["PERSON", "ORG"] and metadata["AccountHolder"] == "NA":
            metadata["AccountHolder"] = ent.text
            logging.debug(f"NER detected AccountHolder: {ent.text}")
        elif ent.label_ == "CARDINAL" and metadata["AccountNumber"] == "NA":
            if len(ent.text) >= 8:
                metadata["AccountNumber"] = ent.text
                logging.debug(f"NER detected AccountNumber: {ent.text}")

    # Detect IFSC Code using Regex
    ifsc_code = detect_ifsc_code(text)
    if ifsc_code:
        metadata["IFSCCode"] = ifsc_code
        logging.debug(f"Regex detected IFSCCode: {ifsc_code}")

    # Extract Transaction Date Range
    date_patterns = [
        r'Transactions From:\s*(\d{2}[/-]\d{2}[/-]\d{4})',
        r'Transaction Period:\s*(\d{2}[/-]\d{2}[/-]\d{4})\s*to\s*(\d{2}[/-]\d{2}[/-]\d{4})'
    ]
    for pattern in date_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            if isinstance(matches[0], tuple) and len(matches[0]) == 2:
                metadata["TransactionFrom"] = parse_date(matches[0][0]) or "NA"
                metadata["TransactionTo"] = parse_date(matches[0][1]) or "NA"
                logging.debug(f"Transaction Period detected: From {metadata['TransactionFrom']} To {metadata['TransactionTo']}")
            elif isinstance(matches[0], str):
                metadata["TransactionFrom"] = parse_date(matches[0]) or "NA"
                metadata["TransactionTo"] = parse_date(matches[0]) or "NA"  # Assuming same date if only one found
                logging.debug(f"Transaction Date detected: {metadata['TransactionFrom']}")
            break

    # Extract Cleared Balance if available
    balance_patterns = [
        r'Cleared Balance:\s*([0-9,]+\.\d{2})',
        r'Available Balance:\s*([0-9,]+\.\d{2})',
        r'Closing Balance:\s*([0-9,]+\.\d{2})'
    ]
    for pattern in balance_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            metadata["ClearedBalance"] = match.group(1)
            logging.debug(f"ClearedBalance detected: {metadata['ClearedBalance']}")
            break

    return metadata

def extract_transactions(tables: List[List[str]], mapped_headers: Dict[str, int], page_num: int) -> List[Dict[str, Any]]:
    transactions = []
    for row_num, row in enumerate(tables, start=1):
        # Skip rows that don't have enough columns
        if len(row) < max(mapped_headers.values()) + 1:
            logging.warning(f"Page {page_num}, Row {row_num}: Incomplete row data. Skipping.")
            continue

        transaction_data = {
            "DATE": row[mapped_headers.get("date", -1)].strip() if mapped_headers.get("date") is not None else "NA",
            "DESCRIPTION": row[mapped_headers.get("description", -1)].strip() if mapped_headers.get("description") is not None else "NA",
            "DEBIT": parse_amount(row[mapped_headers.get("debit", -1)].strip()) if mapped_headers.get("debit") is not None else "",
            "CREDIT": parse_amount(row[mapped_headers.get("credit", -1)].strip()) if mapped_headers.get("credit") is not None else "",
            "BALANCE": parse_amount(row[mapped_headers.get("balance", -1)].strip()) if mapped_headers.get("balance") is not None else ""
        }

        # Parse and validate date
        parsed_date = parse_date(transaction_data["DATE"])
        if not parsed_date:
            logging.warning(f"Invalid date in transaction: {transaction_data['DATE']}")
            logging.warning(f"Page {page_num}, Row {row_num}: Invalid transaction data. Skipping.")
            continue  # Skip invalid transactions
        else:
            transaction_data["DATE"] = parsed_date

        # Validate presence of at least one of DEBIT or CREDIT
        if not transaction_data["DEBIT"] and not transaction_data["CREDIT"]:
            logging.warning(f"Page {page_num}, Row {row_num}: Both DEBIT and CREDIT are zero or empty. Skipping.")
            continue  # Skip transactions with no financial movement

        transactions.append(transaction_data)
        logging.debug(f"Page {page_num}, Row {row_num}: Extracted transaction data: {transaction_data}")

    return transactions

def extract_metadata_from_pdf(pdf: pdfplumber.PDF) -> Dict[str, str]:
    try:
        first_page = pdf.pages[0]
        text = first_page.extract_text()
        metadata = extract_metadata(text)
        logging.info("Metadata extracted successfully.")
        return metadata
    except Exception as e:
        logging.error(f"Failed to extract metadata from PDF: {e}")
        return {}

def process_pdf(pdf_path: str) -> Dict[str, Any]:
    data = {
        "ResponseCode": "00",
        "ResponseMessage": "All fields extracted successfully",
        "Data": {
            "BankName": "Unknown Bank",
            "AccountHolder": "NA",
            "AccountNumber": "NA",
            "IFSCCode": "NA",
            "TransactionFrom": "NA",
            "TransactionTo": "NA",
            "ClearedBalance": "NA",
            "bankStatementTransactions": []
        }
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            logging.info(f"Opened PDF: {pdf_path}")
            # Extract Metadata
            metadata = extract_metadata_from_pdf(pdf)
            data["Data"].update(metadata)

            # Initialize Variables for Transaction Extraction
            all_transactions = []

            for page_num, page in enumerate(pdf.pages, start=1):
                logging.info(f"Processing Page {page_num}...")
                tables = page.extract_tables({
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "intersection_x_tolerance": 5,
                    "intersection_y_tolerance": 5
                })

                if not tables:
                    logging.warning(f"No tables found on Page {page_num}.")
                    continue

                for table in tables:
                    if not table or len(table) < 2:
                        logging.warning(f"Table on Page {page_num} has insufficient rows.")
                        continue

                    headers = table[0]
                    mapped_headers = map_headers(headers)

                    # Check if essential headers are mapped
                    required_fields = ["date", "description", "debit", "credit", "balance"]
                    missing_fields = [field for field in required_fields if field not in mapped_headers]
                    if missing_fields:
                        logging.error(f"Missing required headers on Page {page_num}: {', '.join(missing_fields)}")
                        continue  # Skip this table

                    # Extract transactions from the table (excluding header)
                    for row in table[1:]:
                        transactions = extract_transactions([row], mapped_headers, page_num)
                        all_transactions.extend(transactions)

            # Deduplicate Transactions
            unique_transactions = {}
            for t in all_transactions:
                key = (t["DATE"], t["DESCRIPTION"], t["DEBIT"], t["CREDIT"], t["BALANCE"])
                if key not in unique_transactions:
                    unique_transactions[key] = t
            data["Data"]["bankStatementTransactions"] = list(unique_transactions.values())
            logging.info(f"Transactions deduplicated: {len(unique_transactions)} unique transactions.")

            if not unique_transactions:
                data["ResponseCode"] = "01"
                data["ResponseMessage"] = "No valid transactions found."
                logging.info("Final ResponseCode: 01 | ResponseMessage: No valid transactions found.")
            else:
                logging.info("Final ResponseCode: 00 | ResponseMessage: All fields extracted successfully.")

    except Exception as e:
        logging.error(f"Failed to process PDF: {e}")
        data["ResponseCode"] = "99"
        data["ResponseMessage"] = "An error occurred during processing."

    return data

def save_output(data: Dict[str, Any], output_path: str = "output.json"):
    try:
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=4)
        logging.info(f"Parsed data saved to {output_path}")
    except Exception as e:
        logging.error(f"Failed to save output: {e}")

def main():
    pdf_path = "/Users/madhavpatel/madhavpatel/statement_reader/bank_parser/bank_pdf/MCRM3901 - Lakshmi Vilas Bank - Nov 22.pdf"  # Replace with your actual PDF path
    logging.info(f"Starting processing for PDF: {pdf_path}")

    parsed_data = process_pdf(pdf_path)
    save_output(parsed_data)

    # Optionally, print the JSON output
    print(json.dumps(parsed_data, indent=4))

if __name__ == "__main__":
    main()
