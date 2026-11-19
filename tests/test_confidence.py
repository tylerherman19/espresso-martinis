"""Exercise the UI's actual aging rules offline with Node."""
import subprocess
import unittest
from pathlib import Path


class Confidence(unittest.TestCase):
    def test_aging_and_read_dates(self):
        source = (Path(__file__).resolve().parent.parent / "app.js").read_text()
        rules = source[source.index("const DAY ="):source.index("const isUnder =")]
        cow_assignment = next(line.strip() for line in source.splitlines() if "DATA.cow =" in line)
        script = rules + "\n" + r"""
const assert = require('node:assert/strict');
Date.now = () => Date.parse('2026-12-09T00:00:00Z');
const DATA = {};
let c = {generated_at: '2026-09-09T00:00:00Z', cows: [
  {confidence: 'menu'}, {confidence: 'reported'}, {confidence: 'stale'},
  {confidence: 'menu', verified_at: '2026-12-01'}
]};
""" + cow_assignment + r"""
assert.deepEqual(DATA.cow.map(confidenceOf), ['stale', 'reported', 'stale', 'menu']);
assert.equal(confidenceOf({verified_at: '2026-09-10'}), 'menu');
assert.equal(confidenceOf({seen_at: '2026-11-24'}), 'stale');
assert.equal(confidenceOf({seen_at: '2026-11-25'}), 'menu');
assert.equal(confidenceOf({seen_at: '2026-09-09', confidence: 'menu'}), 'stale');
assert.equal(readOn({seen_at: '2026-09-09'}), 'September 9, 2026');
assert.equal(readOn(DATA.cow[0]), 'September 9, 2026');
assert.equal(confidenceOf({}), 'menu');
assert.equal(confidenceOf({verified_at: 'invalid'}), 'menu');
c = {cows: []};
""" + cow_assignment + r"""
assert.deepEqual(DATA.cow, []);
"""
        subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
