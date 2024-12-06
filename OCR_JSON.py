import os
import shutil
import json
from pdf2image import convert_from_path
import cv2
import pytesseract
from PyPDF2 import PdfReader
from google.colab import files  # For file download in Colab environment

def process_pdfs(input_folder):
    """
    Process PDFs in the input folder, classify them as text-based or scanned,
    and perform OCR on text-based PDFs to extract data.

    :param input_folder: Path to the folder containing PDF files.
    """
    # Create necessary directories
    scanned_folder = os.path.join(input_folder, "scanned_image_based_pdfs")
    output_json_folder = os.path.join(input_folder, "output_json")
    os.makedirs(scanned_folder, exist_ok=True)
    os.makedirs(output_json_folder, exist_ok=True)

    # Iterate through all files in the folder
    for file in os.listdir(input_folder):
        if file.lower().endswith(".pdf"):
            pdf_path = os.path.join(input_folder, file)
            print(f"Processing: {file}")

            # Check if PDF is text-based
            try:
                reader = PdfReader(pdf_path)
                text_content = "".join(page.extract_text() or "" for page in reader.pages)
                
                if text_content.strip():  # Text-based PDF
                    print(f"{file} is a text-based PDF. Proceeding with OCR...")
                    perform_ocr_and_extract(pdf_path, output_json_folder)
                else:  # Scanned image-based PDF
                    print(f"{file} is a scanned image-based PDF. Moving to {scanned_folder}...")
                    shutil.move(pdf_path, os.path.join(scanned_folder, file))
            except Exception as e:
                print(f"Error processing {file}: {e}")

def perform_ocr_and_extract(pdf_path, output_folder):
    """
    Perform OCR on a PDF file and extract data into a JSON file.

    :param pdf_path: Path to the PDF file.
    :param output_folder: Folder to save the JSON output.
    """
    # Output directory for intermediate images
    output_dir = "temp_images"
    os.makedirs(output_dir, exist_ok=True)

    # Convert PDF to images
    pages = convert_from_path(pdf_path, 300)  # 300 DPI for better OCR accuracy

    # Initialize data structure for storing transaction details
    bank_details = {
        "ResponseCode": "00",
        "ResponseMessage": "Success",
        "BankStatement": {
            "transactionData": []
        }
    }

    for i, page in enumerate(pages):
        # Save each page as an image
        image_path = os.path.join(output_dir, f"page_{i + 1}.jpg")
        page.save(image_path, "JPEG")

        # Read the image
        images = cv2.imread(image_path)

        # Convert to grayscale and preprocess
        gray = cv2.cvtColor(images, cv2.COLOR_BGR2GRAY)
        gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

        # Perform OCR on the image
        text = pytesseract.image_to_string(gray, config="--psm 6")

        # Extract relevant details and transactions
        for line in text.split("\n"):
            if "hitachi" in line.lower():
                columns = line.split("|")
                bank_details["BankStatement"]["transactionData"].append({
                    "description": columns[0].strip(),
                    "withdrawAmt": columns[1].strip() if len(columns) > 1 else "0.00",
                    "depositAmt": columns[2].strip() if len(columns) > 2 else "0.00",
                    "balance": columns[3].strip() if len(columns) > 3 else "0.00"
                })

    # Save JSON response to a file
    json_filename = os.path.splitext(os.path.basename(pdf_path))[0] + ".json"
    output_json_path = os.path.join(output_folder, json_filename)
    with open(output_json_path, "w") as json_file:
        json.dump(bank_details, json_file, indent=4)

    print(f"Data from {pdf_path} saved to {output_json_path}")

    # Optional: Clean up temporary images
    for image_file in os.listdir(output_dir):
        os.remove(os.path.join(output_dir, image_file))
    os.rmdir(output_dir)


# Example usage
input_folder_path = "/content/drive/MyDrive/bank_pdf"  
process_pdfs(input_folder_path)
