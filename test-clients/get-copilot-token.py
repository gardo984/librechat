#!/usr/bin/env python3

"""Device-flow helper that prints a GitHub Copilot OAuth token.

Usage: python3 get-copilot-token.py [--verify]

Prompts you to visit github.com/login/device, approve access, then prints the
resulting token so it can be placed in COPILOT_TOKEN.
"""

import sys
import time

import requests

CLIENT_ID = "01ab8ac9400c4e429b23"
CLIENT_UA = "GitHubCopilotChat/0.26.7"
DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
TOKEN_EXCHANGE_URL = "https://api.github.com/copilot_internal/v2/token"
SCOPE = "read:user"


def request_device_code() -> dict:
    response = requests.post(
        DEVICE_CODE_URL,
        headers={"Accept": "application/json", "User-Agent": CLIENT_UA},
        data={"client_id": CLIENT_ID, "scope": SCOPE},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if "device_code" not in payload:
        raise RuntimeError(f"Unexpected device code response: {payload}")
    return payload


def poll_for_token(device_code: str, interval: int, expires_in: int) -> str:
    deadline = time.time() + expires_in
    while time.time() < deadline:
        response = requests.post(
            ACCESS_TOKEN_URL,
            headers={"Accept": "application/json", "User-Agent": CLIENT_UA},
            data={
                "client_id": CLIENT_ID,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("access_token"):
            return payload["access_token"]

        error = payload.get("error")
        if error == "authorization_pending":
            time.sleep(interval)
            continue
        if error == "slow_down":
            interval += 5
            time.sleep(interval)
            continue
        if error == "expired_token":
            raise RuntimeError("Device code expired; re-run the script.")
        raise RuntimeError(f"Device flow failed: {payload}")

    raise RuntimeError("Timed out waiting for authorization.")


def verify_copilot_access(token: str) -> None:
    response = requests.get(
        TOKEN_EXCHANGE_URL,
        headers={
            "Authorization": f"token {token}",
            "User-Agent": CLIENT_UA,
            "Accept": "application/json",
        },
        timeout=30,
    )
    if response.status_code != 200:
        print(f"\nCopilot exchange failed ({response.status_code}): {response.text}")
        print("Check that an active Copilot subscription is on this account.")
        return

    payload = response.json()
    expires_in = int(payload.get("expires_at", 0)) - int(time.time())
    print(f"\nCopilot access OK. Bearer valid for ~{max(expires_in, 0) // 60} minutes.")
    print(f"API base URL: {payload.get('endpoints', {}).get('api', 'unknown')}")


def main() -> int:
    payload = request_device_code()
    print("Visit:", payload["verification_uri"])
    print("Code: ", payload["user_code"])
    print("\nWaiting for approval (Ctrl-C to cancel)...")

    try:
        token = poll_for_token(
            payload["device_code"],
            int(payload.get("interval", 5)),
            int(payload.get("expires_in", 900)),
        )
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 1

    print("\nCopilot OAuth token:\n")
    print(token)

    if "--verify" in sys.argv:
        verify_copilot_access(token)
    else:
        print("\nRe-run with --verify to confirm Copilot access.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
