/* Pure directory rules, shared by the plain-script page and Node tests. */
'use strict';
const Drinks = (() => {
  const money = c => '$' + (c / 100).toFixed(c % 100 === 0 ? 0 : 2);
  const hhShown = (s, happyHour = false) => s.hh_price_cents != null && (happyHour || s.price_cents == null);
  const priceOf = (s, happyHour = false) => hhShown(s, happyHour) ? s.hh_price_cents : s.price_cents;
  function median(list, pick = s => s.price_cents) {
    const prices = list.map(pick).filter(v => v != null).sort((a, b) => a - b);
    if (!prices.length) return null;
    const mid = prices.length >> 1;
    return prices.length % 2 ? prices[mid] : Math.round((prices[mid - 1] + prices[mid]) / 2);
  }
  const validCoords = s => Number.isFinite(s.lat) && Number.isFinite(s.lng)
    && s.lat >= 42.5 && s.lat <= 43.6 && s.lng >= -88.6 && s.lng <= -87.5;
  function confidenceOf(s, now = Date.now()) {
    if (s.confidence) return s.confidence;
    const swept = s.seen_at != null;
    const when = Date.parse(swept ? s.seen_at : s.verified_at);
    if (isNaN(when)) return 'menu';
    return now - when > (swept ? 14 : 90) * 864e5 ? 'stale' : 'menu';
  }
  function keeps(s, { filters = new Set(), query = '', mid = null, area = '', downtown = false, now } = {}) {
    if (filters.has('hh') && !s.happy_hour) return false;
    const price = priceOf(s, filters.has('hh'));
    if (filters.has('value') && !(mid != null && price != null && price < mid)) return false;
    if (filters.has('downtown') && !downtown) return false;
    if (filters.has('menu') && confidenceOf(s, now) !== 'menu') return false;
    const q = query.trim().toLowerCase();
    return !q || [s.name, s.neighborhood, area, s.address,
      ...(Array.isArray(s.items) ? s.items.map(it => it.item) : [])]
      .some(value => String(value || '').toLowerCase().includes(q));
  }
  async function loadData(url, key, fetcher = fetch) {
    const response = await fetcher(url, { cache: 'no-cache' });
    if (!response.ok) throw new Error(`${url} ${response.status}`);
    const doc = await response.json();
    if (!doc || !Array.isArray(doc[key]) || !doc[key].every(s => s && typeof s === 'object'
      && !Array.isArray(s) && typeof s.guid === 'string' && typeof s.name === 'string')) {
      throw new Error(`${url}: invalid ${key} collection`);
    }
    return doc;
  }
  return { money, hhShown, priceOf, median, validCoords, confidenceOf, keeps, loadData };
})();
if (typeof module !== 'undefined') module.exports = Drinks;
