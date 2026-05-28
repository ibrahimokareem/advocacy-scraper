# UNiDAYS Sheets Scraper

This is an automated Playwright scraper that reads partner URLs from a Google Sheet, extracts data, and writes the results back to the Sheet. It's designed to run on a daily schedule using GitHub Actions.

## Setup Instructions

### 1. Google Sheets Setup
1. Create a new Google Sheet.
2. In **Column A**, put the UNiDAYS partner URLs (start from row 2, leave row 1 for header).
3. **Important:** Share the Google Sheet with your Service Account email address. Give it **Editor** access.
4. Note your Google Sheet ID (it's the long string of characters in the Sheet URL between `/d/` and `/edit`).

### 2. Local Testing & Discovery Crawler

Since UNiDAYS has over 54,000 partner URLs globally, we have a one-time "Discovery Crawler" that can run locally on your machine to find all the URLs that actually contain the target data and push them to your Google Sheet.

1. Ensure your `credentials.json` is in this folder.
2. Create a file named `.env` in this directory and add your Sheet ID:
   ```
   GOOGLE_SHEET_ID=your_sheet_id_here
   ```
3. Set up a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   playwright install chromium
   ```

**To run the One-Time Discovery Crawler:**
```bash
python discovery_crawler.py
```
> **Note:** This process checks all 54,000 URLs and could take 24-48 hours. It automatically saves its progress every 50 URLs. You can press `Ctrl+C` to pause it at any time, and when you run it again, it will pick up exactly where it left off! Once it checks all URLs, it will push the valid ones to your Google Sheet.

**To run the Daily Scraper manually:**
```bash
python scraper.py
```

### 3. GitHub Actions Setup
When you push this code to your GitHub repository, you need to configure the Action:
1. Go to your GitHub Repository -> **Settings** -> **Secrets and variables** -> **Actions**.
2. Add a new repository secret named `GOOGLE_SHEET_ID` with your Sheet ID.
3. Add a new repository secret named `GOOGLE_CREDENTIALS` and paste the *entire* contents of your `credentials.json` file into it.

The daily scraper will then run automatically every day at 08:00 UTC, using the URLs you discovered using the local crawler!
# advocacy-scraper
