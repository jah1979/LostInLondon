#!/usr/bin/env python3
"""Build an offline metadata-only index of geotagged Wikimedia Commons photos.

Photographs remain hosted/licensed on Wikimedia Commons. Requests run only
in CI, sequentially, with back-off and an identifying User-Agent.
"""
import html
import json
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

ROOT = Path(__file__).resolve().parents[1]
API = 'https://commons.wikimedia.org/w/api.php'
OUTPUT = ROOT / 'photo-catalog.js'
UA = 'LostInLondonPhotoCatalog/1.0 (https://github.com/jah1979/LostInLondon; contact via GitHub issues)'
BAD_TITLE = re.compile(r'(?:\.svg$|diagram|floor.?plan|location.?map|coat of arms|icon|logo|map of|screenshot|poster|advertis|infographic|route map|blue plaque closeup)', re.I)
DATE_PATTERN = re.compile(r'^(?:(?:\d{1,2}\s+[a-zA-Z]+\s+)|(?:[a-zA-Z]+\s+\d{1,2},?\s+))?(1[89]\d{2}|20\d{2})(?=$|[-/: T\s])')
UNCERTAIN = re.compile(r'\b(?:circa|approx|unknown|before|after|between|c\.|ca\.|~|probably|or)\b', re.I)

def read_seeds():
    app = (ROOT / 'app.js').read_text(encoding='utf-8')
    block = re.search(r'const SEEDS = \[(.*?)\];', app, re.S)
    if not block:
        raise RuntimeError('SEEDS missing from app.js')
    matches = re.findall(r"\{name:'([^']+)',lat:([-0-9.]+),lon:([-0-9.]+)\}", block.group(1))
    if len(matches) < 20:
        raise RuntimeError('Too few London search seeds')
    return [(name,float(lat),float(lon)) for name,lat,lon in matches]

def clean(value):
    return ' '.join(html.unescape(re.sub(r'<[^>]*>',' ',str(value or ''))).split())

def year_from(ext):
    value = clean((ext.get('DateTimeOriginal') or {}).get('value'))
    if not value or UNCERTAIN.search(value):
        return None
    match = DATE_PATTERN.search(value)
    if not match:
        return None
    year = int(match.group(1))
    return year if 1850 <= year <= datetime.now(timezone.utc).year else None

def photo_from(page):
    if page.get('ns') != 6 or not page.get('coordinates') or not page.get('imageinfo'):
        return None
    lat = page['coordinates'][0].get('lat')
    lon = page['coordinates'][0].get('lon')
    if not isinstance(lat,(float,int)) or not isinstance(lon,(float,int)):
        return None
    if not (51.25 <= lat <= 51.74 and -0.62 <= lon <= 0.42):
        return None
    info = page['imageinfo'][0]
    if info.get('width',0)<780 or info.get('height',0)<450:
        return None
    if info.get('mime') not in ('image/jpeg','image/png','image/webp'):
        return None
    title = page.get('title','')
    if BAD_TITLE.search(title):
        return None
    url = info.get('thumburl') or info.get('url','')
    if not url.startswith('https://upload.wikimedia.org/'):
        return None
    ext = info.get('extmetadata') or {}
    author = clean((ext.get('Artist') or {}).get('value')) or 'Wikimedia Commons contributor'
    licence = clean((ext.get('LicenseShortName') or {}).get('value'))
    if not licence:
        return None
    link = str((ext.get('LicenseUrl') or {}).get('value',''))
    if link and not link.startswith('https://'):
        link = ''
    image_id = page.get('pageid')
    if not isinstance(image_id,int):
        return None
    return {'id':image_id,'year':year_from(ext),
            'lat':lat,'lon':lon,'url':url,
            'source':'https://commons.wikimedia.org/wiki/'+urllib.parse.quote(title.replace(' ','_'),safe=''),
            'title':re.sub(r'\.[a-zA-Z0-9]{3,5}$','',title.removeprefix('File:').replace('_',' '))[:140],
            'author':author[:110],'license':licence[:70],'licenseLink':link}

def get_json(params):
    url = API+'?'+urllib.parse.urlencode(params)
    for attempt in range(3):
        req = urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=40) as response:
                result = json.load(response)
            if result.get('error'):
                raise RuntimeError(str(result['error']))
            return result
        except urllib.error.HTTPError as error:
            if error.code not in (429,503) or attempt == 2:
                raise
            try:
                pause = min(90,max(5,int(error.headers.get('Retry-After',''))))
            except ValueError:
                pause = 5*(2**attempt)
            print('Wikimedia backoff:',error.code,pause,'seconds',flush=True)
            time.sleep(pause)
    raise RuntimeError('Wikimedia query failed')

def main():
    seeds = read_seeds()
    random.Random(20261030).shuffle(seeds)
    found = {}
    failures = 0
    for index,(name,lat,lon) in enumerate(seeds,1):
        params = {
            'action':'query','format':'json','formatversion':'2',
            'generator':'geosearch','ggscoord':f'{lat}|{lon}',
            'ggsradius':'5500','ggsnamespace':'6',
            'ggsprimary':'all','ggslimit':'22',
            'prop':'coordinates|imageinfo','coprop':'type|globe',
            'iiprop':'url|size|mime|extmetadata','iiurlwidth':'960',
            'iiextmetadatafilter':'Artist|DateTimeOriginal|LicenseShortName|LicenseUrl'
        }
        try:
            response = get_json(params)
            before = len(found)
            for page in response.get('query',{}).get('pages',[]):
                result = photo_from(page)
                if result:
                    found.setdefault(result['id'],result)
            print(f'{index}/{len(seeds)} {name}: +{len(found)-before}',flush=True)
        except Exception as error:
            failures += 1
            print(f'{name}: {error}',file=sys.stderr,flush=True)
        if index != len(seeds):
            time.sleep(1.2)  # bounded, courteous API rate
    photos = list(found.values())[:350]
    dated = sum(photo['year'] is not None for photo in photos)
    print(f'Valid: {len(photos)}, dated: {dated}, failed areas: {failures}',flush=True)
    if len(photos)<24 or dated<12:
        raise RuntimeError('Too few validated photos: existing catalogue retained')
    text = ('/* Wikimedia Commons geotagged photo metadata, not image files. '
            'Generated by scripts/build_photo_catalog.py. */\n'
            'window.LONDON_PHOTO_CATALOG = '+
            json.dumps(photos,ensure_ascii=False,separators=(',',':'))+';\n')
    OUTPUT.write_text(text,encoding='utf-8')
    print(f'Wrote {OUTPUT} ({len(photos)} records)',flush=True)

if __name__ == '__main__':
    main()
