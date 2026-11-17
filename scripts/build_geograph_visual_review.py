#!/usr/bin/env python3
"""Geographically distributed London Geograph review candidates with local thumbs.

Uses 33 approximate London authority reference centres in the game, for a
one-time manual QA sample (not a complete or authoritative borough survey).
Queries the Geograph API with a PRIVATE GitHub secret. Downloads only the
supplied thumbnail URLs, under Geograph's confirmed rehosting guidance, and
packages images + attribution for OFFLINE manual review. No public deployment.
"""
import csv
import json
import math
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from validate_geograph_london import classify, query_point, year_from_capture
from find_geograph_candidates import as_record

ROOT=Path(__file__).resolve().parents[1]
OUT=Path("geograph-spread-review")
IMAGES=OUT/"thumbs"
AGENT="LostInLondon-VisualReview/0.1 (https://github.com/jah1979/LostInLondon)"
MIN_SEPARATION_KM=0.45
MAX_PER_CENTRE=3
# Source: 33 approximate authority reference points in app.js.
def sample_centres():
    app=(ROOT/"app.js").read_text(encoding="utf-8")
    m=re.search(r"const AREA_BOROUGHS = (\[.*?\]);",app,re.S)
    if not m:
        raise RuntimeError("Authority reference centres not found in game")
    centres=json.loads(m.group(1))
    if len(centres)!=33:
        raise RuntimeError(f"Expected 33 authority reference centres, found {len(centres)}")
    return [(str(name),float(lat),float(lon)) for name,lat,lon in centres]

def kilometre_distance(a,b):
    ay,ax=a
    by,bx=b
    x=math.radians(bx-ax)*math.cos(math.radians((ay+by)/2))
    y=math.radians(by-ay)
    return 6371*math.hypot(x,y)

def geo_area(lat,lon):
    if lat>51.55: return "north"
    if lat<51.45: return "south"
    if lon>=0.04: return "east"
    if lon<=-0.27: return "west"
    return "central"

def safe_thumb(url):
    if not isinstance(url,str):
        return ""
    p=urllib.parse.urlsplit(url)
    allowed={f"s{i}.geograph.org.uk" for i in range(10)}|{"www.geograph.org.uk","geograph.org.uk"}
    if p.scheme!="https" or p.hostname not in allowed or p.username or p.password:
        return ""
    if not p.path.endswith((".jpg",".jpeg",".png",".webp")):
        return ""
    return urllib.parse.urlunsplit(("https",p.hostname,p.path,"",""))

def select_spaced(records,selected,limit=MAX_PER_CENTRE):
    """Greedy farthest-first: prioritise geographic spread, not API order."""
    valid=[]
    for rec in records:
        try:
            lat=float(rec["lat"]);lon=float(rec["lon"])
        except (TypeError,ValueError):
            continue
        if not math.isfinite(lat) or not math.isfinite(lon):
            continue
        if not rec.get("sourceUrl") or not safe_thumb(rec.get("thumbUrl")):
            continue
        if not rec.get("licence") or not rec.get("author"):
            continue
        if not 51.25<=lat<=51.74 or not -.62<=lon<=.42:
            continue
        if rec["sourceId"] in {s["sourceId"] for s in selected}:
            continue
        valid.append(rec)
    pick=[]
    while valid and len(pick)<limit:
        references=selected+pick
        if not references:
            valid.sort(key=lambda x:(bool(x.get("imageTaken")),x["sourceId"]),reverse=True)
            best=valid[0]
            best_km=999
        else:
            scored=[(min(kilometre_distance((float(r["lat"]),float(r["lon"])),
                      (float(ref["lat"]),float(ref["lon"]))) for ref in references),r)
                    for r in valid]
            best_km,best=max(scored,key=lambda q:(q[0],bool(q[1].get("imageTaken")),q[1]["sourceId"]))
        if references and best_km<MIN_SEPARATION_KM:
            break
        pick.append(best)
        valid.remove(best)
    return pick

def download_thumbnail(record):
    url=safe_thumb(record.get("thumbUrl"))
    if not url:
        return ""
    # A supplied Geograph thumb is a preview, not a reviewed full-resolution image.
    name=record["sourceId"]
    if not re.fullmatch(r"\d{1,15}",str(name)):
        return ""
    ext=Path(urllib.parse.urlsplit(url).path).suffix.lower()
    path=IMAGES/(f"{name}{ext}")
    req=urllib.request.Request(url,headers={"User-Agent":AGENT,
        "Accept":"image/jpeg,image/png,image/webp"})
    try:
        with urllib.request.urlopen(req,timeout=17) as response:
            typ=response.headers.get("Content-Type","").lower()
            if "image/" not in typ:
                return ""
            content=response.read(220001)
            if len(content)>220000 or len(content)<100:
                return ""
        # A small signature check stops accidental HTML error-page storage.
        if not (content[:3]==b"\xff\xd8\xff" or content[:8]==b"\x89PNG\r\n\x1a\n"
                or content[:4]==b"RIFF"):
            return ""
        path.write_bytes(content)
        return "thumbs/"+path.name
    except (urllib.error.URLError,TimeoutError,ValueError,OSError):
        return ""

def main():
    key=os.environ.get("GEOGRAPH_API_KEY","").strip()
    if not key:
        print("Missing repository secret GEOGRAPH_API_KEY",file=sys.stderr)
        return 2
    centres=sample_centres()
    OUT.mkdir(parents=True,exist_ok=True)
    IMAGES.mkdir(parents=True,exist_ok=True)
    selected=[]
    per_area=[]
    errors=0
    # Scatter London samples across administrative reference points, NOT
    # proofs of actual photo boroughs or exact subject locations.
    for i,(name,lat,lon) in enumerate(centres,1):
        if i>1: time.sleep(2)
        incoming,error=query_point(key,name,lat,lon)
        if error: errors+=1
        candidates=[]
        for item in incoming:
            if not isinstance(item,dict):
                continue
            flags=classify(item)
            record=as_record(item,name,geo_area(lat,lon))
            if not record.get("sourceId") or not flags["within_guide"]:
                continue
            record["sampleCentreBorough"]=name
            record["borough"]=""  # Never infer photo borough from query centre.
            candidates.append(record)
        new=select_spaced(candidates,selected)
        selected.extend(new)
        per_area.append({"centre":name,"lat":lat,"lon":lon,
                         "returned":len(incoming),"unique_spaced_selected":len(new),
                         "error":error})
        print(f"{i:02d}/33 {name}: {len(incoming)} returned, "
              f"{len(new)} geographically distinct selected"
              + (f", HTTP warning: {error}" if error else ""),flush=True)
    if not selected:
        raise RuntimeError("No metadata candidates returned from Geograph")

    image_ok=0
    for i,rec in enumerate(selected,1):
        relative=download_thumbnail(rec)
        rec["localThumbnail"]=relative
        rec["visualStatus"]="not-reviewed"
        rec["sourceCollection"]="Geograph · manually approved image reuse route"
        rec["coordReview"]="unknown; may be 1 km grid centroid or photographed subject"
        rec["boundaryReview"]="approximate guide only; official borough not assigned"
        rec["rightsReview"]="licence-present; individual reuse terms not independently checked"
        rec["nearDuplicateReview"]="spatially thinned at 450 m; visual duplicates unknown"
        rec["decision"]="unreviewed"
        if relative:
            image_ok+=1
        # Polite network use; do not burst images requests.
        if i<len(selected):time.sleep(0.25)
    # Output is a private review artifact; no images or metadata are committed
    # back to the public site or the main repository.
    (OUT/"candidates.json").write_text(json.dumps(selected,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    columns=list(selected[0].keys())
    with (OUT/"candidates.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=columns,extrasaction="ignore")
        w.writeheader();w.writerows(selected)
    summary={"generated_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "method":"33 approximate authority reference centres, 6 photos/query, spatial thinning 450m",
             "sample_centres":33,"returned_total":sum(c["returned"] for c in per_area),
             "candidate_count":len(selected),"cached_thumbnails":image_ok,
             "captured_years":sum(bool(c["imageTaken"]) for c in selected),
             "api_errors":errors,"centres":per_area,
             "warnings":[
               "Reference points are not formal borough boundaries or photo borough assignments.",
               "Photo coordinates may indicate grid-square centres or subjects, not camera positions.",
               "Photos have not been visually approved; thumbnails are only for local review.",
               "Licence label presence does not prove individual terms or publication approval.",
               "Source and photographer credits must always be displayed.",
               "This one-off small-scale sample is not Geograph bulk extraction.",
             ]}
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(f"RESULT: {len(selected)} spatially selected records, "
          f"{image_ok} locally copied thumbs, {errors} API errors.",flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
