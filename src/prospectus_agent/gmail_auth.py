"""One-time Gmail OAuth setup: obtain the refresh token for `--deliver --live`.

Run this ONCE after creating an OAuth **Desktop** client for an *Internal* app on your
Google Workspace (Google Cloud Console → APIs & Services → Credentials). It opens a
browser for consent, then prints the three values to paste into `.env`.

Requires the Gmail libraries: `pip install '.[gmail]'`.

    python -m prospectus_agent.gmail_auth --client-id XXX --client-secret YYY

Scopes requested: gmail.send (send) + gmail.settings.basic (read your signature).
"""
from __future__ import annotations

import argparse
import sys

from prospectus_agent import send  # for GMAIL_SCOPES (single source of truth)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="prospectus_agent.gmail_auth",
                                     description="One-time Gmail OAuth setup for --deliver.")
    parser.add_argument("--client-id", required=True, help="OAuth client ID (Desktop app)")
    parser.add_argument("--client-secret", required=True, help="OAuth client secret")
    args = parser.parse_args(argv)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Gmail libraries not installed — run `pip install '.[gmail]'` first.")
        return 1

    flow = InstalledAppFlow.from_client_config(
        {"installed": {
            "client_id": args.client_id,
            "client_secret": args.client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }},
        scopes=send.GMAIL_SCOPES,
    )
    creds = flow.run_local_server(port=0)  # opens a browser for consent
    if not creds.refresh_token:
        print("No refresh token returned. Revoke prior access and retry with a fresh consent.")
        return 1

    print("\n✓ Authorized. Add these to your .env:\n")
    print(f"GMAIL_CLIENT_ID={args.client_id}")
    print(f"GMAIL_CLIENT_SECRET={args.client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
