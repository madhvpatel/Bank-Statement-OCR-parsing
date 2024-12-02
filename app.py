from flask import Flask, request, render_template, send_file, jsonify
import os
import cv2
import pytesseract
from PIL import Image
from pdf2image import convert_from_path
import pandas as pd

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
TEMP_IMAGES_FOLDER = 'temp_images'

# Ensure necessary folders exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(TEMP_IMAGES_FOLDER, exist_ok=True)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # Save uploaded file
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)

    try:
        # Convert PDF to images
        pages = convert_from_path(file_path, 300)
        tabulated_data = []
        delimiter = "|"  # Customize this as needed

        for i, page in enumerate(pages):
            # Save each page as an image
            image_path = os.path.join(TEMP_IMAGES_FOLDER, f"page_{i + 1}.jpg")
            page.save(image_path, "JPEG")

            # Preprocess the image
            images = cv2.imread(image_path)
            gray = cv2.cvtColor(images, cv2.COLOR_BGR2GRAY)
            gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

            # Perform OCR
            processed_filename = f"processed_{i + 1}.jpg"
            cv2.imwrite(processed_filename, gray)
            text = pytesseract.image_to_string(Image.open(processed_filename), config="--psm 6")

            # Convert OCR text into rows using delimiter
            for line in text.split("\n"):
                columns = line.split(delimiter)
                if columns:  # Avoid empty lines
                    tabulated_data.append(columns)

            # Clean up processed image
            os.remove(processed_filename)

        # Convert tabulated data to a DataFrame
        df = pd.DataFrame(tabulated_data)

        # Filter rows containing 'Hitachi' in the narration
        filtered_data_df = df[df.apply(lambda row: row.astype(str).str.contains('hitachi', case=False, na=False).any(), axis=1)]

        # Save filtered data to a CSV
        output_csv_path = os.path.join(OUTPUT_FOLDER, 'filtered_extracted_table.csv')
        filtered_data_df.to_csv(output_csv_path, index=False, header=False)

        # Cleanup temporary images
        for image_file in os.listdir(TEMP_IMAGES_FOLDER):
            os.remove(os.path.join(TEMP_IMAGES_FOLDER, image_file))

        return send_file(output_csv_path, as_attachment=True, download_name='filtered_extracted_table.csv')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
