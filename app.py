import os
import shutil
import pdfplumber
import json
import re
import datetime

# Utility Functions
def convert_date_to_d_mm_yyyy(date_str):
    """
    Attempt to parse the date from common formats (dd/mm/yyyy, dd-mm-yyyy, etc.)
    and return it in 'dd-mm-yyyy' format (e.g., '01-09-2022').
    If parsing fails, return the original string.
    """
    date_str = date_str.strip()
    possible_formats = [
        "%d/%m/%Y", "%d-%m-%Y",
        "%d/%m/%y", "%d-%m-%y",
        "%d-%b-%y",  # e.g., "01-SEP-22"
        "%d-%b-%Y"   # e.g., "01-SEP-2022"
    ]
    for fmt in possible_formats:
        try:
            dt = datetime.datetime.strptime(date_str, fmt)
            # Output format: dd-mm-yyyy (e.g., '01-09-2022')
            return dt.strftime("%d-%m-%Y")
        except ValueError:
            pass
    # If none of the formats matched, return the original string
    return date_str

def extract_pattern(text, pattern):
    """Helper function to extract text using regex."""
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None

def generate_response(data, transactions):
    """Generate response with status and remarks."""
    missing_fields = [field for field, value in data.items() if value is None]
    if missing_fields:
        response_code = "01"
        remarks = f"Missed fields: {', '.join(missing_fields)}"
    else:
        response_code = "00"
        remarks = "All fields extracted successfully"

    print(f"Response Code: {response_code} | Remarks: {remarks}")
    return {
        "Response_Code": response_code,
        "Remarks": remarks,
        "Data": data,
        "Transactions": transactions
    }

# Bank Parser Framework
class BankParser:
    def __init__(self):
        self.parsers = {}

    def register_parser(self, bank_name, parser_function):
        """Register a dedicated parser for a specific bank."""
        self.parsers[bank_name.lower()] = parser_function

    def parse(self, pdf_path):
        """Determine the bank type and invoke the corresponding parser."""
        with pdfplumber.open(pdf_path) as pdf:
            first_page_text = pdf.pages[0].extract_text()

            # Identify the bank using keywords in the first page
            for bank_name, parser_function in self.parsers.items():
                if bank_name.lower() in first_page_text.lower():
                    return parser_function(pdf_path)

        # If no parser is found, raise an exception
        raise ValueError("Bank type not recognized. Add a parser for this format.")

# Parser Implementations
def central_bank_of_india_parser(pdf_path):
    """Parser for Central Bank of India."""
    data = {}
    transactions = []

    with pdfplumber.open(pdf_path) as pdf:
        first_page_text = pdf.pages[0].extract_text()

        # Extract data
        data["Bank_Name"] = "Central Bank of India"
        data["Branch_Name"] = extract_pattern(first_page_text, r"Branch Code :(.+)")
        data["Account_Holder"] = extract_pattern(first_page_text, r"M/S (.+)")
        data["Account_Number"] = extract_pattern(first_page_text, r"Account Number :(.+)")
        data["IFSC_Code"] = extract_pattern(first_page_text, r"IFSC :(.+)")
        data["Cleared_Balance"] = extract_pattern(first_page_text, r"Cleared Balance :(.+)")

        # Extract transactions
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                for row in table[1:]:
                    if len(row) >= 5 and "hitachi" in row[4].lower():
                        post_date = row[0].strip() if row[0] else ""
                        value_date = row[1].strip() if row[1] else ""
                        formatted_post_date = convert_date_to_d_mm_yyyy(post_date)
                        formatted_value_date = convert_date_to_d_mm_yyyy(value_date)

                        transactions.append({
                            "Post Date": formatted_post_date,
                            "Value Date": formatted_value_date,
                            "Branch Code": row[2].strip() if row[2] else "",
                            "Cheque Number": row[3].strip() if row[3] else "",
                            "Description": row[4].strip() if row[4] else "",
                            "Debit": row[5].strip() if len(row) > 5 and row[5] else "",
                            "Credit": row[6].strip() if len(row) > 6 and row[6] else "",
                            "Balance": row[7].strip() if len(row) > 7 and row[7] else ""
                        })

    return generate_response(data, transactions)

def city_union_bank_parser(pdf_path):
    """Parser for City Union Bank."""
    data = {}
    transactions = []

    with pdfplumber.open(pdf_path) as pdf:
        first_page_text = pdf.pages[0].extract_text()

        # Extract data
        data["Bank_Name"] = "City Union Bank"
        data["Branch_Name"] = extract_pattern(first_page_text, r"Bank Branch\s*:\s*(.+)")
        data["Account_Holder"] = extract_pattern(first_page_text, r"Account Name\s*:\s*(.+)")
        data["Account_Number"] = extract_pattern(first_page_text, r"Account Number\s*:\s*(\d+)")
        data["IFSC_Code"] = extract_pattern(first_page_text, r"IFSC Code\s*:\s*([A-Z]{4}0[A-Z0-9]{6})")
        data["Cleared_Balance"] = extract_pattern(first_page_text, r"Cleared Balance\s*:\s*([\d,]+\.\d+)")

        # Extract transactions
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                for row in table[1:]:  # Skip the header row
                    if len(row) >= 6 and "hitachi" in row[1].lower():
                        original_date = row[0].strip() if row[0] else ""
                        formatted_date = convert_date_to_d_mm_yyyy(original_date)

                        transactions.append({
                            "Date": formatted_date,
                            "Description": row[1].strip() if row[1] else "",
                            "Cheque": row[2].strip() if row[2] else "",
                            "Debit": row[3].strip() if row[3] else "",
                            "Credit": row[4].strip() if row[4] else "",
                            "Balance": row[5].strip() if row[5] else ""
                        })

    return generate_response(data, transactions)

def chhattisgarh_rajya_gramin_bank_parser(pdf_path):
    """Parser for Chhattisgarh Rajya Gramin Bank."""
    data = {}
    transactions = []

    with pdfplumber.open(pdf_path) as pdf:
        first_page_text = pdf.pages[0].extract_text()

        # Extract data
        data["Bank_Name"] = "Chhattisgarh Rajya Gramin Bank"
        data["Branch_Name"] = extract_pattern(first_page_text, r"Your Branch\s*:\s*(.+)")
        data["Account_Holder"] = extract_pattern(first_page_text, r"Account Holder\s*:\s*(.+)")
        data["Account_Number"] = extract_pattern(first_page_text, r"Account No.\s*:\s*(\d+)")
        data["IFSC_Code"] = extract_pattern(first_page_text, r"IFSC code\s*:\s*([A-Z]{4}0[A-Z0-9]{6})")
        data["Cleared_Balance"] = extract_pattern(first_page_text, r"Cleared Balance\s*:\s*([\d,]+\.\d+)")

        # Extract transactions
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                for row in table[1:]:  # Skip the header row
                    if len(row) >= 6 and "hitachi" in row[2].lower():
                        post_date = row[0].strip() if row[0] else ""
                        value_date = row[1].strip() if row[1] else ""
                        formatted_post_date = convert_date_to_d_mm_yyyy(post_date)
                        formatted_value_date = convert_date_to_d_mm_yyyy(value_date)

                        transactions.append({
                            "Post Date": formatted_post_date,
                            "Value Date": formatted_value_date,
                            "Description": row[2].strip() if row[2] else "",
                            "Debit": row[3].strip() if row[3] else "",
                            "Credit": row[4].strip() if row[4] else "",
                            "Balance": row[5].strip() if row[5] else ""
                        })

    return generate_response(data, transactions)

# Function to Register Parsers
def register_default_parsers(parser_framework):
    parser_framework.register_parser("Central Bank of India", central_bank_of_india_parser)
    parser_framework.register_parser("City Union Bank", city_union_bank_parser)
    parser_framework.register_parser("Chhattisgarh Rajya Gramin Bank", chhattisgarh_rajya_gramin_bank_parser)

# Main Function
def main(input_folder, success_folder, output_json_folder):
    if not os.path.exists(success_folder):
        os.makedirs(success_folder)

    if not os.path.exists(output_json_folder):
        os.makedirs(output_json_folder)

    parser_framework = BankParser()
    register_default_parsers(parser_framework)

    for file_name in os.listdir(input_folder):
        if file_name.lower().endswith('.pdf'):
            pdf_path = os.path.join(input_folder, file_name)
            json_file_name = f"{os.path.splitext(file_name)[0]}.json"
            output_json_path = os.path.join(output_json_folder, json_file_name)

            try:
                # Parse the PDF
                parsed_data = parser_framework.parse(pdf_path)
                # Save as JSON
                with open(output_json_path, 'w') as json_file:
                    json.dump(parsed_data, json_file, indent=4)
                
                # Move successfully parsed PDF to success folder
                shutil.move(pdf_path, os.path.join(success_folder, file_name))
            except ValueError as e:
                print(f"Failed to parse {file_name}: {e}")

# Example Usage
input_folder = './input'  # Replace with the path to your folder containing PDFs
success_folder = './success'  # Replace with the path to your success folder
output_json_folder = './output_json'  # Replace with the path to your output JSON folder
main(input_folder, success_folder, output_json_folder)

