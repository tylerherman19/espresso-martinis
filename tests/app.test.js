'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { money, hhShown, priceOf, median, validCoords, confidenceOf, keeps, loadData } = require('../drinks.js');

test('everyday and happy-hour pricing keep unknown prices separate', () => {
  const s = { price_cents: 1200, hh_price_cents: 600 };
  assert.equal(priceOf(s), 1200);
  assert.equal(priceOf(s, true), 600);
  assert.equal(hhShown(s), false);
  assert.equal(priceOf({ ...s, price_cents: null }), 600);
  assert.equal(priceOf({ price_cents: null, hh_price_cents: null }), null);
  assert.equal(money(1200), '$12');
  assert.equal(money(1250), '$12.50');
});
test('median ignores unknown prices, does not mutate rows, and supports an explicit picker', () => {
  const rows = [{ price_cents: 1200 }, { price_cents: null }, { price_cents: 900 }];
  assert.equal(median(rows), 1050);
  assert.equal(rows[0].price_cents, 1200);
  assert.equal(median([...rows, { price_cents: 1000 }]), 1000);
  assert.equal(median([]), null);
  assert.equal(median([{ price_cents: null, hh_price_cents: 600 }]), null);
  assert.equal(median([{ price_cents: null, hh_price_cents: 600 }], s => priceOf(s)), 600);
});
test('filters combine price, evidence, location, happy hour, and search', () => {
  const s = { name: 'Bar', address: 'Water Street', price_cents: 900, happy_hour: true,
    confidence: 'menu', items: [{ item: 'Espresso Martini' }] };
  const options = { filters: new Set(['value', 'menu', 'downtown', 'hh']), mid: 1200, downtown: true };
  assert.equal(keeps(s, options), true);
  for (const changed of [{ price_cents: null }, { price_cents: 1200 }, { happy_hour: false }, { confidence: 'reported' }]) {
    assert.equal(keeps({ ...s, ...changed }, options), false);
  }
  assert.equal(keeps(s, { ...options, downtown: false }), false);
  assert.equal(keeps(s, { query: '  MARTINI ' }), true);
  assert.equal(keeps(s, { query: 'water' }), true);
  assert.equal(keeps(s, { query: 'missing' }), false);
  assert.equal(keeps({ name: 'Empty' }), true);
  assert.equal(keeps({ name: 'Empty' }, { query: 'martini' }), false);
});
test('confidence honors explicit grades and source-specific aging', () => {
  const now = Date.parse('2026-10-01');
  assert.equal(confidenceOf({ confidence: 'reported' }, now), 'reported');
  assert.equal(confidenceOf({ seen_at: '2026-09-30' }, now), 'menu');
  assert.equal(confidenceOf({ seen_at: '2026-09-01' }, now), 'stale');
  assert.equal(confidenceOf({ verified_at: '2026-09-01' }, now), 'menu');
  assert.equal(confidenceOf({ verified_at: '2026-01-01' }, now), 'stale');
  assert.equal(confidenceOf({}, now), 'menu');
});
test('coordinates must be finite numbers in the metro area', () => {
  assert.equal(validCoords({ lat: 43.04, lng: -87.91 }), true);
  for (const s of [{}, { lat: '43.04', lng: -87.91 }, { lat: NaN, lng: -87.91 },
    { lat: Infinity, lng: -87.91 }, { lat: 0, lng: 0 }, { lat: 43, lng: -180 }]) {
    assert.equal(validCoords(s), false);
  }
});
test('menu grades age from the last reading without overriding reported or stale', () => {
  const now = Date.parse('2026-12-09');
  assert.equal(confidenceOf({ confidence: 'menu', seen_at: '2026-11-24' }, now), 'stale');
  assert.equal(confidenceOf({ confidence: 'menu', seen_at: '2026-11-25' }, now), 'menu');
  assert.equal(confidenceOf({ confidence: 'menu', verified_at: '2026-09-09' }, now), 'stale');
  assert.equal(confidenceOf({ confidence: 'menu', verified_at: '2026-09-10' }, now), 'menu');
  for (const confidence of ['reported', 'stale']) {
    assert.equal(confidenceOf({ confidence, verified_at: '2026-12-01' }, now), confidence);
  }
  assert.equal(confidenceOf({ verified_at: 'invalid' }, now), 'menu');
});
test('Cow loading uses the research date only when its own reading date is absent', async () => {
  const rows = ['menu', 'reported', 'stale'].map(confidence => ({ guid: confidence, name: confidence, confidence }));
  rows.push({ guid: 'fresh', name: 'Fresh', confidence: 'menu', verified_at: '2026-12-01' });
  const fetcher = async () => ({ ok: true, json: async () => ({ generated_at: '2026-09-09', cows: rows }) });
  const doc = await loadData('data/cow.json', 'cows', fetcher);
  assert.deepEqual(doc.cows.map(s => confidenceOf(s, Date.parse('2026-12-09'))), ['stale', 'reported', 'stale', 'menu']);
  for (const row of doc.cows.slice(0, 3)) {
    assert.equal(row.verified_at, undefined);
    assert.equal(row.seen_at, undefined);
    assert.equal(row._research_at, '2026-09-09');
  }
  assert.equal(doc.cows[3].verified_at, '2026-12-01');
  assert.equal(rows[0].verified_at, undefined);
});
test('stable URLs revalidate; normal and empty datasets load', async () => {
  for (const rows of [[], [{ guid: 'one', name: 'Bar' }]]) {
    const doc = await loadData('data/cow.json', 'cows', async (url, options) => {
      assert.equal(url, 'data/cow.json');
      assert.deepEqual(options, { cache: 'no-cache' });
      return { ok: true, json: async () => ({ cows: rows }) };
    });
    assert.deepEqual(doc.cows, rows);
  }
});
test('one failed dataset does not prevent an independent successful load', async () => {
  const failed = loadData('martinis', 'martinis', async () => ({ ok: false, status: 503 }));
  const good = loadData('cow', 'cows', async () => ({ ok: true, json: async () => ({ cows: [] }) }));
  await assert.rejects(failed, /503/);
  assert.deepEqual((await good).cows, []);
  for (const doc of [null, {}, { cows: {} }, { cows: [null] }]) {
    await assert.rejects(loadData('cow', 'cows', async () => ({ ok: true, json: async () => doc })), /invalid/);
  }
  await assert.rejects(loadData('cow', 'cows', async () => { throw new Error('offline'); }), /offline/);
  await assert.rejects(loadData('cow', 'cows', async () => ({ ok: true, json: async () => { throw new Error('bad JSON'); } })), /bad JSON/);
});
