"""
Send follow-up emails 48 hours after initial outreach.

Reads from Google Sheet, finds people emailed 48+ hours ago with no response,
sends "Were you able to see the above?" as a reply in the same Gmail thread.

Usage: python send_followups.py [--dry-run]
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.expanduser("~/.claude/skills/apollo-enrichment/scripts"))
from gmail_client import GmailClient

SHEET_ID = "1JvQrDO8To0h8WFcPNrTFLS46jze2zeTAMNc8cjj11eI"
FOLLOWUP_BODY = "Hi {name},<br><br>Were you able to see the above?<br><br>Calvin"
DRY_RUN = "--dry-run" in sys.argv


def read_sheet(tab, range_):
    result = subprocess.run(
        [
            "gws",
            "sheets",
            "+read",
            "--spreadsheet",
            SHEET_ID,
            "--range",
            f"'{tab}'!{range_}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return {"values": []}
    # Filter out gws warnings from stderr
    return json.loads(result.stdout)


def update_sheet(tab, range_, values):
    params = json.dumps(
        {
            "spreadsheetId": SHEET_ID,
            "range": f"'{tab}'!{range_}",
            "valueInputOption": "USER_ENTERED",
        }
    )
    body = json.dumps({"values": values})
    subprocess.run(
        [
            "gws",
            "sheets",
            "spreadsheets",
            "values",
            "update",
            "--params",
            params,
            "--json",
            body,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )


def get_prospects_needing_followup():
    """Find people emailed 48+ hours ago with no response and no follow-up yet."""
    data = read_sheet("Prospect Tracker", "A1:Z500")
    rows = data.get("values", [])
    if len(rows) < 2:
        return []

    headers = rows[0]

    def col(name):
        try:
            return headers.index(name)
        except ValueError:
            return None

    name_col = col("Leader Name")
    date_sent_col = col("Date Sent")
    response_col = col("Response")
    notes_col = col("Notes")

    if date_sent_col is None or name_col is None:
        print("Missing required columns")
        return []

    now = datetime.now()
    cutoff = now - timedelta(hours=48)
    prospects = []

    for i, row in enumerate(rows[1:], start=2):
        row = row + [""] * (len(headers) - len(row))
        name = row[name_col]
        date_sent = row[date_sent_col]
        response = row[response_col] if response_col is not None else ""
        notes = row[notes_col] if notes_col is not None else ""

        if not date_sent or not name:
            continue
        if response:
            continue
        if "follow-up sent" in notes.lower():
            continue

        # Parse date
        try:
            sent_date = datetime.strptime(date_sent.strip(), "%m/%d/%Y")
        except ValueError:
            try:
                sent_date = datetime.strptime(date_sent.strip(), "%Y-%m-%d")
            except ValueError:
                continue

        if sent_date <= cutoff:
            prospects.append(
                {
                    "name": name,
                    "first_name": name.split()[0],
                    "date_sent": date_sent,
                    "row": i,
                    "notes_col_letter": chr(65 + notes_col)
                    if notes_col is not None and notes_col < 26
                    else None,
                }
            )

    return prospects


def find_thread_for_recipient(gmail, name):
    """Search Gmail sent folder for the original email to this person."""
    query = f"in:sent to:{name.split()[0]} from:me"
    try:
        results = (
            gmail.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=5)
            .execute()
        )
        messages = results.get("messages", [])
        if messages:
            msg = (
                gmail.service.users()
                .messages()
                .get(
                    userId="me",
                    id=messages[0]["id"],
                    format="metadata",
                    metadataHeaders=["To", "Subject"],
                )
                .execute()
            )
            thread_id = msg.get("threadId")
            subject = ""
            to_addr = ""
            for h in msg.get("payload", {}).get("headers", []):
                if h["name"] == "Subject":
                    subject = h["value"]
                if h["name"] == "To":
                    to_addr = h["value"]
            return {
                "thread_id": thread_id,
                "message_id": msg["id"],
                "subject": subject,
                "to": to_addr,
            }
    except Exception as e:
        print(f"  Gmail search failed: {e}")
    return None


def main():
    # Check send window: 8am - 7:30pm PST
    from datetime import timezone

    pst = timezone(timedelta(hours=-7))
    now_pst = datetime.now(pst)
    if not (8 <= now_pst.hour < 19 or (now_pst.hour == 19 and now_pst.minute <= 30)):
        print(f"Outside send window ({now_pst.strftime('%H:%M')} PST). Exiting.")
        return

    prospects = get_prospects_needing_followup()
    print(f"Found {len(prospects)} prospects needing follow-up")

    if not prospects:
        return

    if DRY_RUN:
        for p in prospects:
            print(f"  [DRY RUN] Would follow up: {p['name']} (sent {p['date_sent']})")
        return

    gmail = GmailClient()
    sent = 0

    for p in prospects:
        print(f"\n{p['name']} (sent {p['date_sent']})")

        # Find the original thread
        thread = find_thread_for_recipient(gmail, p["name"])
        if not thread:
            print("  Could not find original email thread, skipping")
            continue

        print(f"  Found thread: {thread['subject']} -> {thread['to']}")

        # Send follow-up as reply in same thread
        body_html = FOLLOWUP_BODY.format(name=p["first_name"])
        import base64
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        msg = MIMEMultipart("alternative")
        msg["To"] = thread["to"]
        msg["Subject"] = "Re: " + thread["subject"]
        msg["In-Reply-To"] = thread["message_id"]
        msg["References"] = thread["message_id"]
        msg.attach(
            MIMEText(body_html.replace("<br>", "\n").replace("&amp;", "&"), "plain")
        )
        msg.attach(MIMEText(body_html, "html"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        try:
            result = (
                gmail.service.users()
                .messages()
                .send(
                    userId="me",
                    body={"raw": raw, "threadId": thread["thread_id"]},
                )
                .execute()
            )
            print(f"  Sent follow-up (msg: {result['id']})")
            sent += 1

            # Mark in sheet
            if p["notes_col_letter"]:
                current_notes = ""  # Could read existing but keep simple
                update_sheet(
                    "Prospect Tracker",
                    f"{p['notes_col_letter']}{p['row']}",
                    [["Follow-up sent " + now_pst.strftime("%m/%d/%Y")]],
                )
        except Exception as e:
            print(f"  Send failed: {e}")

    print(f"\nDone. Sent {sent} follow-ups.")


if __name__ == "__main__":
    main()
