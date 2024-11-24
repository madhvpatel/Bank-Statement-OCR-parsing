from flask import Flask, request, jsonify, send_file
import cv2
import os
import pytesseract
from PIL import Image
from pdf2image import convert_from_path
import pandas as pd

# Ensure Tesseract is installed
# This would need to be ensured in the server environment beforehand
# !sudo apt-get install -y tesseract-ocr
# !pip install pytesseract pdf2image pandas

app = Flask(__name__)

# Output directory for intermediate images
output_dir = "temp_images"
os.makedirs(output_dir, exist_ok=True)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    # Save the uploaded file
    pdf_path = os.path.join(output_dir, file.filename)
    file.save(pdf_path)

    # Convert PDF to images
    print("Converting PDF to images...")
    try:
        pages = convert_from_path(pdf_path, 300)  # 300 DPI for better OCR accuracy
    except Exception as e:
        return jsonify({"error": f"Failed to convert PDF to images: {str(e)}"}), 500

    # Check if the PDF is text-based or scanned
    is_text_based = False
    for page in pages:
        text = pytesseract.image_to_string(page, config="--psm 6")
        if text.strip():  # If there is any text, it's likely text-based
            is_text_based = True
            break

    if not is_text_based:
        return jsonify({"error": "The uploaded PDF appears to be a scanned document. Please upload a text-based PDF."}), 400

    # Initialize list to store data for the table
    tabulated_data = []

    # Specify the column delimiter
    delimiter = "|"  # Replace with desired delimiter: ',', '\t', ' ', etc.

    for i, page in enumerate(pages):
        # Save each page as an image
        image_path = os.path.join(output_dir, f"page_{i + 1}.jpg")
        page.save(image_path, "JPEG")

        # Read the image
        images = cv2.imread(image_path)

        # Convert to grayscale
        gray = cv2.cvtColor(images, cv2.COLOR_BGR2GRAY)

        # Apply preprocessing
        pre_processor = "thresh"  # You can change this to 'blur'
        if pre_processor == "thresh":
            gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        elif pre_processor == "blur":
            gray = cv2.medianBlur(gray, 3)

        # Save processed image to memory
        processed_filename = f"processed_{i + 1}.jpg"
        cv2.imwrite(processed_filename, gray)

        # Perform OCR on the image
        text = pytesseract.image_to_string(Image.open(processed_filename), config="--psm 6")  # PSM 6 for semi-structured data

        # Convert OCR text into rows using delimiter
        for line in text.split("\n"):
            # Split each line into columns based on the specified delimiter
            columns = line.split(delimiter)
            if columns:  # Avoid empty lines
                tabulated_data.append(columns)

        # Clean up processed image
        os.remove(processed_filename)

    # Convert tabulated data to a DataFrame
    df = pd.DataFrame(tabulated_data)

    # Filter rows that contain 'Hitachi' in the narration (case insensitive)
    hitachi_filtered_df = df[df.apply(lambda row: row.astype(str).str.contains('hitachi', case=False, na=False).any(), axis=1)]

    # Save important data (such as bank name, account holder, IFSC, etc.) and filtered transactions
    important_info = []
    filtered_data = []

    # Extract important information and filtered data
    for _, row in df.iterrows():
        if row.astype(str).str.contains('hitachi', case=False, na=False).any():
            filtered_data.append(row.tolist())
        else:
            # Assume bank name, account holder, IFSC, etc. can be identified by keywords
            if any(keyword in str(row).lower() for keyword in ["bank", "account holder", "ifsc"]):
                important_info.append(row.tolist())

    # Create DataFrames for important info and filtered data
    important_info_df = pd.DataFrame(important_info)
    filtered_data_df = pd.DataFrame(filtered_data)

    # Combine both DataFrames while preserving the important information
    combined_df = pd.concat([important_info_df, filtered_data_df], ignore_index=True)

    # Save the combined DataFrame to a CSV file
    output_csv = os.path.join(output_dir, "filtered_extracted_table.csv")
    combined_df.to_csv(output_csv, index=False, header=False)

    # Return the CSV file
    return send_file(output_csv, as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
