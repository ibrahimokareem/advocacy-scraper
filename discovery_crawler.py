import os
import json
import time
import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from tqdm import tqdm

load_dotenv()

PROGRESS_FILE = "progress.json"

def fetch_all_sitemap_urls():
    sitemap_url = "https://www.myunidays.com/sitemap-partners.xml"
    print(f"Fetching sitemap from {sitemap_url}...")
    
    response = requests.get(sitemap_url)
    response.raise_for_status()
    
    root = ET.fromstring(response.content)
    namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    
    discovered_urls = []
    for url in root.findall('ns:url/ns:loc', namespace):
        loc = url.text
        if loc:
            discovered_urls.append(loc)
            
    print(f"Discovered {len(discovered_urls)} total URLs from sitemap.")
    return discovered_urls

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    return {"checked": [], "valid": []}

def save_progress(progress):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f)

def push_to_sheets(valid_urls):
    print("Pushing valid URLs to Google Sheet...")
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    creds_json_str = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_json_str:
        creds_dict = json.loads(creds_json_str)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
        if not os.path.exists(creds_file):
            raise FileNotFoundError("Credentials not found. Please setup credentials.json.")
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)

    client = gspread.authorize(creds)
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise ValueError("Please set the GOOGLE_SHEET_ID environment variable.")

    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.sheet1

    # Overwrite column A with the new list
    cell_list = [gspread.Cell(row=1, col=1, value="Partner URLs")]
    for i, url in enumerate(valid_urls):
        cell_list.append(gspread.Cell(row=i+2, col=1, value=url))
        
    worksheet.update_cells(cell_list)
    print("Successfully updated Google Sheet with valid URLs!")


def main():
    print("=== UNiDAYS Discovery Crawler ===")
    all_urls = fetch_all_sitemap_urls()
    progress = load_progress()
    
    checked_set = set(progress["checked"])
    urls_to_check = [u for u in all_urls if u not in checked_set]
    
    print(f"Previously checked: {len(checked_set)}")
    print(f"Valid found so far: {len(progress['valid'])}")
    print(f"URLs remaining to check: {len(urls_to_check)}")
    
    if not urls_to_check:
        print("All URLs have been checked! Pushing to sheets...")
        push_to_sheets(progress["valid"])
        return

    print("Starting Playwright crawler... (Press Ctrl+C to pause and save state)")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        context.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_())
        
        page = context.new_page()
        
        try:
            for i, url in enumerate(tqdm(urls_to_check, desc="Crawling URLs")):
                try:
                    # Very short timeout, if it doesn't load quickly, skip it
                    page.goto(url, timeout=10000)
                    
                    # Target element
                    selector = ".mui-6sbqm6"
                    try:
                        page.wait_for_selector(selector, timeout=2000)
                        progress["valid"].append(url)
                    except:
                        pass # Element not found on this page
                        
                except Exception as e:
                    pass # Timeout or other network error
                    
                progress["checked"].append(url)
                
                # Save progress every 50 URLs
                if (i + 1) % 50 == 0:
                    save_progress(progress)
                    
                # 1 second delay to avoid rate limiting
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\nPaused by user. Saving progress...")
        finally:
            save_progress(progress)
            browser.close()
            
    print(f"\nFinished crawling session. Total valid URLs found: {len(progress['valid'])}")
    
    if len(progress["checked"]) == len(all_urls):
        push_to_sheets(progress["valid"])
    else:
        print("Run the script again to continue checking the remaining URLs.")

if __name__ == "__main__":
    main()
