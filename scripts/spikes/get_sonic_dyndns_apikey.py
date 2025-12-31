#!/usr/bin/env python3
"""
Helper script to obtain Sonic.net DynDNS API credentials.

This script requests API credentials from Sonic.net using your
username and password, then displays them for use in .env configuration.
"""

import getpass
import json
import sys

import requests


def get_api_key(username: str, password: str) -> dict:
    """
    Request API key from Sonic.net DynDNS API.

    Args:
        username: Sonic.net account username
        password: Sonic.net account password

    Returns:
        Dictionary containing userid and apikey
    """
    url = "https://public-api.sonic.net/dyndns/api_key"
    payload = {"username": username, "password": password}

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error requesting API key: {e}", file=sys.stderr)
        sys.exit(1)


def list_api_keys(username: str, password: str) -> dict:
    """
    List existing API keys from Sonic.net DynDNS API.

    Args:
        username: Sonic.net account username
        password: Sonic.net account password

    Returns:
        Dictionary containing list of API keys
    """
    url = "https://public-api.sonic.net/dyndns/list_api_key"
    payload = {"username": username, "password": password}

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error listing API keys: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main function."""
    print("=" * 80)
    print("Sonic.net DynDNS API Credential Helper")
    print("=" * 80)
    print()
    print("This script will help you obtain API credentials for DynDNS.")
    print()

    # Get credentials
    username = input("Enter your Sonic.net username: ").strip()
    password = getpass.getpass("Enter your Sonic.net password: ")

    print()
    print("Choose an option:")
    print("  1. Create new API key")
    print("  2. List existing API keys")
    print()
    choice = input("Enter choice (1 or 2): ").strip()

    print()
    print("Contacting Sonic.net API...")
    print()

    if choice == "1":
        # Create new API key
        result = get_api_key(username, password)

        if result.get("result") == 200:
            print("✅ API key created successfully!")
            print()
            print("=" * 80)
            print("Add these to your .env file:")
            print("=" * 80)
            print()
            print(f'SONIC_DYNDNS_USERID={result.get("userid", "N/A")}')
            print(f'SONIC_DYNDNS_APIKEY={result.get("apikey", "N/A")}')
            print("SONIC_DYNDNS_HOSTNAME=your-hostname.sonic.net")
            print()
            print("=" * 80)
            print()
            print("Next steps:")
            print("  1. Copy the above lines to your .env file")
            print("  2. Replace 'your-hostname.sonic.net' with your actual hostname")
            print("  3. Start the DynDNS service: docker-compose up -d dyndns")
        else:
            print(f"❌ Failed to create API key: {result.get('message', 'Unknown error')}")
            print()
            print("Full response:")
            print(json.dumps(result, indent=2))
            sys.exit(1)

    elif choice == "2":
        # List existing API keys
        result = list_api_keys(username, password)

        if result.get("result") == 200:
            keys = result.get("api_keys", [])
            if keys:
                print(f"✅ Found {len(keys)} existing API key(s):")
                print()
                for i, key in enumerate(keys, 1):
                    print(f"Key {i}:")
                    print(f"  User ID: {key.get('userid', 'N/A')}")
                    print(f"  API Key: {key.get('apikey', 'N/A')}")
                    print(f"  Created: {key.get('created_at', 'N/A')}")
                    print()
            else:
                print("No existing API keys found.")
                print("Choose option 1 to create a new API key.")
        else:
            print(f"❌ Failed to list API keys: {result.get('message', 'Unknown error')}")
            print()
            print("Full response:")
            print(json.dumps(result, indent=2))
            sys.exit(1)

    else:
        print("Invalid choice. Please run the script again.")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print("Cancelled by user.")
        sys.exit(0)
