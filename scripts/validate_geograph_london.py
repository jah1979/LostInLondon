#!/usr/bin/env python3
"""Small, read-only Geograph metadata-quality pilot across Greater London.

Do not scrape Geograph or download, hotlink, mirror or republish photographs.
Queries the documented Geograph Syndicator JSON API using a private GitHub
Actions secret. Generates only aggregated, non-identifying quality metrics.
For larger catalogues use official Geograph bulk metadata with permission.
"""
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ENDPOINT = "https://api.geograph.org.uk/syndicator.php"
USER_AGENT = "LostInLondon-Metadata-Pilot/0.2 (https://github.com/jah1979/LostInLondon)"
# Purposefully STRATIFIED across the city, not an exhaustive borough inventory.
# 12 requests x at most 6 results; the public API is not used for bulk exports.
SAMPLE_POINTS = (
    ("Central / Westminster", "central", 51.502, -0.126),
    ("Inner north / Hackney", "north", 51.545, -0.056),
    ("Inner south / Wandsworth", "south", 51.457, -0.194),
    ("Inner southeast / Greenwich", "southeast", 51.483, -0.008),
    ("Far northwest / Harrow", "northwest", 51.579, -0.339),
    ("Far north / Enfield", "north", 51.652, -0.080),
    ("Northwest / Barnet", "northwest", 51.625, -0.152),
    ("Far west / Hillingdon", "west", 51.546, -0.478),
    ("Southwest / Kingston", "southwest", 51.412, -0.300),
    ("Far south / Croydon", "south", 51.372, -0.100),
    ("Outer southeast / Bexley", "southeast", 51.455, 0.147),
    ("Far east / Havering", "east", 51.576, 0.184),
)
MAX_ITEMS = 6
# Same *approximate* play envelope as the existing game, not an authoritative
# borough boundary and not proof that a camera is exactly at the listed point.
LONDON_ENVELOPE = (51.25, 51.74, -0.62, 0.42)
LONDON_GUIDE = (
    (51.66,-0.32),(51.69,-0.17),(51.70,-0.05),(51.65,0.08),
    (51.58,0.30),(51.49,0.35),(51.43,0.20),(51.29,0.18),
    (51.28,-0.03),(51.33,-0.17),(51.36,-0.35),(51.44,-0.49),
    (51.54,-0.52),(51.62,-0.39),
)
YEAR_RE = re.compile(r"^(?:(?:[0-3]?\d[-/ ](?:0?[1-9]|1[0-2])[-/ ])|(?:[a-z]{3,9}\s+\d{1,2},?\s+)|(?:\d{1,2}\s+[a-z]{3,9}\s+))?(1[89]\d{2}|20\d{2})(?=$|[-/T\s])", re.I)
UNCERTAIN = re.compile(r"\b(?:circa|approx|unknown|before|after|between|probably)\b|(?:^|[\s,])(?:c\.|ca\.)", re.I)


def inside_guide(lat, lon):
    inside = False
    for i, (y1, x1) in enumerate(LONDON_GUIDE):
        y2, x2 = LONDON_GUIDE[i - 1]
        if (y1 > lat) != (y2 > lat):
            x_hit = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x_hit:
                inside = not inside
    return inside


def get_items(payload):
    if isinstance(payload, dict):
        val = payload.get("items")
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            return [val]
        channel = payload.get("channel")
        if isinstance(channel, dict):
            val = channel.get("item")
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                return [val]
    return []


def year_from_capture(value):
    # imageTaken denotes the capture date; payload.date may be submission date
    # and must never be substituted for the game year.
    if isinstance(value, dict):
        return None
    date_string = str(value or "").strip()
    if not date_string or UNCERTAIN.search(date_string):
        return None
    match = YEAR_RE.match(date_string)
    if not match:
        # The common ISO format YYYY-MM-DD is handled by YEAR_RE; a bare
        # YYYY is also acceptable. Other ambiguous formats are not.
        return None
    year = int(match.group(1))
    return year if 1850 <= year <= datetime.now(timezone.utc).year else None


def as_float(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def classify(item):
    if not isinstance(item, dict):
        return {"coordinates": False, "within_envelope": False,
                "within_guide": False, "dated": False, "author": False,
                "licence": False, "source": False, "thumbnail": False}
    lat, lon = as_float(item.get("lat")), as_float(item.get("long"))
    coordinates = lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180
    inside_box = bool(coordinates and LONDON_ENVELOPE[0] <= lat <= LONDON_ENVELOPE[1]
                      and LONDON_ENVELOPE[2] <= lon <= LONDON_ENVELOPE[3])
    return {
        "coordinates": coordinates,
        "within_envelope": inside_box,
        "within_guide": bool(inside_box and inside_guide(lat, lon)),
        "dated": year_from_capture(item.get("imageTaken")) is not None,
        "author": bool(str(item.get("author") or "").strip()),
        "licence": bool(str(item.get("licence") or "").strip()),
        "source": any(isinstance(item.get(k), str) and item[k].startswith("https://")
                      for k in ("link", "source")),
        "thumbnail": isinstance(item.get("thumb"), str) and item["thumb"].startswith("https://"),
    }


def query_point(key, label, lat, lon):
    url = ENDPOINT + "?" + urllib.parse.urlencode({
        "key": key, "format": "JSON", "location": f"{lat},{lon}",
        "distance": "5", "perpage": str(MAX_ITEMS),
    })
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read(1_000_001)
            if len(body) > 1_000_000:
                raise ValueError("oversized JSON response")
            if response.status != 200:
                raise ValueError("non-200 response")
        return get_items(json.loads(body)), None
    except urllib.error.HTTPError as error:
        # Never print the exception or a URL: both could contain the API key.
        return [], f"HTTP {error.code}"
    except urllib.error.URLError:
        return [], "network error"
    except (ValueError, json.JSONDecodeError):
        return [], "invalid JSON"


def report_for(key):
    areas, observed = [], {}
    requests_failed = 0
    for i, (label, region, lat, lon) in enumerate(SAMPLE_POINTS):
        if i:
            time.sleep(2)  # reasonable rate for a small charity API
        items, error = query_point(key, label, lat, lon)
        if error:
            requests_failed += 1
        metrics = Counter()
        for item in items:
            flags = classify(item)
            metrics.update(k for k, v in flags.items() if v)
            if isinstance(item, dict):
                # Deduplicate only within this run; no IDs or URLs in report.
                unique_key = str(item.get("guid") or item.get("link") or
                                 item.get("source") or (item.get("title"), item.get("lat"), item.get("long")))
                observed.setdefault(unique_key, flags)
        areas.append({
            "sample": label, "region": region,
            "returned": len(items), "error": error,
            "geo": metrics["within_guide"], "dated": metrics["dated"],
            "credited": metrics["author"], "licensed": metrics["licence"],
            "with_source": metrics["source"],
        })
        print(f"{i+1:02d}/{len(SAMPLE_POINTS)} {label}: {len(items)} items; "
              f"within London guide {metrics['within_guide']}; "
              f"dated {metrics['dated']}; licence present {metrics['licence']}"
              + (f"; error {error}" if error else ""), flush=True)

    unique = list(observed.values())
    totals = {k: sum(bool(item[k]) for item in unique)
              for k in ("coordinates", "within_envelope", "within_guide",
                        "dated", "author", "licence", "source", "thumbnail")}
    totals["where_only_candidates"] = sum(item["within_guide"] and item["author"]
                                          and item["licence"] and item["source"] for item in unique)
    totals["where_and_when_candidates"] = sum(item["within_guide"] and item["dated"]
                                              and item["author"] and item["licence"]
                                              and item["source"] for item in unique)
    totals["unique_items"] = len(unique)
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sample_points": len(SAMPLE_POINTS),
        "max_results_per_point": MAX_ITEMS,
        "requests_failed": requests_failed,
        "totals_unique": totals,
        "areas": areas,
        "notes": [
            "12 geographically dispersed sample centres, not all 33 boroughs or a bulk extract.",
            "The in-game Greater London polygon is approximate. Points outside it are review flags, not definitive exclusions.",
            "Reported coordinates may represent grid-square centres rather than camera GPS points; location precision remains unverified.",
            "imageTaken (capture year) is distinct from submission date and may be ambiguous.",
            "Licence presence is not proof of particular reuse terms or image-hosting rights.",
            "No photographs, image URLs, image identifiers, photographer identities or API keys are saved.",
            "No permissions to hotlink or separately host Geograph images are inferred.",
        ],
    }
    return summary


def render_markdown(report):
    total = report["totals_unique"]
    lines = ["# Geograph Greater London metadata pilot",
             "", f"Generated (UTC): {report['generated_at_utc']}",
             "", "**Read-only; no photographs downloaded or republished.**",
             "", "## Unique-record quality checks",
             "", "| Check | Count |", "|---|---:|",
             *[f"| {name.replace('_', ' ').capitalize()} | {count} |"
               for name, count in total.items()],
             "", f"Failed requests: **{report['requests_failed']}** / {report['sample_points']}",
             "", "## Sample coverage",
             "", "| Sample | Returned | Within London guide | Dated | Author | Licence | Error |",
             "|---|---:|---:|---:|---:|---:|---|"]
    for area in report["areas"]:
        lines.append(f"| {area['sample']} | {area['returned']} | {area['geo']} | "
                     f"{area['dated']} | {area['credited']} | {area['licensed']} | "
                     f"{area['error'] or '—'} |")
    lines += ["", "## Qualifications", ""]
    lines += [f"- {note}" for note in report["notes"]]
    return "\n".join(lines) + "\n"


def main():
    key = os.environ.get("GEOGRAPH_API_KEY", "").strip()
    if not key:
        print("Missing GEOGRAPH_API_KEY GitHub Actions secret", file=sys.stderr)
        return 2
    report = report_for(key)
    output = Path(os.environ.get("GEOGRAPH_REPORT_DIR", "geograph-pilot-report"))
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown = render_markdown(report)
    (output / "summary.md").write_text(markdown, encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(markdown)
    print("Metadata report written; no photos or links collected.", flush=True)
    if report["requests_failed"] == report["sample_points"]:
        print("All Geograph queries failed; inspect aggregated errors.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
