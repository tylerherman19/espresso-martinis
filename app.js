(function () {
  const fmt = (cents) => (cents == null ? '?' : '$' + (cents / 100).toFixed(2).replace(/\.00$/, ''));
  const state = { data: null, view: 'list', hood: '', sort: 'downtown', map: null, layer: null };

  const $ = (id) => document.getElementById(id);

  function filtered() {
    let rows = state.data.martinis.slice();
    if (state.hood) rows = rows.filter((r) => (r.neighborhood || 'Unlabeled') === state.hood);
    if (state.sort === 'downtown') rows.sort((a, b) => ((b.downtown ? 1 : 0) - (a.downtown ? 1 : 0)) || (a.price_cents ?? 1e9) - (b.price_cents ?? 1e9) || a.name.localeCompare(b.name));
    else if (state.sort === 'price-asc') rows.sort((a, b) => (a.price_cents ?? 1e9) - (b.price_cents ?? 1e9) || a.name.localeCompare(b.name));
    else if (state.sort === 'price-desc') rows.sort((a, b) => (b.price_cents ?? -1) - (a.price_cents ?? -1) || a.name.localeCompare(b.name));
    else rows.sort((a, b) => a.name.localeCompare(b.name));
    return rows;
  }

  function renderList() {
    const rows = filtered();
    $('n-list').textContent = rows.length;
    $('n-map').textContent = rows.length;
    const el = $('view-list');
    if (!rows.length) { el.innerHTML = '<div class="empty">No espresso martinis found for this filter.</div>'; return; }
    el.innerHTML = rows.map((r, i) => {
      const variants = r.items.length > 1
        ? r.items.slice(1).map((m) => `${m.item} ${fmt(m.price_cents)}`).join(' · ') : '';
      return `<div class="row">
        <span class="rank">${String(i + 1).padStart(2, '0')}</span>
        <span class="name">${esc(r.name)}${variants ? `<span class="variant">also: ${esc(variants)}</span>` : ''}</span>
        <span class="hood">${esc(r.neighborhood || 'Unlabeled')}</span>
        <span class="price">${fmt(r.price_cents)}</span>
      </div>`;
    }).join('');
  }

  function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }

  function renderMap() {
    if (!state.map) {
      state.map = L.map('map', { scrollWheelZoom: true }).setView([43.045, -87.95], 11);
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      }).addTo(state.map);
      state.layer = L.layerGroup().addTo(state.map);
    }
    const rows = filtered().filter((r) => r.lat && r.lng);
    state.layer.clearLayers();
    const bounds = [];
    const min = Math.min(...rows.map((r) => r.price_cents ?? Infinity));
    for (const r of rows) {
      const ll = [r.lat, r.lng];
      bounds.push(ll);
      const cheap = r.price_cents === min;
      const icon = L.divIcon({ className: '', html: `<div class="price-pin${cheap ? ' cheapest' : ''}">${fmt(r.price_cents)}</div>`, iconSize: null, iconAnchor: [18, 14] });
      const items = r.items.map((m) => `<div class="pop-item"><span>${esc(m.item)}</span><b>${fmt(m.price_cents)}</b></div>`).join('');
      L.marker(ll, { icon }).bindPopup(
        `<div class="pop-name">${esc(r.name)}</div><div class="pop-hood">${esc(r.neighborhood || '')}</div>${items}<div class="pop-addr">${esc(r.address || '')}</div>`
      ).addTo(state.layer);
    }
    if (bounds.length) state.map.fitBounds(bounds, { padding: [30, 30] });
    setTimeout(() => state.map.invalidateSize(), 60);
  }

  function switchView(v) {
    state.view = v;
    $('tab-list').classList.toggle('active', v === 'list');
    $('tab-map').classList.toggle('active', v === 'map');
    $('view-list').classList.toggle('hidden', v !== 'list');
    $('view-map').classList.toggle('hidden', v !== 'map');
    $('col-header').style.visibility = v === 'list' ? 'visible' : 'hidden';
    if (v === 'map') renderMap();
  }

  fetch('data/martinis.json?v=' + Date.now())
    .then((r) => r.json())
    .then((doc) => {
      state.data = doc;
      const when = new Date(doc.generated_at);
      $('stamp').innerHTML = `${doc.count} FOUND<br>UPDATED ${when.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase()} ${when.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }).toUpperCase()}`;
      const hoods = [...new Set(doc.martinis.map((m) => m.neighborhood || 'Unlabeled'))].sort();
      $('hood-filter').innerHTML = '<option value="">All neighborhoods</option>' + hoods.map((h) => `<option>${esc(h)}</option>`).join('');
      renderList();
    })
    .catch(() => { $('stamp').textContent = 'DATA UNAVAILABLE'; });

  $('tab-list').addEventListener('click', () => switchView('list'));
  $('tab-map').addEventListener('click', () => switchView('map'));
  $('hood-filter').addEventListener('change', (e) => { state.hood = e.target.value; renderList(); if (state.view === 'map') renderMap(); });
  $('sort-order').addEventListener('change', (e) => { state.sort = e.target.value; renderList(); });
})();
