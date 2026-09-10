/* Milwaukee Drinks — index behaviour. See DESIGN.md for the tokens this respects. */
'use strict';

const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const money = c => '$' + (c / 100).toFixed(c % 100 === 0 ? 0 : 2);
/* Some menus are typed in caps. Lowercase them so a list of 96 rows reads evenly. */
const itemName = t => (/[a-z]/.test(t) ? t : t.replace(/([A-Z])([A-Z]+)/g, (m, a, b) => a + b.toLowerCase()));
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;

const DATA = { martinis: [], cow: [] };
const LABEL = { martinis: 'espresso martinis', cow: 'Spotted Cow pours' };
const state = { tab: 'martinis', query: '', filters: new Set(), sort: 'price' };

/* ---------- districts ---------- */
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
const isCentral = s => districtOf(s) !== null || s.downtown === true;

/* ---------- price helpers ---------- */
const priceOf = s => (s.hh_price_cents != null ? s.hh_price_cents : s.price_cents);
const sortKey = s => { const p = priceOf(s); return p == null ? Infinity : p; };
const priceText = s => { const p = priceOf(s); return p == null ? 'Not posted' : money(p); };
function median(list) {
  const p = list.map(priceOf).filter(v => v != null).sort((a, b) => a - b);
  if (!p.length) return null;
  const mid = p.length >> 1;
  return p.length % 2 ? p[mid] : Math.round((p[mid - 1] + p[mid]) / 2);
}
const current = () => DATA[state.tab];

/* ---------- filtering ---------- */
function matches(s) {
  const f = state.filters;
  if (f.has('hh') && !s.happy_hour) return false;
  if (f.has('downtown') && !isCentral(s)) return false;
  if (f.has('value')) {
    const m = median(current());
    const p = priceOf(s);
    if (m == null || p == null || p > m) return false;
  }
  const q = state.query.trim().toLowerCase();
  if (!q) return true;
  return s.name.toLowerCase().includes(q)
    || (s.neighborhood || '').toLowerCase().includes(q)
    || areaOf(s).toLowerCase().includes(q)
    || s.items.some(it => it.item.toLowerCase().includes(q));
}
function comparator() {
  if (state.sort === 'name') return (a, b) => a.name.localeCompare(b.name);
  if (state.sort === 'price-desc') return (a, b) => (sortKey(b) === Infinity ? -1 : sortKey(a) === Infinity ? 1 : sortKey(b) - sortKey(a)) || a.name.localeCompare(b.name);
  return (a, b) => sortKey(a) - sortKey(b) || a.name.localeCompare(b.name);
}
const shown = () => current().filter(matches).sort(comparator());

/* ---------- results ---------- */
function groupsOf(list) {
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
  const rest = [...bucket.values()].flat().sort(comparator());
  const out = core.concat(named);
  if (rest.length) out.push(['Around the metro', rest]);
  return out;
}

function spotHtml(s, best) {
  const p = priceOf(s);
  const isBest = best != null && p === best;
  const items = s.items.length;
  const meta = [areaOf(s), items > 1 ? items + ' listings' : (s.items[0] && itemName(s.items[0].item))].filter(Boolean).join(' · ');
  let flag = '';
  if (s.hh_price_cents != null) flag = 'Happy hour';
  else if (isBest) flag = 'Cheapest here';
  return `<button class="spot reveal${isBest ? ' best' : ''}" type="button" data-guid="${esc(s.guid)}">
    <span class="spot-name">${esc(s.name)}</span>
    <span class="spot-price"><b>${priceText(s)}</b></span>
    <span class="spot-meta">${esc(meta)}</span>
    <span class="spot-flag">${flag}</span>
  </button>`;
}

function renderResults() {
  const list = shown();
  const box = $('#results');
  if (!list.length) {
    box.innerHTML = `<div class="empty">
      <h3>Nothing matches that yet.</h3>
      <p>Try a different name, or clear the filters and start over.</p>
      <button class="btn btn-outline" type="button" id="reset-all">Clear filters</button>
    </div>`;
    $('#reset-all').addEventListener('click', resetFilters);
    updateResultLine(list);
    return;
  }
  box.innerHTML = groupsOf(list).map(([name, spots]) => {
    const best = Math.min(...spots.map(sortKey));
    return `<div class="group-head"><h3>${esc(name)}</h3><span class="count">${spots.length} ${spots.length === 1 ? 'spot' : 'spots'}</span></div>
      <div class="spot-list">${spots.map(s => spotHtml(s, Number.isFinite(best) ? best : null)).join('')}</div>`;
  }).join('');
  box.querySelectorAll('.spot').forEach(el => el.addEventListener('click', () => openPanel(el.dataset.guid)));
  revealIn(box);
  updateResultLine(list);
  if (MAP) renderPins();
}

function updateResultLine(list) {
  const prices = list.map(priceOf).filter(p => p != null).sort((a, b) => a - b);
  const line = $('#result-line');
  if (!list.length) { line.innerHTML = `No ${LABEL[state.tab]} match those filters.`; return; }
  const bits = [`<b>${list.length}</b> ${list.length === 1 ? 'spot' : 'spots'}`];
  if (prices.length) {
    bits.push(prices[0] === prices[prices.length - 1] ? `all at <b>${money(prices[0])}</b>` : `<b>${money(prices[0])}</b> to <b>${money(prices[prices.length - 1])}</b>`);
    bits.push(`median <b>${money(median(list))}</b>`);
  }
  const noPrice = list.length - prices.length;
  if (noPrice) bits.push(`${noPrice} with no posted price`);
  line.innerHTML = bits.join(' · ');
}

/* Rows fade up as they reach the viewport, staggered in small batches so a
   96-row list arrives in waves instead of one long queue. */
let REVEAL_OBS = null;
function revealIn(scope) {
  const els = [...scope.querySelectorAll('.reveal')];
  if (REDUCED) { els.forEach(el => el.classList.add('shown')); return; }
  if (REVEAL_OBS) REVEAL_OBS.disconnect();
  REVEAL_OBS = new IntersectionObserver((entries, obs) => {
    let i = 0;
    entries.forEach(e => {
      if (!e.isIntersecting) return;
      e.target.style.transitionDelay = Math.min(i++, 8) * 28 + 'ms';
      e.target.classList.add('shown');
      obs.unobserve(e.target);
    });
  }, { rootMargin: '0px 0px -6% 0px', threshold: 0.04 });
  els.forEach(el => REVEAL_OBS.observe(el));
}

/* ---------- hero card + stats ---------- */
function renderHero() {
  const list = current().filter(s => priceOf(s) != null).sort((a, b) => sortKey(a) - sortKey(b)).slice(0, 3);
  $('.art-head span').textContent = state.tab === 'martinis' ? 'Cheapest espresso martinis' : 'Cheapest Spotted Cow';
  $('#hero-list').innerHTML = list.map((s, i) => `<li class="art-row" data-guid="${esc(s.guid)}" role="button" tabindex="0">
      <span class="art-rank">${i + 1}</span>
      <span class="art-name">${esc(s.name)}</span>
      <span class="art-price">${priceText(s)}</span>
    </li>`).join('');
  $$('#hero-list .art-row').forEach(el => {
    const open = () => openPanel(el.dataset.guid);
    el.addEventListener('click', open);
    el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
  });
  const m = median(current());
  $('#hero-foot').textContent = m != null ? `Metro median right now: ${money(m)}` : 'Prices from the latest sweep';
  $('#hero-chip').textContent = `${current().length} spots mapped`;
  $('#fact-spots').textContent = `${DATA.martinis.length + DATA.cow.length} spots tracked`;
}

function countUp(el, to, fmt) {
  const from = el._v || 0;
  el._v = to;
  if (REDUCED || from === to) { el.textContent = fmt(to); return; }
  const t0 = performance.now(), dur = 520;
  (function step(t) {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    el.textContent = fmt(Math.round(from + (to - from) * e));
    if (k < 1) requestAnimationFrame(step);
  })(performance.now());
}
let STATS_SEEN = false;
function renderStats(animate) {
  const list = current();
  const prices = list.map(priceOf).filter(p => p != null);
  const set = (key, to, fmt) => {
    const el = $(`[data-stat="${key}"]`);
    if (animate && STATS_SEEN) countUp(el, to, fmt); else { el._v = to; el.textContent = fmt(to); }
  };
  set('spots', list.length, v => String(v));
  set('median', median(list) || 0, v => (prices.length ? money(v) : '—'));
  set('cheapest', prices.length ? Math.min(...prices) : 0, v => (prices.length ? money(v) : '—'));
  set('hh', list.filter(s => s.happy_hour).length, v => String(v));
}

/* ---------- detail panel ---------- */
let LAST_FOCUS = null;
function openPanel(guid) {
  const s = current().find(x => x.guid === guid);
  if (!s) return;
  const panel = $('#panel'), scrim = $('#scrim');
  const lines = s.items.map(it => {
    const reg = it.price_cents != null ? money(it.price_cents) : null;
    const hh = it.hh_price_cents != null ? money(it.hh_price_cents) : null;
    const stack = hh
      ? `<b class="hh">${hh}</b><small>Happy hour</small>${reg ? `<s>${reg} otherwise</s>` : ''}`
      : `<b>${reg || 'Not posted'}</b>`;
    return `<div class="panel-item"><span>${esc(itemName(it.item))}</span><span class="stack">${stack}</span></div>`;
  }).join('');
  panel.innerHTML = `
    <button class="panel-close" type="button" aria-label="Close"><svg class="icon" aria-hidden="true"><use href="#i-close"></use></svg></button>
    <h3 id="panel-name">${esc(s.name)}</h3>
    <p class="panel-hood"><svg class="icon" aria-hidden="true"><use href="#i-pin"></use></svg>${esc(areaOf(s))}</p>
    <div class="panel-items">${lines}</div>
    <p class="panel-addr">${esc(s.address || '')}</p>
    ${s.notes ? `<p class="panel-notes">${esc(s.notes)}</p>` : ''}
    <div class="panel-actions">
      <button class="btn btn-primary" type="button" data-map="${esc(s.guid)}"><svg class="icon" aria-hidden="true"><use href="#i-pin"></use></svg><span>Show on the map</span></button>
      <a class="btn btn-outline" href="https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(s.name + ' ' + (s.address || ''))}" target="_blank" rel="noopener"><span>Directions</span></a>
    </div>
    ${s.source_url ? `<p class="panel-src"><a class="text-link" href="${esc(s.source_url)}" target="_blank" rel="noopener">Menu source <svg class="icon" aria-hidden="true"><use href="#i-link"></use></svg></a></p>` : ''}`;

  LAST_FOCUS = document.activeElement;
  scrim.hidden = false; panel.hidden = false;
  void panel.offsetHeight;
  scrim.classList.add('open'); panel.classList.add('open');
  document.body.style.overflow = 'hidden';
  panel.querySelector('.panel-close').addEventListener('click', closePanel);
  panel.querySelector('[data-map]').addEventListener('click', () => { closePanel(); focusOnMap(s.guid); });
  panel.querySelector('.panel-close').focus();
}
function closePanel() {
  const panel = $('#panel'), scrim = $('#scrim');
  if (panel.hidden) return;
  panel.classList.remove('open'); scrim.classList.remove('open');
  document.body.style.overflow = '';
  setTimeout(() => { panel.hidden = true; scrim.hidden = true; }, REDUCED ? 0 : 320);
  if (LAST_FOCUS && LAST_FOCUS.isConnected) LAST_FOCUS.focus();
}
$('#scrim').addEventListener('click', closePanel);
document.addEventListener('keydown', e => {
  const panel = $('#panel');
  if (e.key === 'Escape') { closePanel(); return; }
  if (e.key !== 'Tab' || panel.hidden) return;
  const f = panel.querySelectorAll('button, a[href], input, select');
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
});

/* ---------- map ---------- */
let MAP = null, CLUSTER = null, MARKERS = {}, PENDING = null;
function initMap() {
  if (MAP) return;
  MAP = L.map('map', { scrollWheelZoom: false, zoomControl: true });
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
  }).addTo(MAP);
  MAP.on('click', () => MAP.scrollWheelZoom.enable());
  MAP.on('mouseout', () => MAP.scrollWheelZoom.disable());
  CLUSTER = L.markerClusterGroup({
    showCoverageOnHover: false,
    spiderfyDistanceMultiplier: 1.4,
    maxClusterRadius: 46,
    disableClusteringAtZoom: 17,
    iconCreateFunction: c => {
      const n = c.getChildCount();
      return L.divIcon({ className: '', html: `<span class="cluster-pin${n > 9 ? ' lg' : ''}">${n}</span>`, iconSize: null, iconAnchor: [19, 19] });
    }
  }).addTo(MAP);
  renderPins();
  if (PENDING) { focusOnMap(PENDING); PENDING = null; }
}
function popupHtml(s) {
  const lines = s.items.map(it => {
    const reg = it.price_cents != null ? money(it.price_cents) : 'Not posted';
    const hh = it.hh_price_cents != null ? `<b class="hh">${money(it.hh_price_cents)} hh</b>` : `<b>${reg}</b>`;
    return `<div class="pop-line"><span>${esc(itemName(it.item))}</span>${hh}</div>`;
  }).join('');
  return `<div class="pop-name">${esc(s.name)}</div><div class="pop-meta">${esc(areaOf(s))}</div>${lines}`;
}
function renderPins(refit) {
  if (!MAP) return;
  CLUSTER.clearLayers();
  MARKERS = {};
  const list = shown();
  const prices = list.map(priceOf).filter(p => p != null);
  const best = prices.length ? Math.min(...prices) : null;
  list.forEach(s => {
    const isBest = best != null && priceOf(s) === best;
    const icon = L.divIcon({
      className: 'pin-wrap',
      html: `<span class="price-pin${isBest ? ' best' : ''}">${priceText(s) === 'Not posted' ? '—' : priceText(s)}</span>`,
      iconSize: null, iconAnchor: [22, 14]
    });
    MARKERS[s.guid] = L.marker([s.lat, s.lng], { icon, title: s.name }).bindPopup(popupHtml(s));
  });
  CLUSTER.addLayers(Object.values(MARKERS));
  if (refit !== false) frame(list);
}
/* Open on the central bars, where most of the pins are, instead of a metro-wide
   view where 60 price chips land on top of each other. */
function frame(list, all) {
  const set = list || shown();
  const central = set.filter(isCentral);
  const pts = (!all && central.length >= 6 ? central : set).map(s => [s.lat, s.lng]);
  if (!pts.length) return;
  MAP.invalidateSize();
  MAP.fitBounds(L.latLngBounds(pts).pad(0.16), { animate: false });
}
function focusOnMap(guid) {
  const section = $('#map-section');
  section.scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: 'start' });
  if (!MAP) { PENDING = guid; initMap(); return; }
  const s = current().find(x => x.guid === guid);
  if (!s) return;
  if (!MARKERS[s.guid]) renderPins(false);
  setTimeout(() => {
    MAP.invalidateSize();
    MAP.flyTo([s.lat, s.lng], 17, { duration: REDUCED ? 0 : 0.9 });
    const marker = MARKERS[s.guid];
    if (marker) setTimeout(() => CLUSTER.zoomToShowLayer(marker, () => marker.openPopup()), REDUCED ? 0 : 950);
  }, REDUCED ? 0 : 420);
}
$('#map-reset').addEventListener('click', () => { if (MAP) frame(null, true); else initMap(); });
new IntersectionObserver((entries, obs) => {
  if (entries.some(e => e.isIntersecting)) { obs.disconnect(); initMap(); }
}, { rootMargin: '300px' }).observe($('#map-section'));

/* ---------- controls ---------- */
function moveGlider() {
  const active = $('.seg.on');
  const glider = $('#seg-glider');
  if (!active) return;
  glider.style.width = active.offsetWidth + 'px';
  glider.style.transform = `translateX(${active.offsetLeft - 4}px)`;
}
function setTab(tab) {
  if (state.tab === tab || !DATA[tab].length) return;
  state.tab = tab;
  $('#tab-martinis').classList.toggle('on', tab === 'martinis');
  $('#tab-cow').classList.toggle('on', tab === 'cow');
  $('#tab-martinis').setAttribute('aria-pressed', String(tab === 'martinis'));
  $('#tab-cow').setAttribute('aria-pressed', String(tab === 'cow'));
  moveGlider();
  closePanel();
  renderHero(); renderStats(true); renderResults();
}
$('#tab-martinis').addEventListener('click', () => setTab('martinis'));
$('#tab-cow').addEventListener('click', () => setTab('cow'));
addEventListener('resize', moveGlider);

function syncChips() {
  $$('.chip').forEach(c => {
    const on = c.dataset.filter === 'all' ? state.filters.size === 0 : state.filters.has(c.dataset.filter);
    c.classList.toggle('on', on);
    c.setAttribute('aria-pressed', String(on));
  });
}
function resetFilters() {
  state.filters.clear(); state.query = '';
  $('#find').value = ''; $('#find-clear').hidden = true;
  syncChips(); renderResults();
}
$('#chips').addEventListener('click', e => {
  const chip = e.target.closest('.chip');
  if (!chip) return;
  const f = chip.dataset.filter;
  if (f === 'all') state.filters.clear();
  else state.filters.has(f) ? state.filters.delete(f) : state.filters.add(f);
  syncChips(); renderResults();
});
let FIND_T = null;
$('#find').addEventListener('input', e => {
  state.query = e.target.value;
  $('#find-clear').hidden = !state.query;
  clearTimeout(FIND_T);
  FIND_T = setTimeout(renderResults, 130);
});
$('#find-clear').addEventListener('click', () => {
  state.query = ''; $('#find').value = ''; $('#find-clear').hidden = true;
  $('#find').focus(); renderResults();
});
$('#sort').addEventListener('change', e => { state.sort = e.target.value; renderResults(); });

/* ---------- chrome ---------- */
$$('[data-jump]').forEach(b => b.addEventListener('click', () => {
  $(b.dataset.jump).scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: 'start' });
}));

function measureHead() {
  document.documentElement.style.setProperty('--head-h', $('#site-head').offsetHeight + 'px');
}
addEventListener('resize', measureHead);
measureHead();

let ticking = false;
addEventListener('scroll', () => {
  if (ticking) return;
  ticking = true;
  requestAnimationFrame(() => { document.body.classList.toggle('scrolled', scrollY > 8); ticking = false; });
}, { passive: true });

const SPY = new IntersectionObserver(entries => {
  entries.forEach(e => {
    if (!e.isIntersecting) return;
    $$('.head-nav a').forEach(a => a.classList.toggle('current', a.dataset.spy === e.target.id));
  });
}, { rootMargin: '-45% 0px -50% 0px' });
['browse', 'map-section', 'method'].forEach(id => SPY.observe(document.getElementById(id)));

new IntersectionObserver((entries, obs) => {
  if (entries.some(e => e.isIntersecting)) { obs.disconnect(); STATS_SEEN = true; renderStats(true); }
}, { threshold: 0.4 }).observe($('#stats'));

/* ---------- boot ---------- */
const bust = 'v=' + Date.now();
Promise.all([
  fetch(`data/martinis.json?${bust}`).then(r => r.json()),
  fetch(`data/cow.json?${bust}`).then(r => r.json())
]).then(([m, c]) => {
  DATA.martinis = m.martinis || [];
  DATA.cow = c.cows || [];
  const when = new Date(m.generated_at);
  const text = when.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric', timeZone: 'America/Chicago' });
  $('#updated').textContent = text;
  $('#updated').dateTime = when.toISOString().slice(0, 10);
  $('#foot-updated').textContent = text;
  renderHero();
  renderStats(false);
  renderResults();
  moveGlider();
  if (MAP) renderPins();
}).catch(() => {
  $('#result-line').textContent = 'The index could not be loaded. Reload the page to try again.';
  $('#hero-foot').textContent = 'Index unavailable';
});
document.fonts && document.fonts.ready.then(moveGlider);
