# 📢 RBI Circulars Watcher 🚀

This project is an automated Python script that monitors the Reserve
Bank of India (RBI) website for new circulars. When a new circular is
found, it performs a series of actions: it downloads the circular (as a
PDF or an HTML-generated PDF), extracts the text, generates a compliance
checklist using Google's Gemini API, uploads the circular and checklist
to a designated Google Drive folder, and sends an email notification
with the links to a predefined list of recipients.

## 📂 Project Files and Their Use Cases

-   **main.py**: Core Python script orchestrating the entire workflow,
    including web scraping, file handling, API interactions, and email
    sending.
-   **requirements.txt**: Lists all required Python libraries.
-   **credentials.json**: Stores your Google API credentials for Drive
    and Gmail APIs (download from Google Cloud Console).
-   **token.json**: Auto-generated file storing OAuth 2.0 tokens to
    avoid re-authentication.
-   **last_circular.txt**: Stores the ID of the last processed circular
    to prevent duplicates.
-   **RBI_LOG.log**: Log file for all script activities (info, warnings,
    errors).
-   **downloads/**: Temporary folder to store circular PDFs and
    generated checklists before upload.

## ⚙️ Detailed Function Explanations

-   **create_pdf_from_html_content()**: Converts HTML circular pages
    into PDFs using *weasyprint*.
-   **setup_driver()**: Initializes Selenium WebDriver (headless Chrome)
    for scraping.
-   **parse_circulars_table()**: Extracts circular details (number,
    date, department, subject) using BeautifulSoup.
-   **check_pdf_url_exists()**: Verifies PDF URL validity via HEAD
    request.
-   **get_pdf_from_circular_page()**: Finds direct PDF links or extracts
    HTML if unavailable.
-   **get_latest_circular_info()**: Fetches the latest circular from
    RBI's website.
-   **download_pdf()**: Downloads PDFs to the `downloads/` directory.
-   **generate_checklist_from_text()**: Sends extracted text to Gemini
    API to generate a compliance checklist.
-   **create_checklist_file()**: Saves the Gemini-generated checklist
    locally.
-   **authenticate_google_apis()**: Manages OAuth 2.0 authentication for
    Google APIs.
-   **get_or_create_folder()**: Ensures year/month subfolders exist on
    Google Drive, creating them if necessary.
-   **upload_drive()**: Uploads files to the correct Google Drive
    folder.
-   **send_gmail_api_email()**: Sends formatted email notifications with
    links to recipients.
-   **get_last_circular_id() / set_last_circular_id()**: Manage state by
    tracking the last processed circular ID.
-   **main()**: Entry point calling all functions in sequence.

## 🛠️ Technologies Used

### Connecting

-   **Websites**: `requests`, `selenium`, `webdriver-manager`
-   **Google APIs**: `google-auth-oauthlib`, `google-api-python-client`

### Sending

-   **Email**: Python `email` library + Gmail API
-   **AI Prompt**: `google-generativeai` for Gemini model
-   **Files**: Google Drive API for uploads

### Downloading from RBI

-   **Circulars**: `requests` + `selenium`
-   **HTML Content**: `selenium` + `BeautifulSoup`
-   **PDF to Text**: `pdfplumber`
-   **HTML to PDF**: `weasyprint`

## 🚀 How to Run the Project

### Step 1: Prerequisites

-   Python 3.8+ installed
-   Google Chrome installed
-   Google account with Drive and Gmail access

### Step 2: Google API Setup

1.  Go to [Google Cloud Console](https://console.cloud.google.com/).
2.  Create a new project.
3.  Enable **Google Drive API** and **Gmail API**.
4.  Create OAuth 2.0 Client ID credentials (Desktop app).
5.  Download `credentials.json` and place it in the project folder.

### Step 3: Gemini API Setup

1.  Go to [Google AI Studio](https://aistudio.google.com/).
2.  Generate a Gemini API key.
3.  Add the key to `GEMINI_API_KEY` in `main.py`.

### Step 4: Script Configuration

Edit the following variables in `main.py`: - `RBI_FOLDER_ID`: Google
Drive folder ID for storing circulars. - `RECIPIENTS`: Email addresses
of recipients. - `SENDER_EMAIL`: Your authenticated Google account
email.

### Step 5: Install Dependencies

``` bash
pip install -r requirements.txt
```

### Step 6: First Run and Authentication

``` bash
python main.py
```

-   Sign in via browser when prompted.
-   Grant permissions for Drive and Gmail.
-   A `token.json` file will be created for future runs.

### Step 7: Automation

Schedule the script with **Cron** (Linux) or **Task Scheduler**
(Windows).

------------------------------------------------------------------------

## 🎯 Why Use This?
Never miss an RBI update again! ⚡  
Get **instant compliance checklists**, neatly uploaded to **Google Drive**, and notified straight in your inbox 📩.
