/*
 * LOST IN LONDON — a free, client-side Where + When photo guessing game.
 * Photos, coordinates, credit, and date-of-creation are read from Wikimedia
 * Commons' public API. A photo without an identifiable creation year is never
 * used for year-guessing; no dates are guessed from upload timestamps.
 * See README.md for attribution, limitations, and deployment instructions.
 */
(() => {
  'use strict';

  const $ = id => document.getElementById(id);
  const $all = selector => [...document.querySelectorAll(selector)];
  const LONDON_CENTER = [51.5074, -0.1278];
  const MAX_YEAR = new Date().getFullYear();
  const MIN_YEAR = 1850;
  const API = 'https://commons.wikimedia.org/w/api.php';
  const LONDON_MAP_BOUNDS = [[51.25, -0.62], [51.74, 0.42]];
  const SEEDS = [
    {name:'Westminster',lat:51.5021,lon:-0.1261},
    {name:'Soho',lat:51.5137,lon:-0.1337},
    {name:'South Bank',lat:51.5030,lon:-0.1166},
    {name:'Camden',lat:51.5393,lon:-0.1426},
    {name:'Hackney',lat:51.5441,lon:-0.0557},
    {name:'Islington',lat:51.5362,lon:-0.1033},
    {name:'Greenwich',lat:51.4826,lon:-0.0077},
    {name:'Brixton',lat:51.4627,lon:-0.1145},
    {name:'Tooting',lat:51.4282,lon:-0.1676},
    {name:'Wimbledon',lat:51.4214,lon:-0.2064},
    {name:'Richmond',lat:51.4613,lon:-0.3037},
    {name:'Chiswick',lat:51.4877,lon:-0.2687},
    {name:'Ealing',lat:51.5130,lon:-0.3089},
    {name:'Hammersmith',lat:51.4927,lon:-0.2235},
    {name:'Hampstead',lat:51.5566,lon:-0.1780},
    {name:'Alexandra Palace',lat:51.5940,lon:-0.1304},
    {name:'Stratford',lat:51.5413,lon:-0.0036},
    {name:'Woolwich',lat:51.4898,lon:0.0659},
    {name:'Crystal Palace',lat:51.4185,lon:-0.0754},
    {name:'Croydon',lat:51.3727,lon:-0.1006},
    {name:'Bromley',lat:51.4060,lon:0.0158},
    {name:'Wembley',lat:51.5560,lon:-0.2795},
    {name:'Harrow',lat:51.5795,lon:-0.3386},
    {name:'Kingston',lat:51.4124,lon:-0.3000},
    {name:'Ilford',lat:51.5591,lon:0.0730},
    {name:'Hounslow',lat:51.4684,lon:-0.3623},
    {name:'Enfield',lat:51.6520,lon:-0.0800},
    {name:'Beckenham',lat:51.4085,lon:-0.0248}
  ];
  const IGNORED_TITLES = /(?:\.svg$|diagram|floor.?plan|location.?map|coat of arms|icon|logo|map of|screenshot|poster|advertis|infographic|route map|blue plaque closeup)/i;

  const settings = {area:'all', type:'both', rounds:5, timer:0};
  let roundIndex = 0, points = 0, photo = null, guess = null;
  let map = null, resultMap = null, guessMarker = null, loading = false;
  let yearValue = 1988, timerInterval = null, deadline = 0, runToken = 0;
  let sceneReady = false, answered = false, available = [], usedPhotos = new Set(), usedSeeds = new Set();
  let prefetchedPhoto = null, prefetchPromise = null;

  const userPhoto = $('location-photo');
  const yearSlider = $('year-slider');
  const roundMax = () => settings.type === 'both' ? 10000 : 5000;
  const formatNumber = n => Math.round(n).toLocaleString('en-GB');
  const clamp = (v, low, high) => Math.min(high, Math.max(low, v));
  const randomItem = items => items[Math.floor(Math.random() * items.length)];
  const shuffle = arr => {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  };

  function setView(id) {
    ['welcome','game','result','finished'].forEach(k => $(k).classList.toggle('hidden', k !== id));
    window.scrollTo({top:0,behavior:'instant'});
  }

  function toast(message) {
    const el = $('toast');
    el.textContent = message;
    el.classList.add('show');
    clearTimeout(toast.timeout);
    toast.timeout = setTimeout(() => el.classList.remove('show'), 3300);
  }

  function segment(id, key, valueFromButton) {
    const wrapper = $(id);
    wrapper.addEventListener('click', e => {
      const button = e.target.closest('button[data-' + valueFromButton + ']');
      if (!button || !wrapper.contains(button)) return;
      $all('#' + id + ' button').forEach(b => b.classList.toggle('selected', b === button));
      const value = button.dataset[valueFromButton];
      settings[key] = key === 'rounds' || key === 'timer' ? Number(value) : value;
    });
  }
  segment('mode-select', 'area', 'mode');
  segment('game-type-select', 'type', 'type');
  segment('round-select', 'rounds', 'rounds');
  segment('timer-select', 'timer', 'timer');

  yearSlider.max = String(MAX_YEAR);
  function updateYear(value) {
    yearValue = clamp(Math.round(Number(value) || 1988), MIN_YEAR, MAX_YEAR);
    yearSlider.value = String(yearValue);
    $('year-number').textContent = String(yearValue);
    $('year-guess').style.setProperty('--year-pct', ((yearValue - MIN_YEAR) / (MAX_YEAR - MIN_YEAR) * 100) + '%');
  }
  yearSlider.addEventListener('input', () => updateYear(yearSlider.value));
  updateYear(1988);

  function haversine(lat1, lon1, lat2, lon2) {
    const rads = Math.PI / 180, radius = 6371.009;
    const a = Math.sin((lat2 - lat1) * rads / 2) ** 2 +
      Math.cos(lat1 * rads) * Math.cos(lat2 * rads) * Math.sin((lon2 - lon1) * rads / 2) ** 2;
    return 2 * radius * Math.asin(Math.min(1, Math.sqrt(a)));
  }

  // This outline is a conservative approximation of the Greater London area;
  // it is not an official London borough administrative boundary dataset.
  const LONDON_POLYGON = [
    [51.66,-0.32],[51.69,-0.17],[51.70,-0.05],[51.65,0.08],
    [51.58,0.30],[51.49,0.35],[51.43,0.20],[51.29,0.18],
    [51.28,-0.03],[51.33,-0.17],[51.36,-0.35],[51.44,-0.49],
    [51.54,-0.52],[51.62,-0.39]
  ];
  function pointInPolygon(lat, lon, polygon) {
    let inside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const yi = polygon[i][0], xi = polygon[i][1], yj = polygon[j][0], xj = polygon[j][1];
      if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi) / (yj - yi) + xi)) inside = !inside;
    }
    return inside;
  }
  function inPlayArea(lat, lon) {
    if (!pointInPolygon(lat, lon, LONDON_POLYGON)) return false;
    return settings.area !== 'central' || haversine(lat, lon, ...LONDON_CENTER) <= 7;
  }

  function cleanHtml(html = '') {
    // Treat Commons metadata as text only, never inject it as live HTML.
    const plain = String(html).replace(/<[^>]*>/g, ' ')
      .replace(/&nbsp;|&#160;/gi,' ')
      .replace(/&amp;/gi,'&').replace(/&lt;/gi,'<').replace(/&gt;/gi,'>')
      .replace(/&quot;/gi,'"').replace(/&#39;/gi,"'");
    return plain.replace(/\s+/g, ' ').trim();
  }

  function creationYear(info) {
    // CommonsMetadata DateTimeOriginal is the capture/creation date, not the upload date.
    const ext = cleanHtml(info.extmetadata?.DateTimeOriginal?.value ?? '');
    let candidate = ext;
    if (!candidate) {
      const exif = (info.metadata || []).find(item => item.name === 'DateTimeOriginal');
      candidate = String(exif?.value || '');
    }
    // Reject approximate, ambiguous, ranged and machine-generated unknown dates.
    if (!candidate || /\b(?:circa|approx|unknown|before|after|between|circa|c\.|ca\.|~|probably|or)\b/i.test(candidate)) return null;
    const m = candidate.match(/^(?:(?:\d{1,2}\s+[a-zA-Z]+\s+)|(?:[a-zA-Z]+\s+\d{1,2},?\s+))?(1[89]\d{2}|20\d{2})(?=$|[-/: T\s])/);
    if (!m) return null;
    const year = Number(m[1]);
    if (year < MIN_YEAR || year > MAX_YEAR) return null;
    return year;
  }

  function readCommonsPage(page) {
    if (page.ns !== 6 || !Array.isArray(page.imageinfo) || !page.imageinfo[0] || !page.coordinates?.length) return null;
    const image = page.imageinfo[0], coords = page.coordinates[0];
    if (!Number.isFinite(coords.lat) || !Number.isFinite(coords.lon) || !inPlayArea(coords.lat, coords.lon)) return null;
    if ((image.width || 0) < 780 || (image.height || 0) < 450) return null;
    if (!['image/jpeg','image/png','image/webp'].includes(image.mime)) return null;
    if (IGNORED_TITLES.test(page.title)) return null;
    const year = creationYear(image);
    if (year === null && settings.type === 'both') return null;
    const url = image.thumburl || image.url;
    if (!url?.startsWith('https://upload.wikimedia.org/')) return null;
    const title = page.title.replace(/^File:/,'');
    const source = 'https://commons.wikimedia.org/wiki/' + encodeURIComponent(page.title.replaceAll(' ','_'));
    const ext = image.extmetadata || {};
    const author = cleanHtml(ext.Artist?.value || '') || 'Wikimedia Commons contributor';
    const license = cleanHtml(ext.LicenseShortName?.value || '') || 'Commons free licence';
    return {
      id: page.pageid, year, lat:coords.lat, lon:coords.lon,
      url, source, title: title.replaceAll('_',' ').replace(/\.[a-z0-9]{3,5}$/i,''),
      author:author.slice(0,110), license:license.slice(0,70), licenseLink:ext.LicenseUrl?.value || ''
    };
  }


  // Commons recommends avoiding large batches of expensive extmetadata.
  // First search only filenames/coordinates, then request image information
  // for a small randomized shortlist. This greatly reduces API work.
  async function fetchFromCommons(seed, signal) {
    const base = {action:'query',format:'json',formatversion:'2',origin:'*'};
    const geoQuery = new URLSearchParams({
      ...base, generator:'geosearch', ggscoord:seed.lat+'|'+seed.lon,
      ggsradius:settings.area === 'central' ? '4300' : '6000',
      ggsnamespace:'6', ggsprimary:'all', ggslimit:'65',
      prop:'coordinates', coprop:'type|globe'
    });
    const listResponse = await fetch(API+'?'+geoQuery, {signal, mode:'cors'});
    if (!listResponse.ok) throw new Error('Commons geosearch HTTP '+listResponse.status);
    const listPayload = await listResponse.json();
    if (listPayload.error) throw new Error(listPayload.error.info||'Commons geosearch error');
    const shortlist = shuffle((listPayload.query?.pages||[])
      .filter(page => page.ns === 6 && !IGNORED_TITLES.test(page.title) &&
        !usedPhotos.has(page.pageid) && page.coordinates?.some(p =>
          Number.isFinite(p.lat) && Number.isFinite(p.lon) && inPlayArea(p.lat,p.lon))))
      .slice(0,16);
    if (!shortlist.length) return [];

    const detailQuery = new URLSearchParams({
      ...base, pageids:shortlist.map(p=>p.pageid).join('|'),
      prop:'coordinates|imageinfo', coprop:'type|globe',
      iiprop:'url|size|mime|extmetadata', iiurlwidth:'1200',
      iiextmetadatafilter:'Artist|DateTimeOriginal|LicenseShortName|LicenseUrl'
    });
    const response = await fetch(API+'?'+detailQuery, {signal, mode:'cors'});
    if (!response.ok) throw new Error('Commons photo details HTTP '+response.status);
    const payload = await response.json();
    if (payload.error) throw new Error(payload.error.info||'Commons photo details error');
    return shuffle((payload.query?.pages||[]).map(readCommonsPage).filter(Boolean));
  }

  async function findCandidate(token) {
    // Fetch candidate images near different London neighbourhoods until an
    // image with both trustworthy geolocation and date metadata is found.
    for (let attempt = 0; attempt < 7; attempt++) {
      if (token !== runToken) return null;
      if (!available.length) {
        let possibleSeeds = SEEDS.filter(s =>
          settings.area === 'all' || haversine(s.lat,s.lon,...LONDON_CENTER) < 6.5);
        let remaining = possibleSeeds.filter(s => !usedSeeds.has(s.name));
        if (!remaining.length) { usedSeeds.clear(); remaining = possibleSeeds; }
        const seed = randomItem(remaining);
        usedSeeds.add(seed.name);
        try {
          const controller = new AbortController();
          const timeout = setTimeout(() => controller.abort(), 14500);
          try { available = shuffle(await fetchFromCommons(seed, controller.signal)); }
          finally { clearTimeout(timeout); }
        } catch (e) {
          console.warn('Commons photo search failed:', e);
          continue;
        }
      }
      while (available.length) {
        const candidate = available.pop();
        if (!usedPhotos.has(candidate.id)) {
          usedPhotos.add(candidate.id);
          return candidate;
        }
      }
    }
    return null;
  }


  function imageLoads(src, token) {
    return new Promise(resolve => {
      const image = new Image();
      let finished = false;
      const finish = success => {
        if (finished) return;
        finished = true;
        clearTimeout(timeout);
        image.onload = null;
        image.onerror = null;
        resolve(success && token === runToken);
      };
      const timeout = setTimeout(() => finish(false), 9000);
      image.onload = () => finish(true);
      image.onerror = () => finish(false);
      image.src = src;
    });
  }

  async function getReadyPhoto(token) {
    for (let attempt=0; attempt<7; attempt++) {
      if (token !== runToken) return null;
      const candidate = await findCandidate(token);
      if (token !== runToken) return null;
      if (!candidate) return null;
      if (await imageLoads(candidate.url, token)) return candidate;
    }
    return null;
  }

  // Preload just one next photo while the user is thinking, not a whole
  // gallery of images. Keep the promise for early "Next round" clicks.
  function prefetchNextRound() {
    if (prefetchPromise || prefetchedPhoto || !sceneReady ||
        roundIndex + 1 >= settings.rounds) return;
    const token = runToken;
    prefetchPromise = getReadyPhoto(token)
      .then(candidate => {
        if (token === runToken) prefetchedPhoto = candidate;
        return candidate;
      })
      .catch(error => {
        console.warn('Next-round prefetch failed:', error);
        return null;
      })
      .finally(() => {
        if (token === runToken) prefetchPromise = null;
      });
  }

  async function loadRoundPhoto() {
    const token = runToken;
    loading = true;
    sceneReady = false;
    $('photo-loading').classList.remove('hidden');
    $('photo-error').classList.add('hidden');
    userPhoto.hidden = true;
    $('submit-guess').disabled = true;

    let candidate = prefetchedPhoto;
    prefetchedPhoto = null;
    if (!candidate && prefetchPromise) {
      candidate = await prefetchPromise;
      if (token !== runToken) return;
      prefetchedPhoto = null;
    }
    if (!candidate) {
      candidate = await getReadyPhoto(token);
      if (token !== runToken) return;
    }
    if (candidate) {
      photo = candidate;
      userPhoto.src = candidate.url;
      userPhoto.hidden = false;
      $('photo-loading').classList.add('hidden');
      updateCredit(candidate);
      sceneReady = true;
      loading = false;
      $('submit-guess').disabled = !guess;
      startTimer();
      // Defer a little so the current image can paint before networking.
      setTimeout(() => {
        if (token === runToken && sceneReady && !answered) prefetchNextRound();
      }, 650);
      return;
    }
    loading = false;
    $('photo-loading').classList.add('hidden');
    $('photo-error').classList.remove('hidden');
    $('photo-error').querySelector('strong').textContent = 'NO SUITABLE PHOTO COULD BE LOADED';
    $('panel-foot').textContent = 'Commons did not respond with a suitable photo. Try another location.';
  }

  function updateCredit(candidate) {
    const el = $('photo-credit');
    el.replaceChildren();
    el.append(document.createTextNode('PHOTO: '+candidate.author+' · '+candidate.license+' · '));
    const a = document.createElement('a');
    a.href = candidate.source;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.textContent = 'CREDIT / SOURCE ↗';
    el.append(a);
    if (candidate.licenseLink?.startsWith('https://')) {
      const license = document.createElement('a');
      license.href = candidate.licenseLink;
      license.target = '_blank';
      license.rel = 'noopener noreferrer';
      license.textContent = ' · LICENCE ↗';
      el.append(license);
    }
  }

  function makeIcon(actual=false) {
    return L.divIcon({
      className:'pin-icon'+(actual?' actual-icon':''),
      html:'<div></div>', iconSize:[31,31], iconAnchor:[15,30]
    });
  }


  // Use one provider at a time. If its tiles fail, switch once to a separate
  // free, attributed community basemap rather than leaving a checkerboard.
  // Both providers are best-effort; no automated prefetch or cache busting.

  // Community basemaps with clear attribution. OSM France HOT is first,
  // so this small, non-commercial game does not depend on OSMF's volunteer
  // standard tiles as its primary source.
  function addReliableTiles(targetMap, isGuessMap=false) {
    const sources = [
      {
        url:'https://tile.openstreetmap.fr/hot/{z}/{x}/{y}.png',
        attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> · <a href="https://www.openstreetmap.fr/">OSM France / HOT</a>'
      },
      {
        url:'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
      }
    ];
    let activeSource = 0;
    function install(index) {
      let errors = 0;
      const layer = L.tileLayer(sources[index].url, {
        maxZoom:19, keepBuffer:1, updateWhenIdle:true,
        attribution:sources[index].attribution,
        referrerPolicy:'strict-origin-when-cross-origin'
      });
      layer.on('tileerror', () => {
        errors++;
        if (errors >= 3 && index === 0 && activeSource === 0) {
          activeSource = 1;
          targetMap.removeLayer(layer);
          if (isGuessMap && !guess) $('map-hint').textContent = 'TRYING BACKUP MAP…';
          install(1);
        } else if (errors >= 3 && index === 1 && isGuessMap && !guess) {
          $('map-hint').textContent = 'MAP TILES NOT AVAILABLE · TRY AGAIN LATER';
        }
      });
      layer.on('load', () => {
        if (isGuessMap && !guess) $('map-hint').textContent = '↳ TAP THE MAP TO DROP YOUR GUESS';
      });
      layer.addTo(targetMap);
      targetMap._lostInLondonTileLayer = layer;
      return layer;
    }
    return install(0);
  }

  function londonStartZoom() {
    // On small screens this shows more of Greater London at once.
    return window.matchMedia('(max-width: 760px)').matches ? 9 : 10;
  }

  function syncGuessMapSize() {
    if (!map) return;
    map.invalidateSize({pan:false, animate:false});
  }

  function resetGuessMap() {
    if (!map) return;
    // Deliberately avoid maxBounds and panInsideBounds: their snapback was
    // pulling the map around on phones, particularly during a resize.
    map.stop();
    syncGuessMapSize();
    map.setView(LONDON_CENTER, londonStartZoom(), {animate:false});
  }

  function initMap() {
    if (map) {
      setTimeout(resetGuessMap, 70);
      return;
    }
    if (!window.L) {
      $('map-hint').textContent = 'MAP LIBRARY FAILED TO LOAD — REFRESH TO RETRY';
      return;
    }
    map = L.map('map', {
      center:LONDON_CENTER, zoom:londonStartZoom(),
      minZoom:8, maxZoom:18, scrollWheelZoom:false,
      zoomSnap:1, zoomDelta:1, inertia:false, tapTolerance:18
    });
    addReliableTiles(map, true);
    map.on('click', evt => {
      if (!sceneReady || answered) return;
      guess = [evt.latlng.lat,evt.latlng.lng];
      if (!guessMarker) guessMarker = L.marker(guess,{icon:makeIcon()}).addTo(map);
      else guessMarker.setLatLng(guess);
      $('selected-coords').textContent = `${guess[0].toFixed(4)}° N, ${Math.abs(guess[1]).toFixed(4)}° ${guess[1] < 0 ? 'W' : 'E'}`;
      $('map-hint').textContent = 'PIN PLACED — READY TO LOCK IN';
      $('submit-guess').disabled = false;
    });
    // The reset button lives OUTSIDE Leaflet's control container, so it
    // remains visible even if the library styling is unavailable.
    window.addEventListener('resize', () => {
      if (!$('game').classList.contains('hidden')) syncGuessMapSize();
    });
    setTimeout(resetGuessMap, 90);
  }

  $('reset-map').addEventListener('click', resetGuessMap);

  function renderProgress() {
    $('progress-track').replaceChildren();
    for (let i=0;i<settings.rounds;i++) {
      const item = document.createElement('span');
      if (i<roundIndex) item.classList.add('complete');
      else if (i===roundIndex) item.classList.add('active');
      $('progress-track').append(item);
    }
  }

  function stopTimer() {
    clearInterval(timerInterval);
    timerInterval = null;
  }
  function startTimer() {
    stopTimer();
    $('timer-box').hidden = !settings.timer;
    if (!settings.timer) return;
    deadline = Date.now() + settings.timer*1000;
    const tick = () => {
      const seconds = Math.max(0, Math.ceil((deadline-Date.now())/1000));
      $('timer-value').textContent = `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;
      if (seconds===0 && !answered) {
        stopTimer();
        submitGuess(true);
      }
    };
    tick();
    timerInterval = setInterval(tick, 150);
  }

  function resetPhotoZoom() {
    photoZoom = 1;
    panX = 0;
    panY = 0;
    drawPhotoTransform();
  }

  function renderRound() {
    setView('game');
    answered = false;
    guess = null;
    photo = null;
    $('round-label').textContent = `${String(roundIndex+1).padStart(2,'0')} / ${String(settings.rounds).padStart(2,'0')}`;
    $('score-total').textContent = formatNumber(points);
    $('map-hint').textContent = '↳ TAP THE MAP TO DROP YOUR GUESS';
    $('selected-coords').innerHTML = '<span class="pin-small">●</span> NO PIN PLACED YET';
    $('submit-guess').disabled = true;
    $('year-guess').classList.toggle('hidden', settings.type !== 'both');
    $('submit-guess').innerHTML = settings.type === 'both' ? 'LOCK IN WHERE + WHEN <span>→</span>' : 'LOCK IN LOCATION <span>→</span>';
    $('panel-foot').textContent = settings.type === 'both' ? 'The year is checked against the original photo date.' : 'Zoom in for a more precise location guess.';
    updateYear(1988);
    resetPhotoZoom();
    renderProgress();
    stopTimer();
    $('timer-box').hidden = true;
    if (guessMarker && map) map.removeLayer(guessMarker);
    guessMarker = null;
    initMap();
    // Start every round back over London, regardless of the previous pan/zoom.
    setTimeout(resetGuessMap, 110);
    loadRoundPhoto();
  }

  function beginGame() {
    runToken++;
    stopTimer();
    roundIndex = 0;
    points = 0;
    answered = false;
    available = [];
    prefetchedPhoto = null;
    prefetchPromise = null;
    usedSeeds = new Set();
    usedPhotos = new Set();
    renderRound();
  }

  function describeArea(lat, lon) {
    if (haversine(lat,lon,...LONDON_CENTER) < 3.5) return 'CENTRAL LONDON';
    const ns = lat > 51.51 ? 'NORTH' : 'SOUTH';
    const ew = lon > -0.115 ? 'EAST' : 'WEST';
    return `${ns}-${ew} LONDON`;
  }

  function showResultMap() {
    if (!window.L || !guess && !photo) return;
    if (!resultMap) {
      resultMap = L.map('result-map',{scrollWheelZoom:false});
      addReliableTiles(resultMap);
    }
    resultMap.eachLayer(layer => {if (!(layer instanceof L.TileLayer)) resultMap.removeLayer(layer);});
    const target=[photo.lat,photo.lon];
    L.marker(target,{icon:makeIcon(true)}).addTo(resultMap).bindPopup('ACTUAL PHOTO LOCATION');
    if (guess) {
      L.marker(guess,{icon:makeIcon()}).addTo(resultMap).bindPopup('YOUR PIN');
      L.polyline([guess,target],{color:'#d5eeff',weight:3,dashArray:'7,7',opacity:0.8}).addTo(resultMap);
    }
    setTimeout(() => {
      resultMap.invalidateSize({pan:false,animate:false});
      if (guess) {
        const b = L.latLngBounds([guess,target]).pad(0.45);
        resultMap.fitBounds(b,{padding:[44,44],maxZoom:14});
      } else resultMap.setView(target,12);
    },70);
  }

  function submitGuess(expired=false) {
    if (!sceneReady || !photo || answered || (!expired && !guess)) return;
    answered = true;
    stopTimer();
    const distance = guess ? haversine(guess[0],guess[1],photo.lat,photo.lon) : null;
    const locationPoints = distance === null ? 0 : Math.round(5000 * Math.exp(-distance/(settings.area==='central'?3.5:7.5)));
    const yearDifference = photo.year === null ? null : Math.abs(yearValue-photo.year);
    const timePoints = settings.type==='both' && yearDifference !== null ? Math.round(5000*Math.exp(-yearDifference/16)) : 0;
    const earned = locationPoints + timePoints;
    points += earned;
    sceneReady = false;
    $('result-round').textContent = String(roundIndex+1).padStart(2,'0');
    $('result-distance').innerHTML = distance === null ? '— <small>KM</small>' : distance < 1 ? `${Math.round(distance*1000)} <small>M</small>` : `${distance.toFixed(distance<10?2:1)} <small>KM</small>`;
    $('result-headline').textContent = expired && !guess ? 'Time ran out!' : distance !== null && distance<1 ? 'You know your streets.' : distance !== null && distance<5 ? 'Solid London instincts.' : 'The capital is a big place.';
    $('result-subtitle').textContent = expired ? 'The countdown ended. Here’s your round score.' : 'Here’s where the photo was actually taken.';
    $('result-points').textContent = `+${formatNumber(earned)}`;
    $('result-score-max').textContent = `/ ${formatNumber(roundMax())}`;
    $('result-place-points').textContent = `${formatNumber(locationPoints)} / 5,000`;
    $('result-year-points').textContent = `${formatNumber(timePoints)} / 5,000`;
    $('result-time-breakdown').classList.toggle('hidden',settings.type!=='both');
    $('time-reveal').classList.toggle('hidden',settings.type!=='both');
    $('correct-year').textContent = photo.year === null ? 'Unknown' : String(photo.year);
    $('year-delta').textContent = photo.year === null ? '' : `YOUR GUESS: ${yearValue} · ${yearDifference} ${yearDifference===1?'YEAR':'YEARS'} OUT`;
    $('result-location').textContent = photo.title.length>74 ? photo.title.slice(0,71)+'…' : photo.title;
    $('result-area').textContent = describeArea(photo.lat,photo.lon) + ' · '+photo.lat.toFixed(4)+'°, '+photo.lon.toFixed(4)+'°';
    $('next-round').innerHTML = roundIndex+1===settings.rounds ? 'VIEW FINAL SCORE <span>→</span>' : 'NEXT LOCATION <span>→</span>';
    setView('result');
    showResultMap();
  }

  function finishGame() {
    setView('finished');
    const total = settings.rounds*roundMax();
    const portion = points/total;
    $('finish-title').innerHTML = portion>=.80 ? 'LONDON <em>LEGEND.</em>' : portion>=.55 ? 'PROPER <em>LONDONER.</em>' : portion>=.30 ? 'CITY <em>EXPLORER.</em>' : 'KEEP <em>WANDERING.</em>';
    $('finish-desc').textContent = `${settings.rounds} London photo${settings.rounds===1?'':'s'} explored · ${settings.type==='both'?'Locations and years guessed':'Locations guessed'}`;
    $('final-points').textContent = formatNumber(points);
    $('final-max').textContent = '/ '+formatNumber(total)+' PTS';
    const key = `lost-in-london-best-${settings.area}-${settings.type}-${settings.rounds}`;
    let best = 0;
    try {
      best = Number(localStorage.getItem(key)||0);
      if (points>best) {localStorage.setItem(key,String(points));best=points;}
    } catch { /* Browsers may deny storage; the game still works. */ }
    $('best-score').textContent = best ? 'YOUR LOCAL PERSONAL BEST: '+formatNumber(best)+' PTS' : '';
  }

  let photoZoom = 1, panX = 0, panY = 0;
  function drawPhotoTransform() {
    userPhoto.style.transform = `translate(${panX}px,${panY}px) scale(${photoZoom})`;
    $('zoom-indicator').textContent = Math.round(photoZoom*100)+'%';
  }
  function zoom(factor) {
    photoZoom = clamp(Math.round(photoZoom*factor*100)/100,1,4);
    if(photoZoom===1){panX=0;panY=0;}
    drawPhotoTransform();
  }
  $('zoom-in').addEventListener('click',()=>zoom(1.3));
  $('zoom-out').addEventListener('click',()=>zoom(1/1.3));
  const stage = $('photo-stage');
  let drag = null;
  stage.addEventListener('pointerdown',evt=>{
    if (!sceneReady || photoZoom<=1 || evt.target.closest('button,a')) return;
    drag={id:evt.pointerId,x:evt.clientX,y:evt.clientY,ox:panX,oy:panY};
    stage.setPointerCapture(evt.pointerId);
    userPhoto.classList.add('grabbing');
  });
  stage.addEventListener('pointermove',evt=>{
    if(!drag || evt.pointerId!==drag.id)return;
    panX=clamp(drag.ox+evt.clientX-drag.x,-stage.clientWidth*(photoZoom-1)/2,stage.clientWidth*(photoZoom-1)/2);
    panY=clamp(drag.oy+evt.clientY-drag.y,-stage.clientHeight*(photoZoom-1)/2,stage.clientHeight*(photoZoom-1)/2);
    drawPhotoTransform();
  });
  ['pointerup','pointercancel','lostpointercapture'].forEach(type=>stage.addEventListener(type,()=>{
    drag=null;userPhoto.classList.remove('grabbing');
  }));
  stage.addEventListener('wheel',evt=>{
    if(!sceneReady || !evt.ctrlKey) return;
    evt.preventDefault();zoom(evt.deltaY<0?1.15:1/1.15);
  },{passive:false});

  async function share(includeScore) {
    if (location.protocol === 'file:') {
      toast('PUBLISH TO GITHUB PAGES BEFORE SHARING A PUBLIC LINK');
      return;
    }
    const link = location.href.split('#')[0].split('?')[0];
    const text = includeScore
      ? `I scored ${formatNumber(points)} / ${formatNumber(settings.rounds*roundMax())} in LOST IN LONDON — guess where AND when each London photo was taken. Can you beat me?`
      : 'Try LOST IN LONDON! Guess the location and year of real London photos. Free, no login.';
    if (navigator.share) {
      try { await navigator.share({title:'Lost in London',text,url:link}); return; }
      catch (e) { if (e.name==='AbortError') return; }
    }
    const toCopy = text+' '+link;
    try {await navigator.clipboard.writeText(toCopy);toast('LINK COPIED — SEND IT TO YOUR MATES!');}
    catch {window.prompt('Copy this link to share the game:',link);}
  }

  $('start-game').addEventListener('click', beginGame);
  $('restart-button').addEventListener('click',()=>{stopTimer();runToken++;setView('welcome');});
  $('retry-photo').addEventListener('click',()=>{if(!loading)loadRoundPhoto();});
  $('submit-guess').addEventListener('click',()=>submitGuess(false));
  $('next-round').addEventListener('click',()=>{
    roundIndex++;
    if(roundIndex>=settings.rounds)finishGame();
    else renderRound();
  });
  $('play-again').addEventListener('click',()=>{setView('welcome');});
  $('header-share').addEventListener('click',()=>share(false));
  $('share-result').addEventListener('click',()=>share(true));

  // Simple sanity checks in the browser console when developing locally.
  if (new URLSearchParams(location.search).has('debug')) {
    window.LondonGameDebug = {haversine,creationYear,pointInPolygon,inPlayArea};
  }
})();