# Lost in London — Where + When

A free, mobile-friendly London-only photo-geography game, inspired by location guessing and the date-estimation mechanic in TimeGuessr. It works as a **static website** — no database, API key or player account required.

## Play

1. Choose **Greater London** or **Inner London** (roughly a 7 km radius from central London).
2. Choose **Where + When** or **Where Only**, and 5 or 10 rounds.
3. Optionally set a 90-second round timer.
4. Inspect a real London photo, place your guess on the OpenStreetMap map, and estimate the photograph's year with the slider.
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

- This is a **photo-guessing game**, not navigable Google Street View. You can zoom/pan each photograph; you cannot walk around the street. Google Street View integration would require additional implementation, credentials and terms review.
- London filtering is based on an **approximate Greater London outline**, not authoritative borough boundaries. The inner-London option uses a 7 km radius rather than exact fare zones.
- Commons photo coordinates, captions and dates are community-supplied and may occasionally be imperfect. The date recorded for a scanned historical photograph may not reflect the shutter date. This is an exploratory game, not a certified historic GIS dataset.
- Photos are randomly queried live from Wikimedia Commons; results are not curated, and requests depend on the availability of the Commons API. Many date-tagged geolocated Commons photos are relatively recent, so historic variety may be uneven. Photo searches may fail on slow or restricted networks, and there is a **Try another location** button.
- The share button copies your **website link** or invokes your device's share sheet. Players receive random rounds, not the same seeded/daily challenge. Scores are local to each browser, not posted to a leaderboard.
- This is a small personal/demo site. Before high-traffic promotion, review the Wikimedia Commons API etiquette/terms and [OpenStreetMap tile usage policy](https://operations.osmfoundation.org/policies/tiles/) and consider a dedicated map tile provider.

## Code and photo licences

The game code in this folder is released under MIT (see `LICENSE`). Photographs are **not** distributed with the code: they are served directly from Commons and retain their own independent licences and attribution requirements. OpenStreetMap data and Leaflet have separate terms and copyright notices.