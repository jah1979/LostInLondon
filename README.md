# Lost in London — Where + When

A free, mobile-friendly London-only photo-geography game, inspired by location guessing and the date-estimation mechanic in TimeGuessr. It works as a **static website** — no database, API key or player account required.

## Play

1. Choose a hunting ground: **Greater London**, **Inner London** (roughly a 7 km radius), **North of the River**, or **South of the River**. North/South modes cover Greater London on the selected side of the Thames.
2. Choose **Where + When** or **Where Only**, and 5 or 10 rounds.
3. Optionally set a 90-second round timer.
4. Inspect a real London photo and search the map by area or landmark. The local place list responds instantly; for less familiar London locations, select **Search all London** from the suggestions to look up OpenStreetMap places via Photon on demand. This re-centres the map without placing a guess pin. In **Where + When** mode, estimate the photo year; in **Where Only**, guess the location without a date prompt. On mobile, pinch with two fingers to zoom (up to 4×) and drag to pan; on desktop, use the mouse wheel or +/− buttons.
5. Reveal the actual location and year, with separate scores for both answers.
6. Share your game link and your score with mates.

Each location guess can earn up to **5,000 points**. In Where + When mode, the year is worth up to another **5,000 points**, so a 5-round game has a maximum of **50,000 points**. Scores are calculated by distance (haversine) and the absolute number of years off. A local personal best is stored only in the player's browser.

## Make a public shareable website with GitHub Pages

These steps take only a few minutes, assuming you have a GitHub account.

1. At https://github.com/new, create a **public** repository called `lost-in-london`. You can leave it empty.
2. Upload the **three site files** `index.html`, `styles.css` and `app.js` to the top level (root) of that repository. `README.md` is optional but helpful.
3. In your repository select **Settings → Pages**.
4. Under **Build and deployment**, select **Deploy from a branch**, then choose branch **main** and folder **/(root)**, and save.
5. GitHub Pages will publish the game at `https://YOUR_GITHUB_USERNAME.github.io/lost-in-london/` once its deployment finishes. Replace `YOUR_GITHUB_USERNAME` with your own GitHub login; confirm the URL works before sharing it.

You can also upload the files to Netlify, Cloudflare Pages or another static-site host.

## Run locally

Open `index.html` in your browser with an internet connection, or use a local server such as:

```bash
python3 -m http.server 8000
```

Then visit http://localhost:8000.

## Where the photographs come from

- **Wikimedia Commons API:** The game requests photo files with geocoordinates, valid image dimensions and original creation date information. It uses the file's `DateTimeOriginal` metadata to determine the year, not the upload timestamp. A photo missing a trustworthy parseable year is excluded in **Where + When** mode. In **Where Only** mode, the original year is not required.
- **Credits and licences:** Each loaded photo includes the creator attribution, a link to its Commons file page and, when supplied, its licence. Please keep this credit line visible when modifying the game.
- **OpenStreetMap:** Maps are rendered with Leaflet and OpenStreetMap data/tiles and retain the required copyright credit.

### Limitations of this first version

- **Photo loading (BETA 0.15):** For the first round, the game now first tries a small browser-local collection of *previously validated but unseen* Commons photos. If that is empty, it uses a one-request Commons geosearch with imageinfo for up to 10 files, falling back to the existing deeper two-request discovery and a delayed second search when necessary. Later rounds can reuse cached candidates before making another API call, alongside the existing single-photo prefetch. The cache stores only public photo metadata and Commons URLs, **not image files**; entries expire after 14 days, cannot bypass the currently chosen geographic region or date validation, and photos already displayed in this browser are excluded. On mobile, Commons thumbnails are requested at 960 px rather than 1200 px, while desktop retains 1200 px. Browsers and Wikimedia may choose different actual thumbnail sizes. Wikimedia API or image slowness can still affect first-time and cache-miss loads; no guaranteed latency reduction is claimed.

- **North of the River / South of the River** use a local OS Open Rivers-derived Thames centreline produced by scripts/generate_thames.py from OS watercourse links. The source is generalised centreline data, NOT surveyed bank polygons, and a continuous line is map-matched to it with interpolated connections where necessary. Geotags within 50 metres of the estimated river line are excluded as ambiguous. The final image coordinates are checked, not merely the search neighbourhood. This is still an approximate side-of-river boundary near complex meanders and islands. Players make no extra GIS requests.

- **Map-area search:** An offline shortlist of boroughs and well-known neighbourhoods appears as you type. To find less familiar places and landmarks, the user can explicitly select **Search all London**. This sends that one query to [Photon](https://photon.komoot.io/) (using OpenStreetMap geocoding data) and returns London-bounded point results. The lookup is not automatic autocomplete; results are cached in memory for the session, and the search can fail if the public demo server is busy. Photon permits modest use but does not guarantee availability; high traffic needs a dedicated instance or paid provider. Search query text is shared with that external service only when the user selects the option. Selecting a result moves the map without placing a guess pin. OSM place data has [Open Database Licence](https://www.openstreetmap.org/copyright) obligations; attribution is displayed beside online search results.

- This is a **photo-guessing game**, not navigable Google Street View. You can zoom/pan each photograph; you cannot walk around the street. Google Street View integration would require additional implementation, credentials and terms review.
- London filtering is based on an **approximate Greater London outline**, not authoritative borough boundaries. The inner-London option uses a 7 km radius rather than exact fare zones.
- Commons photo coordinates, captions and dates are community-supplied and may occasionally be imperfect. The date recorded for a scanned historical photograph may not reflect the shutter date. This is an exploratory game, not a certified historic GIS dataset.
- Fresh photos are randomly queried from Wikimedia Commons, while previously validated-but-unseen candidates may be reused locally for faster starts. Photo discovery is not centrally curated, and fresh requests still depend on the Commons API's availability. Many date-tagged geolocated Commons photos are relatively recent, so historic variety may be uneven. Photo searches may fail on slow or restricted networks, and there is a **Try another location** button.
- The share button copies your **website link** or invokes your device's share sheet. Players receive random rounds, not the same seeded/daily challenge. Scores are local to each browser, not posted to a leaderboard.
- This is a small personal/demo site. Before high-traffic promotion, review the Wikimedia Commons API etiquette/terms and [OpenStreetMap tile usage policy](https://operations.osmfoundation.org/policies/tiles/) and consider a dedicated map tile provider.


**Additional place search attribution:** Landmark and place search is provided by [Photon (komoot)](https://photon.komoot.io/) using © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), under ODbL. Place search is separate from the Wikimedia Commons image metadata and Ordnance Survey river geometry. The public Photon endpoint is provided on a best-effort basis with fair-use limits.

### Offline-first photo discovery (BETA 0.16)

The game first checks `photo-catalog.js`, a **metadata-only index** of validated Wikimedia Commons photos. Photographs themselves remain on Wikimedia Commons, with their original creators and licences.

The index is generated outside gameplay by `scripts/build_photo_catalog.py` and refreshed through `.github/workflows/refresh-photo-catalog.yml`. The workflow can run manually or weekly. The generator makes a modest number of sequential, identified Wikimedia API requests and replaces the catalogue only after minimum validation checks. It stores Commons IDs, coordinates, capture year where known, image URL, source, author, licence and licence link — never image files.

For each round, cached and indexed records must still pass the selected game area's coordinates and, in Where + When mode, the original date test. Seen photos are excluded. If the catalogue is empty, exhausted or an image fails to load, the existing live Commons search remains available. Image downloads still depend on Wikimedia and the player's connection. The game does not mirror or proxy photos.

**First build:** In GitHub, open **Actions → Refresh London photo catalogue → Run workflow** if the initial push has not triggered an automatic build. The initial version of `photo-catalog.js` contains zero photos until the generator succeeds. Do not assume the loading improvement is active before the index is populated.

## Code and photo licences

The game code in this folder is released under MIT (see `LICENSE`). Photographs are **not** distributed with the code: they are served directly from Commons and retain their own independent licences and attribution requirements. OpenStreetMap data and Leaflet have separate terms and copyright notices.

## Deployment check

This static site is published with GitHub Pages from the root of the `main` branch.


### Landing-page boundary attribution
The decorative Greater London outline was simplified from Ordnance Survey Boundary-Line geometry distributed in [utisz/compound-cities](https://github.com/utisz/compound-cities/blob/master/greater-london.geo.json), under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). Contains Ordnance Survey data © Crown copyright and database right. The landing-page Thames artwork and Tube-inspired lines are illustrative, not official GIS layers or official Transport for London route maps.

**Game-mode river source:** Coordinates in thames-geometry.js derive from Ordnance Survey OS Open Rivers data, © Crown copyright and database right 2026, used under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). [Ordnance Survey](https://www.ordnancesurvey.co.uk/products/os-open-rivers) describes the product as a generalised watercourse centreline. The extraction script and GitHub Actions workflow periodically regenerate a local copy, so gameplay requires no external river API.
