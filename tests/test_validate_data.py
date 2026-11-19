import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from validate_data import validate


class Validation(unittest.TestCase):
    def setUp(self):
        self.row = {"guid": "one", "name": "Bar", "lat": 43.04, "lng": -87.91,
                    "price_cents": 1200, "hh_price_cents": None,
                    "items": [{"item": "Espresso Martini", "price_cents": None, "hh_price_cents": 600}],
                    "seen_at": "2026-09-23", "confidence": "menu"}

    def check(self, rows):
        return validate({"count": len(rows), "martinis": rows}, "martinis")

    def test_valid_and_empty(self):
        self.assertEqual(self.check([self.row]), 1)
        self.assertEqual(self.check([]), 0)

    def test_invalid_rows(self):
        changes = [("guid", ""), ("name", " "), ("lat", None), ("lat", float("nan")),
                   ("lat", float("inf")), ("lat", True), ("lng", 0), ("lat", 50),
                   ("price_cents", 0), ("price_cents", -1), ("price_cents", 1.5),
                   ("price_cents", True), ("hh_price_cents", "600"), ("confidence", "certain"),
                   ("seen_at", "2026-02-30"), ("verified_at", "yesterday"), ("items", None)]
        for field, value in changes:
            row = copy.deepcopy(self.row)
            row[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.check([row])

    def test_duplicate_guids_and_nonobjects(self):
        for rows in ([self.row, self.row], [None], ["bar"]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.check(rows)

    def test_bad_items(self):
        for item in (None, {}, {"price_cents": -3, "hh_price_cents": None}):
            row = {**self.row, "items": [item]}
            with self.subTest(item=item), self.assertRaises(ValueError):
                self.check([row])

    def test_bad_documents(self):
        for doc in ([], {}, {"martinis": {}, "count": 0}, {"martinis": [], "count": 1},
                    {"martinis": [], "count": 0, "generated_at": "not-a-date"}):
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                validate(doc, "martinis")

    def test_other_catalogs_and_timestamp(self):
        for key in ("cows", "entries"):
            self.assertEqual(validate({key: [self.row], "generated_at": "2026-09-09T03:55:13Z"}, key), 1)


if __name__ == "__main__":
    unittest.main()
