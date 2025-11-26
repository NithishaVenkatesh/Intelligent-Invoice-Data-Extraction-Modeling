# Intelligent Invoice Data Extraction & Modeling
Dracarys  
## Objective
This project implements a machine learning-driven pipeline that extracts key structured data from a Google Drive folder of invoice documents (PDFs or images) and models it in a queryable format using a web-based dashboard.

## Project Approach and Reasoning

The pipeline is designed to be modular and scalable, handling invoices of varying formats and quality. The overall architecture is as follows:

**Google Drive Ingestion → OCR → LLM Extraction → Normalization → SQLite Storage → Streamlit Dashboard**

1.  **Data Ingestion:** The pipeline starts by scraping file links from a given public Google Drive folder. It then downloads each file locally for processing.
2.  **OCR (Optical Character Recognition):** A hybrid OCR approach is used for robustness.
    *   **Primary OCR:** **Tesseract** is used as the main engine due to its maturity and power.
    *   **Fallback OCR:** If Tesseract returns very little text (indicating a potentially difficult or image-heavy document), the pipeline automatically falls back to **EasyOCR**, which can sometimes perform better on noisy or stylized images. This two-step process maximizes text recovery.
3.  **LLM-Based Data Extraction:** The raw text from OCR is fed into Google's **Gemini** model. Relying on an LLM is crucial because invoice layouts are inconsistent. A rule-based or regex approach would be too brittle. The LLM is prompted to understand the context of the text and return a structured JSON with the required fields, including nested line items.
4.  **Data Cleaning and Normalization:** The JSON output from the LLM is processed. Dates are parsed into a consistent `YYYY-MM-DD` format using `dateutil`, and numeric fields are cleaned and converted to floats. This ensures data integrity.
5.  **Database Storage:** The cleaned data is stored in a **SQLite** database. SQLite was chosen because it is serverless, lightweight, and file-based, making the project easily portable and self-contained without requiring a separate database server. The schema is relational, with an `invoices` table and a `line_items` table linked by the `invoice_number`.
6.  **Dashboard and Demo:** A **Streamlit** application serves as the user interface. It connects to the SQLite database to provide a readable view of the extracted data, allows for simple queries (searching by vendor, filtering by date), and offers the ability to download the data as CSVs.

---

### Discussion of Trade-offs: Regex vs. OCR+LLM vs. Vision+LLM

**1. Regex (Regular Expressions)**
*   **Pros:** Extremely fast and computationally cheap. Can be very accurate for a fixed, known invoice template.
*   **Cons:** Highly brittle and completely fails with any change in layout, format, or wording. It is not a scalable solution for handling invoices from multiple vendors. The maintenance overhead is enormous.

**2. OCR + LLM (This Project's Approach)**
*   **Pros:** Very flexible and robust against variations in layout. It separates the task of "reading" (OCR) from "understanding" (LLM). This allows it to handle new, unseen invoice formats effectively. Development is fast thanks to powerful pre-trained LLMs.
*   **Cons:** The accuracy is capped by the quality of the OCR. If the OCR misreads a character, the LLM will receive incorrect information. It also loses the 2D spatial information of the document; the LLM only knows the sequence of words, not their exact position on the page.

**3. Vision + LLM (e.g., LayoutLMv3, Donut, Gemini Vision)**
*   **Pros:** The most powerful approach. These models process both the text and the document image simultaneously, understanding the layout. This helps them correctly associate labels with values (e.g., knowing a number is the "Total" because of its location and font size). This leads to the highest potential accuracy.
*   **Cons:** These models are more complex and computationally expensive to run. For the best performance on a specific document type, they often require fine-tuning on a manually labeled dataset, which is a time-consuming process.

---
### Why the OCR + LLM Approach Was Chosen

The **OCR + LLM approach was the strategic choice for this project as it strikes the most effective and pragmatic balance between flexibility, development speed, and accuracy.**

While a Regex-based solution is fast, it is fundamentally unsuitable for the core problem of handling invoices with diverse and unpredictable layouts. It would fail immediately, making it a non-starter.

On the other end of the spectrum, a Vision + LLM model, while potentially the most accurate, introduces significant complexity. Achieving its peak performance would require creating a manually labeled dataset of invoices and fine-tuning the model, a process that is both time-consuming and computationally expensive.

The OCR + LLM method sits in the "sweet spot." It elegantly handles layout variations by decoupling the "reading" task (OCR) from the "understanding" task (LLM). By leveraging a powerful, pre-trained model like Gemini, we can achieve high accuracy on a wide range of unseen documents *without* the prohibitive overhead of data labeling and custom training. This makes it the ideal approach for rapidly developing a scalable and robust solution that directly meets the assignment's objectives.
---

## How to Set Up and Run the Project

### 1. Prerequisites
You must have the following installed on your system:
*   Python 3.8+
*   **Tesseract-OCR Engine:**
    *   **macOS:** `brew install tesseract`
    *   **Ubuntu/Debian:** `sudo apt-get install tesseract-ocr`
*   **Poppler (for PDF processing):**
    *   **macOS:** `brew install poppler`
    *   **Ubuntu/Debian:** `sudo apt-get install poppler-utils`

### 2. Clone the Repository
```sh
git clone <your-repo-url>
cd <your-repo-name>
```

### 3. Set Up a Virtual Environment and Install Dependencies
```sh
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Set Your API Key
You need a Google Gemini API key. Set it as an environment variable.
*   **macOS/Linux:**
    ```sh
    export GEMINI_API_KEY="YOUR_API_KEY_HERE"
    ```
*   **Windows:**
    ```sh
    set GEMINI_API_KEY="YOUR_API_KEY_HERE"
    ```

### 5. Run the Extraction Pipeline
This will process the invoices from the Google Drive folder specified in `main.py` and populate `invoices.db`.
```sh
python main.py
```

### 6. Launch the Dashboard
Start the Streamlit application to view and query the data.
```sh
streamlit run app.py
```