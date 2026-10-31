#!/usr/bin/env python3
"""Small, permission-aware Geograph API smoke test for Lost in London.

Run ONLY with GEOGRAPH_API_KEY configured in the environment.
No scraping, image downloads, catalogue construction or file writes.
Never print the key or a URL containing it.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = "https://api.geograph.org.uk/syndicator.php"
LOCATIONS = [
    ("Central London", 51.5074, -0.1278),
    ("South London", 51.4627, -0.1145),
]
UA = "LostInLondon-API-Pilot/0.1 (https://github.com/jah1979/LostInLondon)"


def summarise(name, payload):
    if isinstance(payload, list):
        entries = payload
        print(f"{name}: JSON array returned; {len(entries)} items")
    elif isinstance(payload, dict):
        print(f"{name}: JSON object keys: {', '.join(list(payload.keys())[:12])}")
        entries = []
        for field in ("items", "item", "results", "photos", "images", "entries"):
            value = payload.get(field)
            if isinstance(value, list):
                entries = value
                break
            if isinstance(value, dict):
                entries = [value]
                break
        if not entries and isinstance(payload.get("channel"), dict):
            channel = payload["channel"]
            value = channel.get("item") or channel.get("items")
            entries = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
        print(f"{name}: {len(entries)} recognisable item(s)")
    else:
        raise ValueError("Unsupported JSON response type")

    # Print field names only: no image URL, response body, or key-bearing URL.
    if entries and isinstance(entries[0], dict):
        print(f"{name}: sample field names: {', '.join(list(entries[0].keys())[:15])}")
    return bool(entries)


def test_location(name, lat, lon, key):
    params = {
        "key": key, "format": "JSON", "location": f"{lat},{lon}",
        "distance": "3", "perpage": "5",
    }
    request = urllib.request.Request(
        ENDPOINT + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": UA, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            print(f"{name}: HTTP {response.status}, type {response.headers.get('Content-Type', 'unknown')}")
            data = response.read(2_000_001)
            if len(data) > 2_000_000:
                raise ValueError("API response unexpectedly large")
            payload = json.loads(data)
        return summarise(name, payload)
    except urllib.error.HTTPError as error:
        print(f"{name}: Geograph API HTTP {error.code}", file=sys.stderr)
    except urllib.error.URLError:
        print(f"{name}: Geograph API network connection failed", file=sys.stderr)
    except ValueError:
        print(f"{name}: Invalid or unexpected API JSON response", file=sys.stderr)
    return False


def main():
    key = os.environ.get("GEOGRAPH_API_KEY", "").strip()
    if not key:
        print("Missing repository secret GEOGRAPH_API_KEY.", file=sys.stderr)
        return 2
    success = False
    for index, (name, lat, lon) in enumerate(LOCATIONS):
        if index:
            time.sleep(2)
        success = test_location(name, lat, lon, key) or success
    if not success:
        print("API pilot inconclusive: no recognisable photo records.", file=sys.stderr)
        return 1
    print("Geograph metadata pilot succeeded. No photographs downloaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
