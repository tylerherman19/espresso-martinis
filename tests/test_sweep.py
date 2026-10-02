"""Tests for scripts/sweep.py. Run with: python -m unittest discover tests"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sweep  # noqa: E402


def row(guid, name, price=1200, platform="toast", **extra):
    r = {"name": name, "address": "1 Main St, Milwaukee, WI", "lat": 43.04, "lng": -87.91,
         "neighborhood": "Downtown", "downtown": True, "price_cents": price,
         "items": [{"item": "Espresso Martini", "price_cents": price, "hh_price_cents": None}],
         "happy_hour": False, "hh_price_cents": None, "platform": platform, "guid": guid}
    r.update(extra)
    return r


class CleanName(unittest.TestCase):
    def test_trailing_address(self):
        self.assertEqual(sweep.clean_name("Von Trier 2235 North Farwell Avenue"), "Von Trier")

    def test_unit_then_address(self):
        self.assertEqual(sweep.clean_name("Aya 700 East Kilbourn Avenue, Suite 100"), "Aya")

    def test_doubled_name(self):
        self.assertEqual(sweep.clean_name("Blu Blu"), "Blu")
        self.assertEqual(sweep.clean_name("The Outsider The Outsider"), "The Outsider")


class ToastQuery(unittest.TestCase):
    def test_errors_without_data_raise(self):
        resp = mock.Mock()
        resp.json.return_value = {"errors": [{"message": "Forbidden"}]}
        with mock.patch.object(sweep, "get", return_value=resp), redirect_stderr(io.StringIO()):
            with self.assertRaises(RuntimeError):
                sweep.toast_query("{x}")

    def test_partial_data_is_kept(self):
        resp = mock.Mock()
        resp.json.return_value = {"errors": [{"message": "one field"}], "data": {"x": 1}}
        with mock.patch.object(sweep, "get", return_value=resp), redirect_stderr(io.StringIO()):
            self.assertEqual(sweep.toast_query("{x}"), {"x": 1})

    def test_unread_menu_is_reported(self):
        with mock.patch.object(sweep, "toast_query", side_effect=RuntimeError("403")), \
                mock.patch.object(sweep.time, "sleep"), redirect_stderr(io.StringIO()):
            items, has_hh, read = sweep.martini_items("g1")
        self.assertEqual((items, has_hh, read), ([], False, False))


class Assemble(unittest.TestCase):
    def test_live_beats_hand_beats_carried(self):
        live = [row("t1", "Blu", 1400, seen_at="2026-10-07")]
        carried = [row("t1", "Blu", 1300), row("t2", "Onesto", 1500), row("t3", "Kept", 1100)]
        hand = [row("manual:blu", "Blu", 1600, platform="website"),
                row("manual:onesto", "Onesto", 1600, platform="website")]
        with redirect_stderr(io.StringIO()):
            out = sweep.assemble(live, carried, hand)
        by_name = {(r["name"], r["platform"], r["price_cents"]) for r in out}
        self.assertEqual(by_name, {("Blu", "toast", 1400), ("Onesto", "website", 1600), ("Kept", "toast", 1100)})
        self.assertEqual([r["price_cents"] for r in out], sorted(r["price_cents"] for r in out))

    def test_hand_check_replaces_by_guid(self):
        # The platform spells it "Sweetdiner- MKE"; the hand-check says "Sweet Diner".
        carried = [row("t9", "Sweetdiner- MKE", 1500)]
        hand = [row("manual:sweet-diner", "Sweet Diner", 1500, platform="website", replaces="t9")]
        with redirect_stderr(io.StringIO()):
            self.assertEqual([r["guid"] for r in sweep.assemble([], carried, hand)], ["manual:sweet-diner"])
            # Once the platform answers again, its live reading wins.
            live = [row("t9", "Sweetdiner- MKE", 1600)]
            self.assertEqual([r["guid"] for r in sweep.assemble(live, carried, hand)], ["t9"])

    def test_collapsed(self):
        self.assertTrue(sweep.collapsed(2, 98))
        self.assertFalse(sweep.collapsed(60, 98))
        self.assertFalse(sweep.collapsed(0, 5))  # too small a list to judge


class MainRun(unittest.TestCase):
    """The whole sweep with the network replaced, on the two days that matter."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "martinis.json"
        self.gh_out = Path(self.tmp.name) / "gh_output"
        self.gh_out.write_text("")
        prev = [row(f"t{i}", f"Bar {i}", 1000 + i * 50) for i in range(20)]
        prev[0]["seen_at"] = "2026-09-16"  # one already carried once, keeps its date
        self.prev_doc = {"generated_at": "2026-09-23T10:00:00+00:00", "count": len(prev), "martinis": prev}
        self.out.write_text(json.dumps(self.prev_doc))
        # Two hand-checks, so the run does not depend on what data/manual.json holds today.
        self.manual = Path(self.tmp.name) / "manual.json"
        self.manual.write_text(json.dumps({"entries": [
            row("manual:a", "Hand A", 1600, platform="website"), row("manual:b", "Hand B", None, platform="website")]}))

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, directory, failed, menus):
        def fake_items(guid):
            return menus.get(guid, ([], False, True))
        env = {"GITHUB_OUTPUT": str(self.gh_out)}
        with mock.patch.object(sweep, "toast_directory", return_value=(directory, failed, 28)), \
                mock.patch.object(sweep, "martini_items", side_effect=fake_items), \
                mock.patch.object(sweep, "clover_slugs", return_value=({}, True)), \
                mock.patch.object(sweep, "neighborhood", return_value="Downtown"), \
                mock.patch.object(sweep, "MANUAL", self.manual), \
                mock.patch.object(sweep.time, "sleep"), \
                mock.patch.dict(os.environ, env), \
                mock.patch.object(sys, "argv", ["sweep.py", "--out", str(self.out)]), \
                redirect_stderr(io.StringIO()):
            os.environ.pop("GITHUB_STEP_SUMMARY", None)
            sweep.main()
        return json.loads(self.out.read_text())

    def test_blocked_platform_keeps_last_reading(self):
        # 2026-09-30: every Toast request 403s. The list must not collapse.
        doc = self.run_main({}, 28, {})
        swept = [r for r in doc["martinis"] if r["platform"] == "toast"]
        self.assertEqual(len(swept), 20)
        self.assertEqual(doc["carried_forward"], 20)
        dates = {r["guid"]: r["seen_at"] for r in swept}
        self.assertEqual(dates["t0"], "2026-09-16")
        self.assertEqual(dates["t1"], "2026-09-23")
        self.assertTrue(doc["problems"])
        self.assertIn("degraded=true", self.gh_out.read_text())

    def test_healthy_run_drops_what_is_gone(self):
        # Toast answers, and only twelve of the twenty still list the drink.
        loc = {"address1": "1 Main St", "city": "Milwaukee", "state": "WI", "latitude": 43.04, "longitude": -87.91}
        directory = {f"t{i}": {"guid": f"t{i}", "name": f"Bar {i}", "location": loc} for i in range(20)}
        item = [{"item": "Espresso Martini", "price_cents": 1300, "hh_price_cents": None}]
        menus = {f"t{i}": (item, False, True) for i in range(12)}
        # One menu does not answer: it keeps last week's reading rather than vanishing.
        menus["t12"] = ([], False, False)
        doc = self.run_main(directory, 0, menus)
        swept = {r["guid"]: r for r in doc["martinis"] if r["platform"] == "toast"}
        self.assertEqual(set(swept), {f"t{i}" for i in range(13)})
        self.assertEqual(swept["t12"]["seen_at"], "2026-09-23")
        self.assertNotEqual(swept["t0"]["seen_at"], "2026-09-23")
        self.assertEqual(doc["problems"], [])
        self.assertEqual(self.gh_out.read_text(), "")

    def test_collapse_is_refused_and_file_left_alone(self):
        # Toast answers but nothing parses: a format change, not 18 closures.
        loc = {"address1": "1 Main St", "city": "Milwaukee", "state": "WI", "latitude": 43.04, "longitude": -87.91}
        directory = {f"t{i}": {"guid": f"t{i}", "name": f"Bar {i}", "location": loc} for i in range(20)}
        before = self.out.read_text()
        with self.assertRaises(SystemExit) as cm:
            self.run_main(directory, 0, {})
        self.assertEqual(cm.exception.code, 1)
        self.assertEqual(self.out.read_text(), before)
        self.assertIn("degraded=true", self.gh_out.read_text())


if __name__ == "__main__":
    unittest.main()
