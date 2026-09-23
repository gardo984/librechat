#!/usr/bin/env python3

"""Refresh COPILOT_BEARER in .env from the long-lived COPILOT_TOKEN.

The GitHub OAuth token (COPILOT_TOKEN) does not expire, but the Copilot bearer
it exchanges for is only valid for ~24 hours. Custom endpoints cannot perform
that exchange themselves, so this script keeps COPILOT_BEARER current.

Usage:
    python3 refresh-copilot-bearer.py [--env-path /path/to/.env]
"""

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

import requests

CLIENT_UA = "GitHubCopilotChat/0.26.7"
EXCHANGE_URL = "https://api.github.com/copilot_internal/v2/token"
BEARER_PREFIX = "COPILOT_BEARER="
TOKEN_PREFIX = "COPILOT_TOKEN="


def read_env(env_path):
    # type: (Path) -> str
    if not env_path.is_file():
        raise SystemExit(f"Environment file not found: {env_path}")
    return env_path.read_text()


def extract(contents, prefix):
    # type: (str, str) -> Optional[str]
    match = re.search(rf"^{re.escape(prefix)}(.*)$", contents, re.MULTILINE)
    return match.group(1).strip() if match else None


def exchange(github_token):
    # type: (str) -> Tuple[str, float]
    response = requests.get(
        EXCHANGE_URL,
        headers={
            "Authorization": f"token {github_token}",
            "User-Agent": CLIENT_UA,
            "Accept": "application/json",
        },
        timeout=30,
    )

    if response.status_code != 200:
        raise SystemExit(
            f"Token exchange failed ({response.status_code}). "
            f"Check that COPILOT_TOKEN is valid and Copilot is active.\n{response.text[:300]}"
        )

    payload = response.json()
    hours = (payload["expires_at"] - time.time()) / 3600
    return payload["token"], hours


def write_bearer(env_path, contents, bearer):
    # type: (Path, str, str) -> None
    line = f"{BEARER_PREFIX}{bearer}"
    if re.search(rf"^{re.escape(BEARER_PREFIX)}.*$", contents, re.MULTILINE):
        updated = re.sub(rf"^{re.escape(BEARER_PREFIX)}.*$", line, contents, flags=re.MULTILINE)
    elif re.search(rf"^{re.escape(TOKEN_PREFIX)}.*$", contents, re.MULTILINE):
        updated = re.sub(
            rf"^({re.escape(TOKEN_PREFIX)}.*)$", rf"\1\n{line}", contents, count=1, flags=re.MULTILINE
        )
    else:
        updated = contents.rstrip("\n") + f"\n{line}\n"

    env_path.write_text(updated)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-path",
        default=str(Path(__file__).resolve().parents[1] / ".env"),
        help="Path to the .env file (defaults to the repo root)",
    )
    args = parser.parse_args()

    env_path = Path(args.env_path)
    contents = read_env(env_path)

    github_token = extract(contents, TOKEN_PREFIX)
    if not github_token:
        raise SystemExit(f"{TOKEN_PREFIX.rstrip('=')} is not set in {env_path}")

    bearer, hours = exchange(github_token)
    write_bearer(env_path, contents, bearer)

    print(f"Updated {BEARER_PREFIX.rstrip('=')} in {env_path}")
    print(f"Bearer valid for ~{hours:.2f} hours")
    print("Restart LibreChat to pick up the new value.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
