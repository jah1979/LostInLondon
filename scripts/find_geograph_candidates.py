#!/usr/bin/env python3
"""Find small, London-wide sample of actual Geograph photo *metadata* for review.

This runs on GitHub Actions with GEOGRAPH_API_KEY; no secret is embedded in
public code, no images are downloaded and the live game is never updated.
Read-only small-scale API use: 12 places x 6 items, 2 seconds between calls.
Bulk catalogue work should use Geograph's separately approved data dumps.
"""
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from validate_geograph_london import (
    SAMPLE_POINTS, MAX_ITEMS, classify, query_point, year_from_capture,
)

OUT = Path("geograph-candidate-review")
COLUMNS = [
    "sourceId", "title", "centreId", "borough", "area", "lat", "lon",
    "imageTaken", "submissionDate", "author", "licence", "sourceUrl", "thumbUrl",
    "coordinateCheck", "envelopeCheck", "guideCheck", "captureYearCheck",
    "authorCheck", "licenceCheck", "sourceCheck", "thumbnailCheck",
    "precision", "officialGeo", "dateStatus", "rightsStatus",
    "uniqueStatus", "decision", "flags", "notes",
]
# These are geographic sample-centre labels, not authoritative point-in-borough
# assignments. A returned photo may lie in a neighbouring borough.
CENTRE_BOROUGH = {
    "Central / Westminster": "Westminster",
    "Inner north / Hackney": "Hackney",
    "Inner south / Wandsworth": "Wandsworth",
    "Inner southeast / Greenwich": "Greenwich",
    "Far northwest / Harrow": "Harrow",
    "Far north / Enfield": "Enfield",
    "Northwest / Barnet": "Barnet",
    "Far west / Hillingdon": "Hillingdon",
    "Southwest / Kingston": "Kingston upon Thames",
    "Far south / Croydon": "Croydon",
    "Outer southeast / Bexley": "Bexley",
    "Far east / Havering": "Havering",
}

def safe_url(value):
    if not isinstance(value, str):
        return ""
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return ""
    # Never retain any query tokens, credentials, fragments, or non-HTTPS URL.
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return ""
    # Only recognise original Geograph or approved image content domains.
    if parsed.hostname not in ("www.geograph.org.uk", "geograph.org.uk",
                                "images.geograph.org.uk", "s0.geograph.org.uk",
                                "s1.geograph.org.uk", "s2.geograph.org.uk",
                                "s3.geograph.org.uk", "api.geograph.org.uk"):
        return ""
    return parsed._replace(query="", fragment="").geturl()

def photo_id(item):
    val = item.get("guid")
    if isinstance(val, (str, int)) and str(val).strip():
        # For Geograph, a GUID may be an image URL or opaque ID.
        return str(val).strip()[:160]
    link = safe_url(item.get("link"))
    match = re.search(r"/photo/(\d+)", link)
    return match.group(1) if match else link

def text(value, limit=240):
    if value is None:
        return ""
    return str(value).strip().replace("\r", " ").replace("\n", " ")[:limit]

def as_record(item, label, region):
    flags = classify(item)
    sid = photo_id(item)
    original = safe_url(item.get("link")) or safe_url(item.get("source"))
    # Thumbnail URL is a *reference only*; the review UI will not load/hotlink
    # Geograph images. Hosting is a separate, permission-aware phase.
    thumb = safe_url(item.get("thumb"))
    taken = text(item.get("imageTaken"), 80)
    submitted = text(item.get("date"), 80)
    realname = text(item.get("realname") or "", 160)
    api_author = text(item.get("author"), 160)
    author = realname or api_author
    notes = [
        "Imported Geograph API candidate; not individually reviewed.",
        "Photo point may be a 1 km grid-square centroid; confirm camera/subject precision.",
        "London guide is approximate; check against authoritative borough boundary.",
        "Licence field ≠ verified image-specific reuse/attribution requirements.",
        "Sample-centre borough is not an assigned photograph borough.",
        "Photographer's realname needs confirmation" if not realname else "Geograph realname field present.",
    ]
    if not flags["dated"]:
        notes.append("Original capture date missing or ambiguous; Where + When not yet eligible.")
    if not flags["within_guide"]:
        notes.append("Outside approximate guide: requires geographic verification.")
    if not original:
        notes.append("Source URL unavailable or failed host validation.")
    return {
        "sourceId": sid,
        "title": text(item.get("title") or "Untitled", 180),
        "centreId": label,
        # Do not assign a photo to a borough without polygon spatial join.
        "borough": "", "area": region,
        "lat": item.get("lat", ""), "lon": item.get("long", ""),
        "imageTaken": taken, "submissionDate": submitted,
        "author": author, "licence": text(item.get("licence"), 100),
        "sourceUrl": original, "thumbUrl": thumb,
        "coordinateCheck": bool(flags["coordinates"]),
        "envelopeCheck": bool(flags["within_envelope"]),
        "guideCheck": bool(flags["within_guide"]),
        "captureYearCheck": bool(flags["dated"]),
        "authorCheck": bool(flags["author"]),
        "licenceCheck": bool(flags["licence"]),
        "sourceCheck": bool(flags["source"] and original),
        "thumbnailCheck": bool(flags["thumbnail"] and thumb),
        "precision": "unknown", "officialGeo": "unknown",
        "dateStatus": "unknown", "rightsStatus": "unknown",
        "uniqueStatus": "unique-in-this-batch", "decision": "unreviewed",
        "flags": "grid-centroid-unverified;boundary-approximate;reuse-rights-unverified",
        "notes": " ".join(notes),
    }

def main():
    key = os.environ.get("GEOGRAPH_API_KEY", "").strip()
    if not key:
        print("Missing GitHub Actions secret GEOGRAPH_API_KEY.", file=sys.stderr)
        return 2
    OUT.mkdir(exist_ok=True)
    seen = set()
    records = []
    per_area = []
    failures = 0
    for index, (label, region, lat, lon) in enumerate(SAMPLE_POINTS, start=1):
        if index > 1:
            time.sleep(2)
        items, error = query_point(key, label, lat, lon)
        if error:
            failures += 1
        added = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            rec = as_record(item, label, region)
            # Only actual image metadata with a stable id enters the register.
            if not rec["sourceId"]:
                continue
            unique_key = rec["sourceId"]
            if unique_key in seen:
                continue
            seen.add(unique_key)
            records.append(rec)
            added += 1
        per_area.append({"sample":label,"region":region,"returned":len(items),
                         "unique_new":added,"error":error})
        print(f"{index:02d}/{len(SAMPLE_POINTS)} {label}: {len(items)} returned, "
              f"{added} unique metadata records" +
              (f", error: {error}" if error else ""), flush=True)

    if not records:
        print("No photo candidates; no output made.", file=sys.stderr)
        return 1

    with (OUT / "candidate-records.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    (OUT / "candidate-records.json").write_text(
        json.dumps(records, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    summary = {
        "generated_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method":"12 modest, location-based Geograph Syndicator API requests",
        "total_unique":len(records),"sample_count":len(SAMPLE_POINTS),
        "failed_requests":failures,
        "checks": {k:sum(bool(r[k]) for r in records) for k in (
            "coordinateCheck","envelopeCheck","guideCheck","captureYearCheck",
            "authorCheck","licenceCheck","sourceCheck","thumbnailCheck")},
        "areas":per_area,
        "cautions":[
            "Metadata sourced from Geograph API, not visually vetted individual photographs.",
            "Geograph image URLs are not downloaded/hotlinked by the review workspace.",
            "Coordinates may be grid-square centroids; verify position precision.",
            "Approximate Greater London guide is a screen, not authoritative borough geometry.",
            "Licence present does not itself verify per-image reuse rights.",
            "author may be a username until realname is checked against complete metadata.",
            "The reported borough relates only to the search centre, never an assigned photo borough.",
        ],
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    with (OUT / "README.txt").open("w",encoding="utf-8") as stream:
        stream.write("REAL Geograph photo metadata for London review.\n")
        stream.write("Import candidate-records.csv (or .json) into London Metadata Review.\n")
        stream.write("Use original Geograph page links for visual inspection.\n")
        stream.write("DO NOT treat coordinates, dates, licence fields or image rights as individually verified.\n")
        stream.write("No images were downloaded or served by this export.\n")
    print("Prepared:",len(records),"unique candidates;",
          summary["checks"]["captureYearCheck"],"with parseable capture year;",
          failures,"failed requests.",flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
