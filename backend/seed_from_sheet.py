"""
Seed the database from the Google Sheet prospect tracker.

Usage: python seed_from_sheet.py
"""

import json
import subprocess
import sys

import requests
from dotenv import load_dotenv
import os

load_dotenv()

SPREADSHEET_ID = "1JvQrDO8To0h8WFcPNrTFLS46jze2zeTAMNc8cjj11eI"
RANGE = "A1:Z500"
API_KEY = os.getenv("SWIPE_API_KEY", "")
BASE_URL = os.getenv("SWIPE_BASE_URL", "http://localhost:8000")

# Column mapping (0-indexed)
COL = {
    "company": 0,
    "leader_name": 1,
    "title": 2,
    "location": 3,
    "ai_signal": 4,
    "job_search_url": 5,
    "linkedin_url": 6,
    "icp_score": 16,
    "employee_count": 17,
    "company_summary": 18,
    "ai_signal_analysis": 19,
    "why_trace_fits": 20,
    "recommended_approach": 21,
    "score_breakdown": 22,
}


def read_sheet():
    """Read the Google Sheet using gws CLI."""
    result = subprocess.run(
        [
            "gws",
            "sheets",
            "+read",
            "--spreadsheet",
            SPREADSHEET_ID,
            "--range",
            RANGE,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Failed to read sheet: {result.stderr}")
        sys.exit(1)
    data = json.loads(result.stdout)
    return data.get("values", [])


def get(row, col_name):
    """Safely get a value from a row by column name."""
    idx = COL[col_name]
    if idx < len(row):
        return row[idx].strip()
    return ""


def parse_int(s):
    """Try to parse an integer from a string."""
    try:
        return int(s.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def main():
    print("Reading Google Sheet...")
    rows = read_sheet()
    if len(rows) < 2:
        print("No data rows found")
        return

    headers = rows[0]
    data_rows = rows[1:]
    print(f"Found {len(data_rows)} rows")

    profiles = []
    skipped = 0
    for row in data_rows:
        name = get(row, "leader_name")
        linkedin_url = get(row, "linkedin_url")

        # Skip rows without name or LinkedIn URL
        if not name or not linkedin_url or name == "N/A":
            skipped += 1
            continue

        # Skip search result URLs (not actual profiles)
        if "/search/results/" in linkedin_url:
            skipped += 1
            continue

        profile = {
            "linkedin_url": linkedin_url,
            "name": name,
            "headline": get(row, "title"),
            "company": get(row, "company"),
            "location": get(row, "location"),
            "icp_score": parse_int(get(row, "icp_score")),
            "employee_count": get(row, "employee_count") or None,
            "company_summary": get(row, "company_summary") or None,
            "ai_signal": get(row, "ai_signal") or None,
            "ai_signal_analysis": get(row, "ai_signal_analysis") or None,
            "why_trace_fits": get(row, "why_trace_fits") or None,
            "recommended_approach": get(row, "recommended_approach") or None,
            "score_breakdown": get(row, "score_breakdown") or None,
            "job_search_url": get(row, "job_search_url") or None,
        }
        profiles.append(profile)

    print(f"Parsed {len(profiles)} valid profiles ({skipped} skipped)")

    # Upload in batches of 50
    batch_size = 50
    total_created = 0
    total_dupes = 0
    for i in range(0, len(profiles), batch_size):
        batch = profiles[i : i + batch_size]
        resp = requests.post(
            f"{BASE_URL}/profiles",
            json=batch,
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=30,
        )
        if resp.status_code == 201:
            result = resp.json()
            total_created += result["created"]
            total_dupes += result["duplicates"]
            print(
                f"  Batch {i // batch_size + 1}: {result['created']} created, {result['duplicates']} duplicates"
            )
        else:
            print(
                f"  Batch {i // batch_size + 1} FAILED: {resp.status_code} {resp.text}"
            )

    print(f"\nDone: {total_created} created, {total_dupes} duplicates")


if __name__ == "__main__":
    main()
