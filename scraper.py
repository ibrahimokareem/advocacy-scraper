import os
import json
import datetime
import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Load environment variables from .env if present
load_dotenv()

def fetch_all_sitemap_urls():
    sitemap_url = "https://www.myunidays.com/sitemap-partners.xml"
    print(f"Fetching sitemap from {sitemap_url}...")
    try:
        response = requests.get(sitemap_url)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls = [url.text for url in root.findall('ns:url/ns:loc', namespace) if url.text]
        print(f"Discovered {len(urls)} total URLs from sitemap.")
        return urls
    except Exception as e:
        print(f"Failed to fetch sitemap: {e}")
        return []

# 1. Setup Google Sheets Authentication
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

creds_json_str = os.environ.get("GOOGLE_CREDENTIALS")
if creds_json_str:
    creds_dict = json.loads(creds_json_str)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
else:
    creds_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
    if not os.path.exists(creds_file):
        raise FileNotFoundError(f"Credentials not found at {creds_file} and GOOGLE_CREDENTIALS env var not set.")
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)

client = gspread.authorize(creds)

sheet_id = os.environ.get("GOOGLE_SHEET_ID")
if not sheet_id:
    raise ValueError("Please set the GOOGLE_SHEET_ID environment variable.")

print(f"Connecting to Google Sheet ID: {sheet_id}")
spreadsheet = client.open_by_key(sheet_id)
worksheet = spreadsheet.sheet1

# Try to connect to the Invalid URLs tab
try:
    invalid_worksheet = spreadsheet.worksheet("Invalid URLs")
except gspread.exceptions.WorksheetNotFound:
    print("Error: Could not find 'Invalid URLs' tab. Please create it.")
    exit(1)

# 2. Read the Valid URLs dynamically
print("Looking for the 'Partner URLs' column in main sheet...")
first_row = worksheet.row_values(1)

# Clean up headers (lowercase and strip spaces) for robust matching
cleaned_headers = [str(header).strip().lower() for header in first_row]

try:
    url_col_index = cleaned_headers.index("partner urls") + 1
except ValueError:
    print(f"Error: Could not find 'Partner URLs' header in the first row. Found headers: {first_row}")
    exit(1)

all_url_col = worksheet.col_values(url_col_index)
valid_urls = all_url_col[1:] if len(all_url_col) > 1 else []

# 3. Read the Invalid URLs
print("Reading 'Invalid URLs' tab...")
all_invalid_col = invalid_worksheet.col_values(1)
if not all_invalid_col:
    invalid_worksheet.update_cell(1, 1, "Invalid URLs")
    invalid_urls = []
else:
    invalid_urls = all_invalid_col[1:] if len(all_invalid_col) > 1 else []

# 4. Mini-Discovery Logic
sitemap_urls = fetch_all_sitemap_urls()
existing_urls = set(valid_urls).union(set(invalid_urls))
new_urls_to_check = [u for u in sitemap_urls if u not in existing_urls]

new_valid = []
new_invalid = []

if new_urls_to_check:
    print(f"Found {len(new_urls_to_check)} brand new URLs in sitemap. Checking them now...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        context.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_())
        page = context.new_page()
        
        for url in new_urls_to_check:
            print(f"Checking new URL: {url}")
            try:
                page.goto(url, timeout=10000)
                selector = ".mui-6sbqm6"
                try:
                    page.wait_for_selector(selector, timeout=5000)
                    new_valid.append(url)
                    print("  -> Valid!")
                except:
                    new_invalid.append(url)
                    print("  -> Invalid (Element not found)")
            except Exception as e:
                new_invalid.append(url)
                print("  -> Invalid (Timeout/Error)")
        browser.close()
        
    # Append new valid URLs to the bottom of the Partner URLs column
    if new_valid:
        print(f"Appending {len(new_valid)} new valid URLs to main sheet...")
        start_row = len(all_url_col) + 1
        cells = [gspread.Cell(row=start_row + i, col=url_col_index, value=u) for i, u in enumerate(new_valid)]
        worksheet.update_cells(cells)
        valid_urls.extend(new_valid)
        
    # Append new invalid URLs to the bottom of Invalid URLs sheet
    if new_invalid:
        print(f"Appending {len(new_invalid)} new invalid URLs to Invalid URLs sheet...")
        start_row = len(all_invalid_col) + 1 if all_invalid_col else 2
        cells = [gspread.Cell(row=start_row + i, col=1, value=u) for i, u in enumerate(new_invalid)]
        invalid_worksheet.update_cells(cells)
else:
    print("No new URLs found in sitemap.")

if not valid_urls:
    print("No valid URLs to scrape. Exiting.")
    exit(0)

# 5. Scrape Data for all Valid URLs
today_date = datetime.date.today().strftime("%Y-%m-%d")
scraped_data = []

print(f"Starting main scrape for {len(valid_urls)} URLs...")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    context.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_())
    page = context.new_page()
    
    for url in valid_urls:
        if not url.strip():
            scraped_data.append("")
            continue
            
        print(f"Scraping: {url}")
        try:
            page.goto(url, timeout=30000)
            selector = ".mui-6sbqm6"
            page.wait_for_selector(selector, timeout=10000)
            
            element = page.locator(selector).first
            raw_text = element.inner_text().strip()
            
            cleaned_text = "".join(filter(str.isdigit, raw_text))
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

# 6. Write Data Back to Google Sheets
print("Writing data back to Google Sheet...")
first_row = worksheet.row_values(1)
next_col_index = len(first_row) + 1

if next_col_index > worksheet.col_count:
    print(f"Adding a new column to the spreadsheet...")
    worksheet.add_cols(1)

cell_list = [gspread.Cell(row=1, col=next_col_index, value=today_date)]
for i, val in enumerate(scraped_data):
    cell = gspread.Cell(row=i+2, col=next_col_index, value=val)
    cell_list.append(cell)

worksheet.update_cells(cell_list)
print("Successfully updated Google Sheet!")
