/* Milwaukee Drinks — see DESIGN.md for the system this respects. */
'use strict';

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const money = c => '$' + (c / 100).toFixed(c % 100 === 0 ? 0 : 2);
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
/* Menus get typed in caps. Lower them so a long list reads evenly. */
const itemName = t => (/[a-z]/.test(t) ? t : t.replace(/([A-Z])([A-Z]+)/g, (m, a, b) => a + b.toLowerCase()));

const DATA = { martini: [], cow: [] };
const COPY = {
  martini: { title: 'Espresso Martinis', sub: 'Every one we can find in the metro, with the price that is on the menu right now.' },
  cow: { title: 'Spotted Cow', sub: 'Where New Glarus is actually on tap or in the cooler, and what the pour costs.' }
};
let LOCKS = 0;
function lockScroll() { if (LOCKS++) return; document.documentElement.style.overflow = 'hidden'; }
function unlockScroll() { if (!LOCKS || --LOCKS) return; document.documentElement.style.overflow = ''; }

const state = { drink: 'martini', query: '', filters: new Set(), sort: 'hood', here: null, prevSort: 'hood' };

/* ── where a spot sits ───────────────────────────────── */
const BOXES = {
  'Deer District': [43.0430, 43.0480, -87.9190, -87.9120],
  'Theater District': [43.0370, 43.0430, -87.9170, -87.9085],
  'Third Ward': [43.0295, 43.0370, -87.9125, -87.9000],
  "Walker's Point": [43.0160, 43.0300, -87.9200, -87.9000],
  'Brady Street': [43.0450, 43.0565, -87.9100, -87.8850],
  'North Avenue': [43.0565, 43.0620, -87.9160, -87.8800],
  'Downtown': [43.0350, 43.0465, -87.9300, -87.8980]
};
const CORE = ['Deer District', 'Theater District', 'Downtown', 'Third Ward', "Walker's Point", 'Brady Street', 'North Avenue'];
function districtOf(s) {
  for (const name of Object.keys(BOXES)) {
    const b = BOXES[name];
    if (s.lat >= b[0] && s.lat <= b[1] && s.lng >= b[2] && s.lng <= b[3]) return name;
  }
  return null;
}
const areaOf = s => districtOf(s) || s.neighborhood || 'Milwaukee';

function milesFrom(here, s) {
  const R = 3958.8, rad = d => d * Math.PI / 180;
  const dLat = rad(s.lat - here.lat), dLng = rad(s.lng - here.lng);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(rad(here.lat)) * Math.cos(rad(s.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}
const milesText = m => (m < 0.1 ? 'right here' : m < 10 ? m.toFixed(1) + ' mi' : Math.round(m) + ' mi');

/* ── prices ──────────────────────────────────────────── */
const priceOf = s => (s.hh_price_cents != null ? s.hh_price_cents : s.price_cents);
const key = s => { const p = priceOf(s); return p == null ? Infinity : p; };
const priceText = s => { const p = priceOf(s); return p == null ? 'Not posted' : money(p); };
function median(list) {
  const p = list.map(priceOf).filter(v => v != null).sort((a, b) => a - b);
  if (!p.length) return null;
  const mid = p.length >> 1;
  return p.length % 2 ? p[mid] : Math.round((p[mid - 1] + p[mid]) / 2);
}
const all = () => DATA[state.drink];
const isUnder = s => { const m = median(all()), p = priceOf(s); return m != null && p != null && p < m; };

/* ── which spots show ────────────────────────────────── */
function keeps(s) {
  const f = state.filters;
  if (f.has('hh') && !s.happy_hour) return false;
  if (f.has('value') && !isUnder(s)) return false;
  const q = state.query.trim().toLowerCase();
  if (!q) return true;
  return s.name.toLowerCase().includes(q)
    || (s.neighborhood || '').toLowerCase().includes(q)
    || areaOf(s).toLowerCase().includes(q)
    || s.items.some(it => it.item.toLowerCase().includes(q));
}
function order() {
  const byName = (a, b) => a.name.localeCompare(b.name);
  const cheap = (a, b) => key(a) - key(b) || byName(a, b);
  if (state.sort === 'name') return byName;
  if (state.sort === 'price') return cheap;
  if (state.sort === 'price-desc') return (a, b) => (key(b) === Infinity ? -1 : key(a) === Infinity ? 1 : key(b) - key(a)) || byName(a, b);
  if (state.sort === 'near' && state.here) return (a, b) => milesFrom(state.here, a) - milesFrom(state.here, b);
  return cheap;
}
const showing = () => all().filter(keeps).sort(order());

/* ── rendering the list ──────────────────────────────── */
function chapters(list) {
  if (state.sort !== 'hood') return [[null, list]];
  const bucket = new Map();
  list.forEach(s => {
    const a = areaOf(s);
    if (!bucket.has(a)) bucket.set(a, []);
    bucket.get(a).push(s);
  });
  const core = CORE.filter(n => bucket.has(n)).map(n => [n, bucket.get(n)]);
  core.forEach(([n]) => bucket.delete(n));
  const named = [...bucket.entries()].filter(([, l]) => l.length >= 3).sort((a, b) => b[1].length - a[1].length);
  named.forEach(([n]) => bucket.delete(n));
  const rest = [...bucket.values()].flat().sort(order());
  const out = core.concat(named);
  if (rest.length) out.push(['Elsewhere in the metro', rest]);
  return out;
}

/* On the Cow tab every line says "Spotted Cow", so the useful thing to carry in
   the meta is how they pour it, not the name of the beer again. */
function servedAs(s) {
  const t = s.items.map(i => i.item).join(' ').toLowerCase();
  const tap = /draft|tap/.test(t), pack = /bottle|can/.test(t);
  return tap && pack ? 'Tap, bottle or can' : tap ? 'On tap' : pack ? 'Bottle or can' : '';
}
function rowHtml(s, low) {
  const p = priceOf(s);
  const bits = [areaOf(s)];
  if (state.here) bits.push(milesText(milesFrom(state.here, s)));
  if (state.drink === 'cow') {
    const how = servedAs(s);
    if (how) bits.push(how);
  } else {
    bits.push(s.items.length > 1 ? s.items.length + ' listings' : itemName(s.items[0].item));
  }
  let tag = '';
  if (s.hh_price_cents != null) tag = 'Happy-hour price';
  else if (low != null && p === low) tag = 'Cheapest here';
  else if (s.happy_hour) tag = 'Happy hour';
  return `<li><button class="row rise" type="button" data-guid="${esc(s.guid)}">
    <span class="row-name">${esc(s.name)}</span>
    <span class="row-price${p == null ? ' none' : ''}">${priceText(s)}</span>
    <span class="row-meta">${esc(bits.join(' · '))}</span>
    <span class="row-tag">${tag}</span>
  </button></li>`;
}

function renderList() {
  const list = showing();
  const box = $('#results');
  if (!list.length) {
    box.innerHTML = `<div class="blank">
      <h3>Nothing here matches.</h3>
      <p>Try a different name, or start the list over.</p>
      <button class="linkish" type="button" id="start-over">Clear everything</button>
    </div>`;
    $('#start-over').addEventListener('click', clearAll);
    tally(list);
    drawPins();
    return;
  }
  box.innerHTML = chapters(list).map(([name, spots]) => {
    const head = name ? `<div class="chapter"><h2>${esc(name)}</h2><span class="rule"></span><span class="n">${spots.length}</span></div>` : '';
    const low = Math.min(...spots.map(key));
    const mark = name && spots.length >= 3 && Number.isFinite(low) ? low : null;
    return head + `<ul class="rows">${spots.map(s => rowHtml(s, mark)).join('')}</ul>`;
  }).join('');
  box.querySelectorAll('.row').forEach(el => {
    const guid = el.dataset.guid;
    el.addEventListener('click', () => openDetail(guid));
    el.addEventListener('mouseenter', () => setLive(guid, false));
    el.addEventListener('mouseleave', () => setLive(null, false));
    el.addEventListener('focus', () => setLive(guid, false));
  });
  riseIn(box);
  tally(list);
  drawPins();
}

function tally(list) {
  const prices = list.map(priceOf).filter(p => p != null).sort((a, b) => a - b);
  const el = $('#tally');
  const noun = state.drink === 'martini' ? 'espresso martinis' : 'Spotted Cow pours';
  if (!list.length) { el.innerHTML = `No ${noun} match that.`; return; }
  const bits = [`<b>${list.length}</b> ${list.length === 1 ? 'spot' : 'spots'}`];
  if (prices.length) {
    bits.push(prices[0] === prices[prices.length - 1]
      ? `all at <b>${money(prices[0])}</b>`
      : `<b>${money(prices[0])}</b> to <b>${money(prices[prices.length - 1])}</b>`);
    bits.push(`median <b>${money(median(list))}</b>`);
  }
  const blank = list.length - prices.length;
  if (blank) bits.push(`${blank} with no posted price`);
  el.innerHTML = bits.join(' &nbsp;·&nbsp; ');
}

/* Rows lift in as they arrive on screen, in small waves. */
let RISE = null;
function riseIn(scope) {
  const els = [...scope.querySelectorAll('.rise')];
  if (REDUCED) { els.forEach(el => el.classList.add('set')); return; }
  if (RISE) RISE.disconnect();
  RISE = new IntersectionObserver((entries, obs) => {
    let i = 0;
    entries.forEach(e => {
      if (!e.isIntersecting) return;
      e.target.style.transitionDelay = Math.min(i++, 10) * 26 + 'ms';
      e.target.classList.add('set');
      obs.unobserve(e.target);
    });
  }, { rootMargin: '0px 0px -5% 0px', threshold: 0.03 });
  els.forEach(el => RISE.observe(el));
}

/* ── the cover ───────────────────────────────────────── */
function countTo(el, to, fmt) {
  const from = el._v || 0;
  el._v = to;
  if (REDUCED || from === to) { el.textContent = fmt(to); return; }
  const t0 = performance.now(), ms = 620;
  (function step(t) {
    const k = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - k, 3);
    el.textContent = fmt(Math.round(from + (to - from) * e));
    if (k < 1) requestAnimationFrame(step);
  })(performance.now());
}
let COVER_SEEN = false;
function renderIndex(animate) {
  const list = all();
  const prices = list.map(priceOf).filter(p => p != null);
  const put = (k, to, fmt) => {
    const el = $(`[data-stat="${k}"]`);
    if (animate && COVER_SEEN) countTo(el, to, fmt); else { el._v = to; el.textContent = fmt(to); }
  };
  put('spots', list.length, v => String(v));
  put('low', prices.length ? Math.min(...prices) : 0, v => (prices.length ? money(v) : '—'));
  put('median', median(list) || 0, v => (prices.length ? money(v) : '—'));
  put('hh', list.filter(s => s.happy_hour).length, v => String(v));
}

function drawGlass(svg) {
  if (REDUCED || !svg) return;
  [...svg.children].forEach((el, i) => {
    let len = 320;
    try { len = el.getTotalLength() || 320; } catch (err) { /* older engines */ }
    el.style.strokeDasharray = len;
    el.style.strokeDashoffset = len;
    el.style.animation = 'none';
    void el.getBoundingClientRect();
    el.style.animation = `draw var(--t-draw) var(--in) ${i * 70}ms forwards`;
  });
}

/* ── changing rooms ──────────────────────────────────── */
function glide() {
  const on = $('.switch button.on'), g = $('.switch-glide');
  if (!on) return;
  g.style.width = on.offsetWidth + 'px';
  g.style.transform = `translateX(${on.offsetLeft - 3}px)`;
}
function setDrink(drink) {
  if (state.drink === drink || !DATA[drink].length) return;
  state.drink = drink;
  document.body.dataset.drink = drink;
  $('#pick-martini').classList.toggle('on', drink === 'martini');
  $('#pick-cow').classList.toggle('on', drink === 'cow');
  $('#pick-martini').setAttribute('aria-pressed', String(drink === 'martini'));
  $('#pick-cow').setAttribute('aria-pressed', String(drink === 'cow'));
  glide();
  closeDetail();

  const t = $('#cover-title');
  t.classList.add('out');
  setTimeout(() => {
    t.textContent = COPY[drink].title;
    $('#cover-sub').textContent = COPY[drink].sub;
    t.classList.remove('out');
  }, REDUCED ? 0 : 260);
  drawGlass($(drink === 'martini' ? '.glass-coupe' : '.glass-pint'));

  const col = $('#results');
  col.classList.add('swapping');
  setTimeout(() => {
    renderList();
    renderIndex(true);
    col.classList.remove('swapping');
  }, REDUCED ? 0 : 240);
}
$('#pick-martini').addEventListener('click', () => setDrink('martini'));
$('#pick-cow').addEventListener('click', () => setDrink('cow'));
addEventListener('resize', glide);

/* ── the detail panel ────────────────────────────────── */
let CAME_FROM = null;
function openDetail(guid) {
  const s = all().find(x => x.guid === guid);
  if (!s) return;
  const panel = $('#detail'), scrim = $('#scrim');
  const lines = s.items.map(it => {
    const reg = it.price_cents != null ? money(it.price_cents) : null;
    const hh = it.hh_price_cents != null ? money(it.hh_price_cents) : null;
    const fig = hh
      ? `<b class="under">${hh}</b><small>Happy hour</small>${reg ? `<s>${reg} otherwise</s>` : ''}`
      : `<b${reg && isUnder(s) ? ' class="under"' : ''}>${reg || 'Not posted'}</b>`;
    return `<div class="detail-line"><span>${esc(itemName(it.item))}</span><span class="fig">${fig}</span></div>`;
  }).join('');
  const dist = state.here ? ' · ' + milesText(milesFrom(state.here, s)) : '';
  panel.innerHTML = `
    <button class="detail-x" type="button" aria-label="Close"><svg class="icon" aria-hidden="true"><use href="#i-close"></use></svg></button>
    <h3 id="detail-name">${esc(s.name)}</h3>
    <p class="detail-where"><svg class="icon" aria-hidden="true"><use href="#i-pin"></use></svg>${esc(areaOf(s) + dist)}</p>
    <div class="detail-lines">${lines}</div>
    <p class="detail-addr">${esc(s.address || '')}</p>
    ${s.notes ? `<p class="detail-said">${esc(s.notes)}</p>` : ''}
    <div class="detail-acts">
      <a class="act" href="https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(s.name + ' ' + (s.address || ''))}" target="_blank" rel="noopener">Directions</a>
      <button class="act ghost" type="button" data-find="${esc(s.guid)}">Find it on the map</button>
    </div>
    ${s.source_url ? `<p class="detail-src"><a href="${esc(s.source_url)}" target="_blank" rel="noopener">Where this price came from</a></p>` : ''}`;

  CAME_FROM = document.activeElement;
  scrim.hidden = false; panel.hidden = false;
  void panel.getBoundingClientRect();
  scrim.classList.add('open'); panel.classList.add('open');
  lockScroll();
  panel.querySelector('.detail-x').addEventListener('click', closeDetail);
  panel.querySelector('[data-find]').addEventListener('click', () => { closeDetail(); findOnMap(guid); });
  panel.querySelector('.detail-x').focus();
  setLive(guid, true);
}
function closeDetail() {
  const panel = $('#detail'), scrim = $('#scrim');
  if (panel.hidden) return;
  panel.classList.remove('open'); scrim.classList.remove('open');
  unlockScroll();
  setTimeout(() => { panel.hidden = true; scrim.hidden = true; }, REDUCED ? 0 : 420);
  if (CAME_FROM && CAME_FROM.isConnected) CAME_FROM.focus();
}
$('#scrim').addEventListener('click', closeDetail);
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { if (!$('#detail').hidden) closeDetail(); else closeSheet(); return; }
  const panel = $('#detail');
  if (e.key !== 'Tab' || panel.hidden) return;
  const f = panel.querySelectorAll('button, a[href]');
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
});

/* ── the map ─────────────────────────────────────────── */
let MAP = null, PINS = {}, LIVE = null, TAGGED = false;
function bootMap() {
  if (MAP) return;
  MAP = L.map('map', { scrollWheelZoom: false, zoomControl: true, attributionControl: true });
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
  }).addTo(MAP);
  MAP.on('click', () => MAP.scrollWheelZoom.enable());
  MAP.on('mouseout', () => MAP.scrollWheelZoom.disable());
  MAP.on('zoomend', () => { const want = MAP.getZoom() >= 15; if (want !== TAGGED) { TAGGED = want; dressPins(); } });
  drawPins();
}
function iconFor(s, live) {
  const cls = live ? ' live' : '';
  return TAGGED
    ? L.divIcon({ className: '', html: `<span class="tagged${cls}">${priceText(s) === 'Not posted' ? '—' : priceText(s)}</span>`, iconSize: null, iconAnchor: [24, 13] })
    : L.divIcon({ className: '', html: `<span class="dot${cls}"></span>`, iconSize: [11, 11], iconAnchor: [5.5, 5.5] });
}
function dressPins() {
  Object.entries(PINS).forEach(([guid, m]) => m.setIcon(iconFor(m._spot, guid === LIVE)));
}
function popHtml(s) {
  const hh = s.hh_price_cents != null;
  return `<div class="pop-name">${esc(s.name)}</div>
    <div class="pop-meta">${esc(areaOf(s))}${state.here ? ' · ' + milesText(milesFrom(state.here, s)) : ''}</div>
    <div class="pop-price${hh ? ' hh' : ''}">${priceText(s)}${hh ? ' happy hour' : ''}</div>
    <button class="pop-open" type="button" data-open="${esc(s.guid)}">See the menu lines</button>`;
}
function drawPins() {
  if (!MAP) return;
  Object.values(PINS).forEach(m => m.remove());
  PINS = {}; LIVE = null;
  const list = showing();
  list.forEach(s => {
    const m = L.marker([s.lat, s.lng], { icon: iconFor(s, false), title: s.name, riseOnHover: true });
    m._spot = s;
    m.bindPopup(popHtml(s));
    m.on('mouseover', () => setLive(s.guid, false));
    m.on('mouseout', () => setLive(null, false));
    m.on('click', () => { setLive(s.guid, true); scrollRowTo(s.guid); });
    m.addTo(MAP);
    PINS[s.guid] = m;
  });
  $('#map-note').textContent = list.length
    ? (MAP.getZoom() >= 15 ? 'Prices shown. Zoom out for the whole metro.' : 'Zoom in to read the prices.')
    : 'Nothing to pin right now.';
  frame(list);
}
/* Frame the central bars when there are enough of them: fitting the whole metro
   leaves the tall map column mostly empty field. */
function frame(list) {
  const set = list || showing();
  if (!set.length || !MAP) return;
  const core = set.filter(s => districtOf(s) !== null || s.downtown === true);
  const pts = (core.length >= 6 ? core : set).map(s => [s.lat, s.lng]);
  MAP.invalidateSize();
  MAP.fitBounds(L.latLngBounds(pts).pad(0.14), { animate: false });
}
/* One highlight, shared by the row and its pin, in both directions. */
function setLive(guid, hard) {
  if (LIVE === guid && !hard) return;
  const was = LIVE;
  LIVE = guid;
  [was, guid].forEach(g => {
    if (!g) return;
    const row = document.querySelector(`.row[data-guid="${CSS.escape(g)}"]`);
    if (row) row.classList.toggle('live', g === guid);
    if (PINS[g]) PINS[g].setIcon(iconFor(PINS[g]._spot, g === guid));
  });
  if (hard && guid && PINS[guid] && MAP) {
    MAP.panTo(PINS[guid].getLatLng(), { animate: !REDUCED, duration: 0.5 });
  }
}
function scrollRowTo(guid) {
  const row = document.querySelector(`.row[data-guid="${CSS.escape(guid)}"]`);
  if (row) row.scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: 'center' });
}
function findOnMap(guid) {
  const wide = matchMedia('(min-width: 1080px)').matches;
  if (!wide) openSheet(guid);
  else {
    bootMap();
    const m = PINS[guid];
    if (!m) return;
    setLive(guid, true);
    MAP.flyTo(m.getLatLng(), 16, { duration: REDUCED ? 0 : 0.8 });
    setTimeout(() => m.openPopup(), REDUCED ? 0 : 850);
  }
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-open]');
  if (b) openDetail(b.dataset.open);
});

/* The map is one instance; the phone sheet borrows it and gives it back. */
function openSheet(guid) {
  const sheet = $('#sheet-map');
  bootMap();
  $('#sheet-hold').appendChild($('#map'));
  sheet.hidden = false;
  void sheet.getBoundingClientRect();
  sheet.classList.add('open');
  lockScroll();
  setTimeout(() => {
    MAP.invalidateSize();
    if (guid && PINS[guid]) { setLive(guid, true); MAP.flyTo(PINS[guid].getLatLng(), 16, { duration: REDUCED ? 0 : 0.8 }); setTimeout(() => PINS[guid].openPopup(), REDUCED ? 0 : 850); }
    else frame();
  }, REDUCED ? 0 : 120);
}
function closeSheet() {
  const sheet = $('#sheet-map');
  if (sheet.hidden) return;
  sheet.classList.remove('open');
  unlockScroll();
  setTimeout(() => {
    sheet.hidden = true;
    $('.map-hold').insertBefore($('#map'), $('#map-note'));
    if (MAP) MAP.invalidateSize();
  }, REDUCED ? 0 : 420);
}
$('#bar-map').addEventListener('click', () => openSheet());
$('#sheet-close').addEventListener('click', closeSheet);

/* ── controls ────────────────────────────────────────── */
function syncToggles() {
  $$('.toggle').forEach(t => {
    const on = t.dataset.filter === 'near' ? state.sort === 'near' : state.filters.has(t.dataset.filter);
    t.setAttribute('aria-pressed', String(on));
  });
  $('#sort').value = state.sort;
}
function clearAll() {
  state.filters.clear();
  state.query = '';
  if (state.sort === 'near') state.sort = state.prevSort;
  $('#find').value = ''; $('#find-clear').hidden = true;
  syncToggles(); renderList();
}
$('.toggles').addEventListener('click', e => {
  const t = e.target.closest('.toggle');
  if (!t) return;
  const f = t.dataset.filter;
  if (f === 'near') { toggleNear(t); return; }
  state.filters.has(f) ? state.filters.delete(f) : state.filters.add(f);
  syncToggles(); renderList();
});
function toggleNear(btn) {
  if (state.sort === 'near') { state.sort = state.prevSort; syncToggles(); renderList(); return; }
  if (state.here) { state.prevSort = state.sort; state.sort = 'near'; syncToggles(); renderList(); return; }
  if (!navigator.geolocation) { $('#tally').textContent = 'This browser will not share a location.'; return; }
  btn.dataset.state = 'working';
  navigator.geolocation.getCurrentPosition(pos => {
    delete btn.dataset.state;
    state.here = { lat: pos.coords.latitude, lng: pos.coords.longitude };
    if (!$('#sort').querySelector('[value="near"]')) {
      const opt = document.createElement('option');
      opt.value = 'near'; opt.textContent = 'Nearest to me';
      $('#sort').appendChild(opt);
    }
    state.prevSort = state.sort;
    state.sort = 'near';
    syncToggles(); renderList();
  }, () => {
    delete btn.dataset.state;
    $('#tally').textContent = 'No location shared, so the list stays as it was.';
  }, { timeout: 9000, maximumAge: 300000 });
}
let FIND_T = null;
$('#find').addEventListener('input', e => {
  state.query = e.target.value;
  $('#find-clear').hidden = !state.query;
  clearTimeout(FIND_T);
  FIND_T = setTimeout(renderList, 130);
});
$('#find-clear').addEventListener('click', () => {
  state.query = ''; $('#find').value = ''; $('#find-clear').hidden = true;
  $('#find').focus(); renderList();
});
$('#sort').addEventListener('change', e => {
  if (e.target.value !== 'near') state.prevSort = e.target.value;
  state.sort = e.target.value;
  syncToggles(); renderList();
});
$('#cue').addEventListener('click', () => $('#list').scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: 'start' }));

/* ── chrome ──────────────────────────────────────────── */
function measure() {
  const r = document.documentElement.style;
  r.setProperty('--bar-h', $('#bar').offsetHeight + 'px');
  r.setProperty('--tools-h', $('#tools').offsetHeight + 'px');
}
addEventListener('resize', () => { measure(); glide(); });
measure();

let ticking = false;
addEventListener('scroll', () => {
  if (ticking) return;
  ticking = true;
  requestAnimationFrame(() => { document.body.classList.toggle('moved', scrollY > 8); ticking = false; });
}, { passive: true });

new IntersectionObserver((entries, obs) => {
  if (entries.some(e => e.isIntersecting)) { obs.disconnect(); COVER_SEEN = true; renderIndex(true); }
}, { threshold: 0.4 }).observe($('#index'));

new IntersectionObserver((entries, obs) => {
  if (entries.some(e => e.isIntersecting)) { obs.disconnect(); bootMap(); }
}, { rootMargin: '400px' }).observe($('#list'));

/* ── boot ────────────────────────────────────────────── */
const bust = 'v=' + Date.now();
Promise.all([
  fetch(`data/martinis.json?${bust}`).then(r => r.json()),
  fetch(`data/cow.json?${bust}`).then(r => r.json())
]).then(([m, c]) => {
  DATA.martini = m.martinis || [];
  DATA.cow = c.cows || [];
  const when = new Date(m.generated_at);
  const text = when.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric', timeZone: 'America/Chicago' });
  $('#swept').textContent = text;
  $('#swept').dateTime = when.toISOString().slice(0, 10);
  renderIndex(false);
  renderList();
  glide();
  measure();
  drawGlass($('.glass-coupe'));
}).catch(() => {
  $('#tally').textContent = 'The list could not be loaded. Reload the page to try again.';
});
if (document.fonts) document.fonts.ready.then(() => { glide(); measure(); });
