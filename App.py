import os
import time
import requests
import re
from datetime import datetime
import base64
import logging

# Email libraries
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import pdfplumber

# Google API libraries
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError
import google.generativeai as genai

# === CONFIGURATION ===
BASE_PAGE = "https://rbi.org.in/Scripts/BS_CircularIndexDisplay.aspx"
RBI_BASE = "https://rbi.org.in/Scripts/"
LAST_CIRCULAR_FILE = 'last_circular.txt'

# Combine scopes for Drive and Gmail APIs
SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/gmail.send'
]
# Add your recipient email addresses
RECIPIENTS = ["<YOUR_RECIPIENT_EMAIL_1>", "<YOUR_RECIPIENT_EMAIL_2>"]
SENDER_EMAIL = "<YOUR_SENDER_EMAIL>"

# === Google Drive Folder Configuration ===
# Paste the folder ID of your permanent "RBI" folder here.
# The script will create year and month sub-folders inside this folder.
RBI_FOLDER_ID = "<YOUR_GOOGLE_DRIVE_FOLDER_ID>"

# === Gemini API Configuration ===
# Add your Gemini API key here
GEMINI_API_KEY = "<YOUR_GEMINI_API_KEY>"

# === LOGGING CONFIGURATION ===
# Corrected log file path to ensure it is in the script's directory
script_dir = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(script_dir, 'RBI_LOG.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)


# === HELPER FUNCTIONS ===
def create_pdf_from_html_content(circular_data, html_content):
    """Create a PDF from HTML content when no PDF is available"""
    try:
        from weasyprint import HTML
        html_doc = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{circular_data['circular_number']}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
                .header {{ text-align: center; border-bottom: 2px solid #000; padding-bottom: 10px; margin-bottom: 20px; }}
                .circular-no {{ font-weight: bold; font-size: 14px; }}
                .date {{ font-style: italic; margin-top: 5px; }}
                .content {{ margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="circular-no">{circular_data['circular_number']}</div>
                <div class="date">{circular_data['date']}</div>
                <div>{circular_data['subject']}</div>
            </div>
            <div class="content">
                {html_content}
            </div>
        </body>
        </html>
        """
        safe_name = re.sub(r'[^\w\-_.]', '_', circular_data['circular_number'])
        filename = f"RBI_Circular_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        os.makedirs('downloads', exist_ok=True)
        filepath = os.path.join('downloads', filename)
        HTML(string=html_doc).write_pdf(filepath)
        logging.info(f"PDF created from HTML content: {filepath}")
        return filepath
    except ImportError:
        logging.warning("weasyprint not installed. Install it with: pip install weasyprint")
        logging.info("Saving HTML content instead...")
        safe_name = re.sub(r'[^\w\-_.]', '_', circular_data['circular_number'])
        filename = f"RBI_Circular_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        os.makedirs('downloads', exist_ok=True)
        filepath = os.path.join('downloads', filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        logging.info(f"HTML content saved: {filepath}")
        return filepath
    except Exception as e:
        logging.error(f"Error creating PDF from HTML: {e}")
        return None


def setup_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument(
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    try:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        logging.error(f"Failed to set up WebDriver: {e}")
        return None


def parse_circulars_table(soup):
    circulars = []
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 4:
                first_cell = cells[0]
                link = first_cell.find('a', href=True)
                if link and 'BS_CircularIndexDisplay.aspx?Id=' in link['href']:
                    try:
                        circular_data = {
                            'link': link,
                            'href': link['href'],
                            'circular_number': link.get_text(strip=True),
                            'date': cells[1].get_text(strip=True) if len(cells) > 1 else '',
                            'department': cells[2].get_text(strip=True) if len(cells) > 2 else '',
                            'subject': cells[3].get_text(strip=True) if len(cells) > 3 else '',
                        }
                        circulars.append(circular_data)
                    except Exception as e:
                        logging.warning(f"Error parsing row: {e}")
                        continue
    return circulars


def generate_pdf_from_circular_id(circular_id):
    pdf_patterns = [
        f"https://rbidocs.rbi.org.in/rdocs/content/pdfs/{circular_id}.pdf",
        f"https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid={circular_id}",
        f"https://rbidocs.rbi.org.in/rdocs/circulars/{circular_id}.pdf",
    ]
    return pdf_patterns


def check_pdf_url_exists(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/pdf,application/octet-stream,*/*',
            'Referer': 'https://rbi.org.in/'
        }
        response = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
        content_type = response.headers.get('content-type', '').lower()
        if response.status_code == 200 and 'pdf' in content_type:
            logging.info(f"Valid PDF found: {url}")
            return True
        else:
            logging.warning(f"Not a valid PDF: {url} (Status: {response.status_code}, Type: {content_type})")
            return False
    except Exception as e:
        logging.error(f"Error checking URL {url}: {e}")
        return False


def get_pdf_from_circular_page(circular_url):
    driver = setup_driver()
    if not driver:
        return None, None

    try:
        logging.info(f"Loading circular page: {circular_url}")
        driver.get(circular_url)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        circular_id = None
        if '?Id=' in circular_url:
            circular_id = circular_url.split('?Id=')[1].split('&')[0]
            logging.info(f"Circular ID: {circular_id}")

        pdf_links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            if href.lower().endswith('.pdf') and 'utkarsh' not in href.lower():
                full_url = urljoin(circular_url, href)
                if check_pdf_url_exists(full_url):
                    pdf_links.append(full_url)

        for tag in soup.find_all(['object', 'iframe', 'embed']):
            src = tag.get('src') or tag.get('data')
            if src and '.pdf' in src.lower() and 'utkarsh' not in src.lower():
                full_url = urljoin(circular_url, src)
                if check_pdf_url_exists(full_url):
                    pdf_links.append(full_url)

        if circular_id and not pdf_links:
            logging.info("Trying to generate PDF URLs from circular ID...")
            potential_urls = generate_pdf_from_circular_id(circular_id)
            for url in potential_urls:
                if check_pdf_url_exists(url):
                    pdf_links.append(url)
                    break

        if not pdf_links:
            logging.info("This appears to be an HTML-only circular")
            page_content = driver.find_element(By.TAG_NAME, 'body').get_attribute('innerHTML')
            return "HTML_ONLY", page_content

        pdf_links = list(set(pdf_links))
        if pdf_links:
            logging.info(f"Found valid PDF link: {pdf_links[0]}")
            return pdf_links[0], None
        else:
            logging.warning("No valid PDF found for this circular")
            return None, None
    except Exception as e:
        logging.error(f"Error loading circular page: {e}")
        return None, None
    finally:
        if driver:
            driver.quit()


def get_latest_circular_info():
    driver = setup_driver()
    if not driver:
        return None

    try:
        logging.info("Loading RBI circulars page...")
        driver.get(BASE_PAGE)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(3)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        circulars = parse_circulars_table(soup)
        if not circulars:
            logging.error("No circulars found in table format")
            return None

        latest_circular = circulars[0]
        circular_url = urljoin(RBI_BASE, latest_circular['href'])
        latest_circular['url'] = circular_url
        return latest_circular
    except Exception as e:
        logging.error(f"Error fetching latest circular: {e}")
        return None
    finally:
        if driver:
            driver.quit()


def download_pdf(pdf_url):
    try:
        logging.info(f"Downloading PDF from: {pdf_url}")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/pdf,application/octet-stream,*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Referer': 'https://rbi.org.in/'
        }
        response = requests.get(pdf_url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()
        content_type = response.headers.get('content-type', '').lower()
        logging.info(f"Content-Type: {content_type}")
        url_path = urlparse(pdf_url).path
        fname = url_path.split('/')[-1].split('?')[0] or f"rbi_circular_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        if not fname.lower().endswith('.pdf'):
            fname += '.pdf'
        name_parts = fname.rsplit('.pdf', 1)
        fname = f"{name_parts[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        # Corrected part: create 'downloads' folder in the script's directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        downloads_dir = os.path.join(script_dir, 'downloads')
        os.makedirs(downloads_dir, exist_ok=True)
        path = os.path.join(downloads_dir, fname)

        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        with open(path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
        logging.info(f"PDF saved to: {path} ({downloaded} bytes)")
        with open(path, 'rb') as f:
            header = f.read(4)
            if header != b'%PDF':
                logging.warning("Downloaded file doesn't appear to be a valid PDF")
        return path
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed downloading PDF: {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error downloading PDF: {e}")
        return None


def generate_checklist_from_text(document_text):
    """
    Uses the Gemini 2.5 Flash model to generate a checklist from the document text.
    """
    genai.configure(api_key=GEMINI_API_KEY)

    # Use the 'gemini-2.5-flash' model
    model = genai.GenerativeModel('gemini-2.5-flash')

    prompt = f"""
    As an expert in RBI regulations and cybersecurity, analyze the provided text to generate a unified, exhaustive compliance checklist, grouping all requirements under clear headings and converting each specific, detailed item into an audit-ready yes/no question without omitting any conditions or timeframes.
    Circular Text:
    {document_text}

    Compliance Checklist:
    """

    try:
        logging.info("Generating checklist using Gemini 2.5 Flash...")
        response = model.generate_content(prompt)
        checklist_text = response.text.strip()
        logging.info("Checklist generated successfully.")
        return checklist_text
    except Exception as e:
        logging.error(f"Error generating checklist with Gemini: {e}")
        return None


def create_checklist_file(checklist_text, circular_data):
    """Saves the generated checklist to a local text file."""
    try:
        safe_name = re.sub(r'[^\w\-_.]', '_', circular_data['circular_number'])
        filename = f"RBI_Checklist_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

        script_dir = os.path.dirname(os.path.abspath(__file__))
        downloads_dir = os.path.join(script_dir, 'downloads')
        os.makedirs(downloads_dir, exist_ok=True)
        filepath = os.path.join(downloads_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(checklist_text)

        logging.info(f"Checklist saved to: {filepath}")
        return filepath
    except Exception as e:
        logging.error(f"Error saving checklist file: {e}")
        return None


def authenticate_google_apis():
    """Authenticate with Google APIs using OAuth 2.0 and the specified scopes."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as f:
            f.write(creds.to_json())
    return creds


def get_or_create_folder(drive_service, folder_name, parent_id):
    """Checks if a folder exists and returns its ID, otherwise creates it and returns the new ID."""
    try:
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents"
        results = drive_service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        folders = results.get('files', [])

        if folders:
            folder_id = folders[0]['id']
            logging.info(f"Found existing folder: '{folder_name}' (ID: {folder_id})")
            return folder_id
        else:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            folder = drive_service.files().create(body=file_metadata, fields='id').execute()
            folder_id = folder['id']
            logging.info(f"Created new folder: '{folder_name}' (ID: {folder_id})")
            return folder_id
    except Exception as e:
        logging.error(f"Error handling folder '{folder_name}' with parent '{parent_id}': {e}")
        return None


def upload_drive(filepath, drive_service, rbi_folder_id):
    """
    Uploads a file to Google Drive in a structured folder hierarchy:
    RBI_FOLDER_ID -> Current Year -> Current Month -> File
    """
    try:
        current_year = datetime.now().strftime('%Y')
        year_folder_id = get_or_create_folder(drive_service, current_year, rbi_folder_id)
        if not year_folder_id:
            return None

        current_month = datetime.now().strftime('%B')
        month_folder_id = get_or_create_folder(drive_service, current_month, year_folder_id)
        if not month_folder_id:
            return None

        file_metadata = {'name': os.path.basename(filepath), 'parents': [month_folder_id]}
        mimetype = 'application/pdf' if filepath.lower().endswith('.pdf') else 'text/plain'
        media = MediaFileUpload(filepath, mimetype=mimetype)
        result = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,webViewLink,name'
        ).execute()

        logging.info(f"Uploaded: {result.get('name')}")
        logging.info(f"Link: {result.get('webViewLink')}")
        return result.get('webViewLink')

    except Exception as e:
        logging.error(f"Failed to upload to Drive: {e}")
        return None


def send_gmail_api_email(gmail_service, circular_data, circular_drive_link, checklist_drive_link=None):
    """Sends an email using the Gmail API with an HTML body and footer."""
    logging.info("Sending email notification with HTML content...")
    try:
        msg = MIMEMultipart('alternative')
        msg['To'] = ", ".join(RECIPIENTS)
        msg['From'] = SENDER_EMAIL
        msg['Subject'] = f"New RBI Circular Released: {circular_data['circular_number']}"

        checklist_html = ""
        checklist_text = ""
        if checklist_drive_link:
            checklist_html = f"""<p>You can also view the compliance checklist here:<br>
            <a href="{checklist_drive_link}">{checklist_drive_link}</a></p>"""
            checklist_text = f"""
            You can also view the compliance checklist here:
            {checklist_drive_link}
            """

        # Plain text version for compatibility
        text_body = f"""
        Hello Team,
        A new RBI circular has been published.

        Circular Number: {circular_data['circular_number']}
        Date: {circular_data['date']}
        Subject: {circular_data['subject']}

        You can view the circular directly on Google Drive here:
        {circular_drive_link}

        {checklist_text}


        """

        # HTML version with a proper footer
        html_body = f"""
        <html>
          <body>
            <p>Hello Team,</p>
            <p>A new RBI circular has been published.</p>
            <p><b>Circular Number:</b> {circular_data['circular_number']}<br>
            <b>Date:</b> {circular_data['date']}<br>
            <b>Subject:</b> {circular_data['subject']}</p>
            <p>You can view the circular directly on Google Drive here:<br>
            <a href="{circular_drive_link}">{circular_drive_link}</a></p>
            {checklist_html}
            <p style="margin-top: 20px;">
          <strong>Regards</strong><br>
          <span style="color: #2b2b99;"><strong>Your-Name</strong></span><br>
          <span style="color: #2b2b99;"><strong>Your-Designation</strong></span><br>
        </p>

            <hr style="margin-top: 20px; border: 0; height: 1px; background: #ccc;">

          </body>
        </html>
        """

        part1 = MIMEText(text_body, 'plain')
        part2 = MIMEText(html_body, 'html')

        msg.attach(part1)
        msg.attach(part2)

        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        message = gmail_service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()

        logging.info("Email sent successfully with HTML footer.")
        return message

    except HttpError as error:
        logging.error(f'An error occurred with the Gmail API: {error}')
        return None
    except Exception as e:
        logging.error(f"Failed to send email: {e}")
        return None

def get_last_circular_id():
    """Reads the last processed circular ID from a file."""
    if os.path.exists(LAST_CIRCULAR_FILE):
        with open(LAST_CIRCULAR_FILE, 'r') as f:
            return f.read().strip()
    return None


def set_last_circular_id(circular_id):
    """Writes the new circular ID to the file."""
    with open(LAST_CIRCULAR_FILE, 'w') as f:
        f.write(circular_id)
    logging.info(f"Updated last circular ID to: {circular_id}")


def main():
    """Main function to run the automated workflow."""
    logging.info("Starting RBI Circular Downloader...")

    try:
        # Step 1: Check for a new circular
        last_circular_id = get_last_circular_id()
        logging.info(f"Last processed circular ID: {last_circular_id}")

        latest_circular = get_latest_circular_info()

        if not latest_circular:
            logging.error("Could not fetch the latest circular information. Exiting.")
            return

        current_circular_id = latest_circular['circular_number']

        if current_circular_id == last_circular_id:
            logging.info(
                f"No new circular found. The latest circular ({current_circular_id}) has already been processed.")
            return

        logging.info(f"New circular detected: {current_circular_id} - {latest_circular['subject']}")

        # Step 2: Get PDF link or HTML content
        pdf_url, html_content = get_pdf_from_circular_page(latest_circular['url'])

        local_filepath = None
        circular_content = None

        # Step 3: Handle different types of content (PDF or HTML)
        if pdf_url and pdf_url != "HTML_ONLY":
            local_filepath = download_pdf(pdf_url)
            if local_filepath:
                try:
                    with pdfplumber.open(local_filepath) as pdf:
                        circular_content = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
                except Exception as e:
                    logging.warning(f"Failed to extract text from PDF for checklist generation: {e}")
                    circular_content = None

        elif pdf_url == "HTML_ONLY":
            logging.info("This circular is HTML-only. Creating a PDF from the page content.")
            local_filepath = create_pdf_from_html_content(latest_circular, html_content)
            circular_content = html_content
        else:
            logging.error("Failed to find or generate a circular document.")
            return

        if not local_filepath:
            logging.error("Failed to process the circular document. Exiting.")
            return

        # Step 4: Authenticate with Google APIs
        logging.info("Authenticating with Google APIs...")
        if not os.path.exists('credentials.json'):
            logging.warning("credentials.json not found. Skipping Google Drive upload and email.")
            return

        creds = authenticate_google_apis()
        if not creds:
            logging.error("Authentication with Google APIs failed. Exiting.")
            return

        drive_service = build('drive', 'v3', credentials=creds)
        gmail_service = build('gmail', 'v1', credentials=creds)

        # Step 5: Upload the circular to Google Drive
        circular_drive_link = upload_drive(local_filepath, drive_service, rbi_folder_id=RBI_FOLDER_ID)
        if not circular_drive_link:
            logging.error("Failed to upload circular to Google Drive. Exiting.")
            return

        # Step 6: Generate and upload the checklist
        checklist_drive_link = None
        if circular_content:
            checklist_text = generate_checklist_from_text(circular_content)
            if checklist_text:
                checklist_filepath = create_checklist_file(checklist_text, latest_circular)
                if checklist_filepath:
                    checklist_drive_link = upload_drive(checklist_filepath, drive_service, rbi_folder_id=RBI_FOLDER_ID)

        # Step 7: Send email notification
        send_gmail_api_email(gmail_service, latest_circular, circular_drive_link, checklist_drive_link)

        # Step 8: Update the last processed circular ID
        set_last_circular_id(current_circular_id)

        logging.info("Process completed successfully!")

    except Exception as e:
        logging.critical(f"An unhandled exception occurred in the main process: {e}", exc_info=True)


if __name__ == "__main__":
    main()