#!/usr/bin/env python3
"""Build an incremental, metadata-only London photo catalogue from Commons.

Retain verified records between runs, and never download or relicense images.
Wikimedia geosearch is often overloaded; minimize its work, back off on
transient API errors, and do not erase existing records if discovery fails.
"""
import html
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

ROOT = Path(__file__).resolve().parents[1]
API = 'https://commons.wikimedia.org/w/api.php'
OUTPUT = ROOT / 'photo-catalog.js'
UA = 'LostInLondonPhotoCatalog/1.1 (https://github.com/jah1979/LostInLondon; report issues at this repository)'
MAX_PHOTOS = 350
BAD_TITLE = re.compile(r'(?:\.svg$|diagram|floor.?plan|location.?map|coat of arms|icon|logo|map of|screenshot|poster|advertis|infographic|route map|blue plaque closeup)', re.I)
DATE_PATTERN = re.compile(r'^(?:(?:\d{1,2}\s+[a-zA-Z]+\s+)|(?:[a-zA-Z]+\s+\d{1,2},?\s+))?(1[89]\d{2}|20\d{2})(?=$|[-/: T\s])')
UNCERTAIN = re.compile(r'\b(?:circa|approx|unknown|before|after|between|c\.|ca\.|~|probably|or)\b', re.I)


class BusyCommons(RuntimeError):
    """Upstream Commons search/index currently unavailable."""


def read_seeds():
    app = (ROOT / 'app.js').read_text(encoding='utf-8')
    block = re.search(r'const SEEDS = \[(.*?)\];', app, re.S)
    if not block:
        raise RuntimeError('SEEDS missing from app.js')
    values = re.findall(r"\{name:'([^']+)',lat:([-0-9.]+),lon:([-0-9.]+)\}", block.group(1))
    if len(values) < 20:
        raise RuntimeError('Too few London search seeds')
    return [(name, float(lat), float(lon)) for name, lat, lon in values]


def clean(value):
    return ' '.join(html.unescape(re.sub(r'<[^>]*>', ' ', str(value or ''))).split())


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
    lat, lon = (page['coordinates'][0].get(key) for key in ('lat', 'lon'))
    if not isinstance(lat, (float, int)) or not isinstance(lon, (float, int)):
        return None
    if not (51.25 <= lat <= 51.74 and -0.62 <= lon <= 0.42):
        return None
    info = page['imageinfo'][0]
    if info.get('width', 0) < 780 or info.get('height', 0) < 450:
        return None
    if info.get('mime') not in ('image/jpeg', 'image/png', 'image/webp'):
        return None
    title = page.get('title', '')
    if BAD_TITLE.search(title):
        return None
    url = info.get('thumburl') or info.get('url', '')
    if not url.startswith('https://upload.wikimedia.org/'):
        return None
    ext = info.get('extmetadata') or {}
    author = clean((ext.get('Artist') or {}).get('value')) or 'Wikimedia Commons contributor'
    licence = clean((ext.get('LicenseShortName') or {}).get('value'))
    if not licence:
        return None
    link = str((ext.get('LicenseUrl') or {}).get('value', ''))
    if link and not link.startswith('https://'):
        link = ''
    image_id = page.get('pageid')
    if not isinstance(image_id, int):
        return None
    return {'id': image_id, 'year': year_from(ext),
            'lat': lat, 'lon': lon, 'url': url,
            'source': 'https://commons.wikimedia.org/wiki/' +
                      urllib.parse.quote(title.replace(' ', '_'), safe=''),
            'title': re.sub(r'\.[a-zA-Z0-9]{3,5}$', '',
                            title.removeprefix('File:').replace('_', ' '))[:140],
            'author': author[:110], 'license': licence[:70], 'licenseLink': link}


def valid_existing(photo):
    return (isinstance(photo, dict) and isinstance(photo.get('id'), int)
            and isinstance(photo.get('lat'), (int, float))
            and isinstance(photo.get('lon'), (int, float))
            and 51.25 <= photo['lat'] <= 51.74
            and -0.62 <= photo['lon'] <= 0.42
            and (photo.get('year') is None or
                 isinstance(photo.get('year'), int) and 1850 <= photo['year'] <= datetime.now(timezone.utc).year)
            and isinstance(photo.get('url'), str) and photo['url'].startswith('https://upload.wikimedia.org/')
            and isinstance(photo.get('source'), str) and photo['source'].startswith('https://commons.wikimedia.org/wiki/')
            and isinstance(photo.get('author'), str)
            and isinstance(photo.get('license'), str) and bool(photo['license'])
            and isinstance(photo.get('licenseLink'), str)
            and isinstance(photo.get('title'), str))


def read_existing():
    if not OUTPUT.exists():
        return {}
    contents = OUTPUT.read_text(encoding='utf-8')
    match = re.search(r'window\.LONDON_PHOTO_CATALOG\s*=\s*(\[.*?\]);', contents, re.S)
    if not match:
        raise RuntimeError('Existing catalogue cannot be parsed; refusing to overwrite it')
    photos = json.loads(match.group(1))
    if not isinstance(photos, list):
        raise RuntimeError('Existing photo catalogue is not a list')
    return {photo['id']: photo for photo in photos if valid_existing(photo)}


def get_json(params):
    url = API + '?' + urllib.parse.urlencode(params)
    for attempt in range(3):
        request = urllib.request.Request(url, headers={
            'User-Agent': UA, 'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                result = json.load(response)
            if result.get('error'):
                error = result['error']
                code = str(error.get('code', ''))
                if 'too-busy' in code or code == 'maxlag':
                    raise BusyCommons(code + ': ' + str(error.get('info', '')))
                raise RuntimeError('Commons API: ' + code + ': ' + str(error.get('info', '')))
            return result
        except (BusyCommons, urllib.error.HTTPError) as error:
            if isinstance(error, urllib.error.HTTPError) and error.code not in (429, 503):
                raise
            if attempt == 2:
                raise
            retry_after = None
            if isinstance(error, urllib.error.HTTPError):
                try:
                    retry_after = int(error.headers.get('Retry-After', ''))
                except (ValueError, TypeError):
                    pass
            delay = min(50, max(5, retry_after or 6 * (attempt + 1)))
            print(f'Upstream Commons busy ({error}); retry in {delay}s', flush=True)
            time.sleep(delay)
    raise RuntimeError('Commons API retries exhausted')


def locate_files(seed, rng):
    name, lat, lon = seed
    # Alter search origins each run; otherwise 28 fixed nearby lists keep
    # returning the same unsuitable files forever.
    radius_km = rng.uniform(0.3, 1.6)
    angle = rng.uniform(0, 2 * math.pi)
    search_lat = lat + math.cos(angle) * radius_km / 111.2
    search_lon = lon + math.sin(angle) * radius_km / (111.2 * math.cos(math.radians(lat)))
    result = get_json({
        'action': 'query', 'format': 'json', 'formatversion': '2',
        'generator': 'geosearch', 'ggscoord': f'{search_lat}|{search_lon}',
        'ggsradius': '5500', 'ggsnamespace': '6', 'ggsprimary': 'all',
        'ggslimit': '100', 'prop': 'coordinates', 'coprop': 'type|globe'
    })
    pages = [
        p for p in result.get('query', {}).get('pages', [])
        if p.get('ns') == 6 and not BAD_TITLE.search(p.get('title', ''))
        and p.get('coordinates')
    ]
    rng.shuffle(pages)
    return pages


def details_for(pages):
    params = {
        'action': 'query', 'format': 'json', 'formatversion': '2',
        'pageids': '|'.join(str(p['pageid']) for p in pages),
        'prop': 'coordinates|imageinfo', 'coprop': 'type|globe',
        'iiprop': 'url|size|mime|extmetadata', 'iiurlwidth': '960',
        'iiextmetadatafilter': 'Artist|DateTimeOriginal|LicenseShortName|LicenseUrl'
    }
    response = get_json(params)
    return [photo for page in response.get('query', {}).get('pages', [])
            if (photo := photo_from(page)) is not None]


def main():
    rng = random.Random(int(os.environ.get('GITHUB_RUN_ID', '0')) or int(time.time()))
    seeds = read_seeds()
    rng.shuffle(seeds)
    found = read_existing()
    initial = len(found)
    print(f'Existing validated Commons records: {initial}', flush=True)
    failures = 0
    for index, seed in enumerate(seeds, 1):
        name = seed[0]
        try:
            pages = locate_files(seed, rng)
            novel = [p for p in pages if p['pageid'] not in found]
            # Fetch metadata in bounded batches only for files that pass
            # the cheap geotag/title filter first.
            added = 0
            for offset in (0, 24):
                batch = novel[offset:offset + 24]
                if not batch:
                    break
                photos = details_for(batch)
                for photo in photos:
                    if photo['id'] not in found:
                        found[photo['id']] = photo
                        added += 1
                if added >= 8:
                    break
            print(f'{index}/{len(seeds)} {name}: {len(pages)} candidates; +{added}', flush=True)
        except Exception as error:
            failures += 1
            print(f'{name}: {type(error).__name__}: {error}', file=sys.stderr, flush=True)
        if len(found) >= MAX_PHOTOS:
            break
        time.sleep(1.4)
    new_count = len(found) - initial
    dated = sum(p['year'] is not None for p in found.values())
    print(f'Catalogue: {len(found)} valid (+{new_count}), {dated} dated, {failures} failed areas', flush=True)

    if not found:
        raise RuntimeError('Commons supplied no valid photo metadata. No catalogue overwritten. '
                           'Check the upstream cirrussearch-too-busy errors above.')
    if not new_count:
        print('WARNING: No additional photos today; preserving existing index.', flush=True)
        return

    photos = list(found.values())[:MAX_PHOTOS]
    text = ('/* Licensed Wikimedia Commons photo METADATA only; no image files. '
            'Generated by scripts/build_photo_catalog.py. */\n'
            'window.LONDON_PHOTO_CATALOG = ' +
            json.dumps(photos, ensure_ascii=False, separators=(',', ':')) + ';\n')
    OUTPUT.write_text(text, encoding='utf-8')
    print(f'Wrote {OUTPUT} ({len(photos)} records)', flush=True)


if __name__ == '__main__':
    main()
