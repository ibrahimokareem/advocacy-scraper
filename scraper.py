import os
import json
import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Load environment variables from .env if present
load_dotenv()

# 1. Setup Google Sheets Authentication
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

creds_json_str = os.environ.get("GOOGLE_CREDENTIALS")
if creds_json_str:
    creds_dict = json.loads(creds_json_str)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
else:
    # Fallback to local file for testing
    creds_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    if not os.path.exists(creds_file):
        raise FileNotFoundError(f"Credentials not found at {creds_file} and GOOGLE_CREDENTIALS env var not set.")
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)

client = gspread.authorize(creds)

# 2. Open the Spreadsheet
sheet_id = os.environ.get("GOOGLE_SHEET_ID")
if not sheet_id:
    raise ValueError("Please set the GOOGLE_SHEET_ID environment variable.")

print(f"Connecting to Google Sheet ID: {sheet_id}")
spreadsheet = client.open_by_key(sheet_id)
worksheet = spreadsheet.sheet1

# 3. Read the URLs dynamically by finding the "Partner URLs" column
print("Looking for the 'Partner URLs' column...")
first_row = worksheet.row_values(1)

try:
    # .index() is 0-based, gspread columns are 1-based
    url_col_index = first_row.index("Partner URLs") + 1
except ValueError:
    print("Error: Could not find 'Partner URLs' header in the first row. Exiting.")
    exit(1)

print(f"Reading URLs from Column {url_col_index}...")
all_url_col = worksheet.col_values(url_col_index)
if len(all_url_col) <= 1:
    print("No URLs found below the header. Exiting.")
    exit(0)
    
urls = all_url_col[1:] # Skip row 1 (Header)

# 4. Scrape Data using Playwright
today_date = datetime.date.today().strftime("%Y-%m-%d")
scraped_data = []

print(f"Starting scrape for {len(urls)} URLs...")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    # Block images/media to speed up the scraper since we just need text
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    context.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_())
    
    page = context.new_page()
    
    for url in urls:
        if not url.strip():
            scraped_data.append("")
            continue
            
        print(f"Scraping: {url}")
        try:
            page.goto(url, timeout=30000)
            
            # The target data is inside: <span class="MuiBox-root mui-6sbqm6">
            selector = ".mui-6sbqm6"
            page.wait_for_selector(selector, timeout=10000)
            
            # Extract the text
            element = page.locator(selector).first
            raw_text = element.inner_text().strip()
            
            # Clean up formatting differences (e.g. "1.035", "3 077", "68,428") by keeping only digits
            cleaned_text = "".join(filter(str.isdigit, raw_text))
            
            # Convert to integer so Google Sheets recognizes it as a true number
            if cleaned_text:
                text_value = int(cleaned_text)
            else:
                text_value = raw_text
            
            print(f"  -> Found value: {text_value} (raw: {raw_text})")
            scraped_data.append(text_value)
            
        except Exception as e:
            print(f"  -> Error scraping {url}: {e}")
            scraped_data.append("Error")
            
    browser.close()

# 5. Write Data Back to Google Sheets
print("Writing data back to Google Sheet...")

# Find the next empty column
first_row = worksheet.row_values(1)
next_col_index = len(first_row) + 1

# If we've hit the edge of the spreadsheet, add more columns automatically
if next_col_index > worksheet.col_count:
    print(f"Adding a new column to the spreadsheet...")
    worksheet.add_cols(1)

# Prepare the column data to update in batch
cell_list = [gspread.Cell(row=1, col=next_col_index, value=today_date)]

for i, val in enumerate(scraped_data):
    # i+2 because row 1 is header, so data starts at row 2
    cell = gspread.Cell(row=i+2, col=next_col_index, value=val)
    cell_list.append(cell)

worksheet.update_cells(cell_list)

print("Successfully updated Google Sheet!")
