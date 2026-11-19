"""Tests for scripts/sweep.py. Run with: python -m unittest discover tests"""
import io
import json
import os
import socket
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sweep  # noqa: E402


def setUpModule():
    for target in ("requests.sessions.Session.request", "socket.getaddrinfo"):
        patcher = mock.patch(target, side_effect=AssertionError("live network forbidden in tests"))
        patcher.start()
        unittest.addModuleCleanup(patcher.stop)


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

    def test_partial_data_is_unread(self):
        resp = mock.Mock()
        resp.json.return_value = {"errors": [{"message": "one field"}], "data": {"x": 1}}
        with mock.patch.object(sweep, "get", return_value=resp), redirect_stderr(io.StringIO()):
            with self.assertRaises(RuntimeError):
                sweep.toast_query("{x}")

    def test_missing_data_is_unread(self):
        for payload in ({}, {"data": None}):
            with self.subTest(payload=payload), mock.patch.object(sweep, "get") as get:
                get.return_value.json.return_value = payload
                with self.assertRaises(ValueError):
                    sweep.toast_query("{x}")

    def test_missing_menu_fields_are_unread(self):
        for payload in ({}, {"menusV3": None}, {"menusV3": {}}, {"menusV3": {"menus": None}}):
            with self.subTest(payload=payload), mock.patch.object(sweep, "toast_query", return_value=payload), \
                    mock.patch.object(sweep.time, "sleep"), redirect_stderr(io.StringIO()):
                self.assertEqual(sweep.martini_items("g1"), ([], False, False))

    def test_confirmed_empty_menu_is_read(self):
        with mock.patch.object(sweep, "toast_query", return_value={"menusV3": {"menus": []}}), \
                mock.patch.object(sweep.time, "sleep"):
            self.assertEqual(sweep.martini_items("g1"), ([], False, True))

    def test_directory_missing_or_null_field_fails(self):
        for payload in ({}, {"nearbyRestaurants": None}):
            with self.subTest(payload=payload), mock.patch.object(sweep, "toast_query", return_value=payload), \
                    redirect_stderr(io.StringIO()):
                directory, failed, cells = sweep.toast_directory()
                self.assertEqual(directory, {})
                self.assertEqual(failed, cells)

    def test_unread_menu_is_reported(self):
        with mock.patch.object(sweep, "toast_query", side_effect=RuntimeError("403")), \
                mock.patch.object(sweep.time, "sleep"), redirect_stderr(io.StringIO()):
            items, has_hh, read = sweep.martini_items("g1")
        self.assertEqual((items, has_hh, read), ([], False, False))


class Assemble(unittest.TestCase):
    def test_same_name_branches_are_kept_but_local_alias_is_merged(self):
        live = row("t1", "The Bar", address="1 Main St", lat=43.04)
        branch = row("m1", "The Bar", address="9 Lake St", lat=43.08)
        alias = row("m2", "the bar", address="1 Main Street", lat=43.0402)
        self.assertEqual({r["guid"] for r in sweep.assemble([live], [], [branch, alias])}, {"t1", "m1"})

    def test_matching_address_without_coords_merges(self):
        live = row("t1", "The Bar", lat=None, lng=None)
        manual = row("m1", "THE BAR", address="1 MAIN ST., Milwaukee, WI", lat=None, lng=None)
        self.assertEqual(sweep.assemble([live], [], [manual]), [live])

    def test_city_only_addresses_do_not_merge_distant_branches(self):
        a = row("c1", "The Bar", address="Milwaukee, WI", lat=43.04)
        b = row("c2", "The Bar", address="Milwaukee, WI", lat=43.10)
        self.assertEqual({r["guid"] for r in sweep.assemble([a, b], [], [])}, {"c1", "c2"})

    def test_grid_address_without_coords_merges(self):
        a = row("g1", "The Bar", address="N96W16865 Cumberland Ct, Menomonee Falls, WI", lat=None, lng=None)
        b = row("g2", "The Bar", address="n96w16865 cumberland ct, menomonee falls, wi", lat=None, lng=None)
        self.assertEqual(sweep.assemble([a], [], [b]), [a])

    def test_empty_inputs(self):
        self.assertEqual(sweep.assemble([], [], []), [])

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

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, directory, failed, menus, slugs=None, discovery_problems=None, clover=None, extra_args=None):
        read_items = sweep.martini_items
        def fake_items(guid):
            return read_items(guid) if menus is None else menus.get(guid, ([], False, True))
        env = {"GITHUB_OUTPUT": str(self.gh_out)}
        with mock.patch.object(sweep, "toast_directory", return_value=(directory, failed, 28)), \
                mock.patch.object(sweep, "martini_items", side_effect=fake_items), \
                mock.patch.object(sweep, "clover_slugs", return_value=(slugs or {}, discovery_problems or [])), \
                mock.patch.object(sweep, "clover_martini_items", side_effect=clover) as clover_read, \
                mock.patch.object(sweep, "neighborhood", return_value="Downtown"), \
                mock.patch.object(sweep.time, "sleep"), \
                mock.patch.dict(os.environ, env), \
                mock.patch.object(sys, "argv", ["sweep.py", "--out", str(self.out)] + (extra_args or [])), \
                redirect_stderr(io.StringIO()):
            os.environ.pop("GITHUB_STEP_SUMMARY", None)
            sweep.main()
            self.clover_calls = clover_read.call_args_list
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
        self.assertEqual(doc["problems"], ["Toast menus: 1 of 20 did not answer"])
        self.assertIn("degraded=true", self.gh_out.read_text())

    def test_previous_clover_is_queried_and_carried_after_discovery_and_menu_failure(self):
        previous = row("old-clover", "Clover Bar", platform="clover", seen_at="2026-09-01")
        self.out.write_text(json.dumps({"martinis": [previous]}))
        doc = self.run_main({}, 0, {}, discovery_problems=["Clover discovery: timeout"],
                            clover=RuntimeError("503"))
        self.assertEqual(self.clover_calls, [mock.call("old-clover")])
        self.assertIn(previous, doc["martinis"])
        self.assertEqual(doc["carried_forward"], 1)
        self.assertEqual(len(doc["problems"]), 2)
        self.assertIn("degraded=true", self.gh_out.read_text())

    def test_previous_clover_is_queried_after_successful_discovery(self):
        self.out.write_text(json.dumps({"martinis": [row("old-clover", "Clover Bar", platform="clover")]}))
        doc = self.run_main({}, 0, {}, clover=lambda slug: ({"name": "Clover Bar"}, []))
        self.assertEqual(self.clover_calls, [mock.call("old-clover")])
        self.assertNotIn("old-clover", {r["guid"] for r in doc["martinis"]})
        self.assertEqual(doc["problems"], [])

    def test_single_clover_http_failure_is_degraded(self):
        error = sweep.requests.HTTPError("server error", response=mock.Mock(status_code=500))
        doc = self.run_main({}, 28, {}, slugs={"new": "seed"}, clover=error)
        self.assertTrue(any("Clover new" in p for p in doc["problems"]))
        self.assertIn("degraded=true", self.gh_out.read_text())

    def test_happy_hour_only_keeps_regular_price_null_for_both_platforms(self):
        self.out.unlink()
        loc = {"address1": "1 Main St", "city": "Milwaukee", "state": "WI", "latitude": 43.04, "longitude": -87.91}
        directory = {"t1": {"guid": "t1", "name": "Toast Bar", "location": loc}}
        items = [{"item": "Espresso Martini", "price_cents": None, "hh_price_cents": 600}]
        merchant = {"name": "Clover Bar", "location": {"latitude": 43.04, "longitude": -87.91}}
        doc = self.run_main(directory, 0, {"t1": (items, True, True)}, slugs={"c1": "seed"},
                            clover=lambda slug: (merchant, items))
        swept = [r for r in doc["martinis"] if r["platform"] in ("toast", "clover")]
        self.assertEqual(len(swept), 2)
        for r in swept:
            self.assertIsNone(r["price_cents"])
            self.assertEqual(r["hh_price_cents"], 600)

    def test_invalid_previous_stops_before_network(self):
        self.out.write_text("not json")
        with mock.patch.object(sweep, "toast_directory") as directory:
            with self.assertRaises(ValueError):
                self.run_main({}, 0, {})
            directory.assert_not_called()
        self.assertEqual(self.out.read_text(), "not json")

    def test_graphql_errors_and_null_fields_carry_previous_readings(self):
        directory = {f"t{i}": {"guid": f"t{i}", "name": f"Bar {i}", "location": {}} for i in range(20)}
        payloads = ({"errors": [{"message": "partial"}], "data": {"menusV3": {"menus": []}}},
                    {"data": {}}, {"data": {"menusV3": None}})
        for payload in payloads:
            with self.subTest(payload=payload), mock.patch.object(sweep, "get") as get:
                get.return_value.json.return_value = payload
                doc = self.run_main(directory, 0, None)
            swept = [r for r in doc["martinis"] if r["platform"] == "toast"]
            self.assertEqual(len(swept), 20)
            self.assertEqual(next(r for r in swept if r["guid"] == "t0")["seen_at"], "2026-09-16")
            self.assertEqual(doc["carried_forward"], 20)
            self.assertIn("degraded=true", self.gh_out.read_text())

    def test_limit_production_is_refused_before_network(self):
        production = Path(sweep.__file__).resolve().parent.parent / "data" / "martinis.json"
        with mock.patch.object(sys, "argv", ["sweep.py", "--limit", "1", "--output", str(production), "--force"]), \
                mock.patch.object(sweep, "toast_directory") as directory, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exc:
                sweep.main()
        self.assertEqual(exc.exception.code, 2)
        directory.assert_not_called()

    def test_limit_alternate_output_is_allowed(self):
        self.out.unlink()
        doc = self.run_main({}, 0, {}, extra_args=["--limit", "1", "--output", str(self.out)])
        self.assertEqual(doc["restaurants_scanned"], 0)

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


class MenuParsing(unittest.TestCase):
    def test_matcher_excludes_non_cocktails(self):
        for name in ("NA Espresso Martini", "N/A Espresso Martini", "Non-Alcoholic Espresso Martini",
                     "Espresso Martini Mocktail", "Zero Proof Espresso Martini", "Espresso Martini Chocolate Bar",
                     "Espresso Martini Cake", "Espresso Martini Cookie", "SHOP Espresso Martini",
                     "Espresso Martini Bottle", "Espresso Martini Flight", "Espresso Martini Liqueur",
                     "Espresso Martini Bar", "Canned Espresso Martini", "Espresso Martini 4 Pack"):
            with self.subTest(name=name):
                self.assertFalse(sweep.is_martini(name))
        self.assertTrue(sweep.is_martini("Espresso Martini"))
        self.assertTrue(sweep.is_martini("Chocolate Espresso Martini"))
        self.assertFalse(sweep.is_martini("Espresso"))

    def test_toast_regular_and_happy_hour_items(self):
        payload = {"menusV3": {"menus": [{"name": "Drinks", "groups": [{"name": "Cocktails", "items": [
            {"name": "NA Espresso Martini", "price": 7},
            {"name": "Espresso Martini Chocolate Bar", "price": 9.95},
            {"name": "Espresso Martini", "price": 12},
            {"name": "HH Espresso Martini", "price": 6}]}]}]}}
        with mock.patch.object(sweep, "toast_query", return_value=payload), mock.patch.object(sweep.time, "sleep"):
            items, _, read = sweep.martini_items("g1")
        self.assertTrue(read)
        self.assertEqual(items, [{"item": "Espresso Martini", "price_cents": 1200, "hh_price_cents": None},
                                 {"item": "HH Espresso Martini", "price_cents": None, "hh_price_cents": 600}])

    def test_clover_regular_happy_hour_and_excluded_items(self):
        merchant, menu = mock.Mock(), mock.Mock()
        merchant.json.return_value = {"merchantUuid": "m1"}
        menu.json.return_value = {"items": [{"name": "NA Espresso Martini", "price": 700},
                                               {"name": "Espresso Martini Chocolate Bar", "price": 995},
                                               {"name": "Espresso Martini", "price": 1200},
                                               {"name": "HH Espresso Martini", "price": 600}]}
        with mock.patch.object(sweep, "get", side_effect=[merchant, menu]):
            _, items = sweep.clover_martini_items("slug")
        self.assertEqual([i["item"] for i in items], ["Espresso Martini", "HH Espresso Martini"])
        self.assertEqual(items[0]["price_cents"], 1200)
        self.assertEqual(items[1]["hh_price_cents"], 600)

    def test_clover_null_items_are_unread_but_empty_items_are_valid(self):
        for value in (None, []):
            merchant, menu = mock.Mock(), mock.Mock()
            merchant.json.return_value = {"merchantUuid": "m1"}
            menu.json.return_value = {"items": value}
            with self.subTest(value=value), mock.patch.object(sweep, "get", side_effect=[merchant, menu]):
                if value is None:
                    with self.assertRaises(ValueError):
                        sweep.clover_martini_items("slug")
                else:
                    self.assertEqual(sweep.clover_martini_items("slug")[1], [])


class WebsiteDiscovery(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(sweep.requests, "Session")
        self.session = patcher.start().return_value.__enter__.return_value
        self.addCleanup(patcher.stop)

    def response(self, body=b"", redirect=None):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.is_redirect = redirect is not None
        response.headers = {"Location": redirect} if redirect else {}
        response.encoding = "utf-8"
        response.iter_content.return_value = [body]
        return response

    def dns(self, host, *args, **kwargs):
        ip = host if host in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1") else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 80))]

    def test_public_page_streams_with_limit(self):
        response = self.response(b"clover.com/online-ordering/the-bar")
        with mock.patch.object(sweep.socket, "getaddrinfo", side_effect=self.dns), \
                mock.patch.object(self.session, "get", return_value=response) as get:
            self.assertIn("the-bar", sweep.website_html("https://example.com/menu"))
        self.assertTrue(get.call_args.kwargs["stream"])
        self.assertFalse(get.call_args.kwargs["allow_redirects"])
        self.assertEqual(get.call_args.args[0], "https://93.184.216.34:443/menu")
        self.assertEqual(get.call_args.kwargs["headers"]["Host"], "example.com")
        self.assertFalse(self.session.trust_env)
        adapter = self.session.mount.call_args.args[1]
        self.assertEqual(adapter.poolmanager.connection_pool_kw["server_hostname"], "example.com")
        self.assertEqual(adapter.poolmanager.connection_pool_kw["assert_hostname"], "example.com")
        response.iter_content.assert_called_once_with(chunk_size=16384)

    def test_unsafe_urls_never_requested(self):
        for url in ("file:///etc/passwd", "ftp://example.com/", "http://127.0.0.1/", "http://10.0.0.1/",
                    "http://169.254.169.254/", "http://[::1]/", "https://user:pass@example.com/"):
            with self.subTest(url=url), mock.patch.object(sweep.socket, "getaddrinfo", side_effect=self.dns), \
                    mock.patch.object(self.session, "get") as get:
                with self.assertRaises(ValueError):
                    sweep.website_html(url)
                get.assert_not_called()

    def test_private_dns_answer_rejected(self):
        with mock.patch.object(sweep.socket, "getaddrinfo", return_value=self.dns("10.0.0.1")), \
                mock.patch.object(self.session, "get") as get:
            with self.assertRaises(ValueError):
                sweep.website_html("https://example.com")
            get.assert_not_called()

    def test_redirect_target_checked_before_request(self):
        for target in ("http://127.0.0.1/", "file:///etc/passwd"):
            with self.subTest(target=target), mock.patch.object(sweep.socket, "getaddrinfo", side_effect=self.dns), \
                    mock.patch.object(self.session, "get", return_value=self.response(redirect=target)) as get:
                with self.assertRaises(ValueError):
                    sweep.website_html("https://example.com")
                self.assertEqual(get.call_count, 1)

    def test_relative_public_redirect_works(self):
        with mock.patch.object(sweep.socket, "getaddrinfo", side_effect=self.dns), \
                mock.patch.object(self.session, "get", side_effect=[self.response(redirect="/menu"), self.response(b"menu")]) as get:
            self.assertEqual(sweep.website_html("https://example.com"), "menu")
        self.assertEqual(get.call_args.args[0], "https://93.184.216.34:443/menu")

    def test_oversized_page_and_redirect_loop_fail(self):
        for response in (self.response(b"x" * 400001), self.response(redirect="/loop")):
            with self.subTest(response=response), mock.patch.object(sweep.socket, "getaddrinfo", side_effect=self.dns), \
                    mock.patch.object(self.session, "get", return_value=response):
                with self.assertRaises(ValueError):
                    sweep.website_html("https://example.com")

    def test_probe_failure_is_recorded_and_successful_links_kept(self):
        def html(url):
            if url.endswith("/bad"):
                raise sweep.requests.Timeout("timeout")
            return "https://clover.com/online-ordering/new-bar"
        with mock.patch.object(sweep, "osm_websites", return_value=["https://example.com/bad", "https://example.com/good"]), \
                mock.patch.object(sweep, "website_html", side_effect=html), redirect_stderr(io.StringIO()):
            slugs, problems = sweep.clover_slugs()
        self.assertIn("new-bar", slugs)
        self.assertEqual(len(problems), 1)
        self.assertIn("timeout", problems[0])

    def test_overpass_failure_is_recorded(self):
        with mock.patch.object(sweep, "osm_websites", return_value=None), redirect_stderr(io.StringIO()):
            slugs, problems = sweep.clover_slugs()
        self.assertEqual(set(slugs), set(sweep.CLOVER_SEEDS))
        self.assertTrue(problems)

    def test_empty_discovery_is_successful(self):
        with mock.patch.object(sweep, "osm_websites", return_value=[]), redirect_stderr(io.StringIO()):
            slugs, problems = sweep.clover_slugs()
        self.assertEqual(set(slugs), set(sweep.CLOVER_SEEDS))
        self.assertEqual(problems, [])


class OutputSafety(unittest.TestCase):
    def test_missing_previous_is_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(sweep.load_previous(Path(directory) / "missing.json"), {})

    def test_invalid_and_unreadable_previous_raise(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            for body in ("broken", "[]", "{}", '{"martinis":null}', '{"martinis":[{}]}'):
                path.write_text(body)
                with self.subTest(body=body), self.assertRaises(ValueError):
                    sweep.load_previous(path)
            with mock.patch.object(Path, "read_text", side_effect=PermissionError("unreadable")):
                with self.assertRaises(PermissionError):
                    sweep.load_previous(path)

    def test_atomic_replacement_and_failure_preserves_previous(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text("old")
            def replace(source, destination):
                self.assertEqual(Path(source).parent, path.parent)
                self.assertEqual(path.read_text(), "old")
                self.assertEqual(json.loads(Path(source).read_text()), {"martinis": []})
                os.rename(source, destination)
            with mock.patch.object(sweep.os, "replace", side_effect=replace) as replacement:
                sweep.write_atomic(path, {"martinis": []})
            replacement.assert_called_once()
            self.assertEqual(json.loads(path.read_text()), {"martinis": []})
            before = path.read_text()
            with mock.patch.object(sweep.os, "replace", side_effect=OSError("interrupted")):
                with self.assertRaises(OSError):
                    sweep.write_atomic(path, {"martinis": [1]})
            self.assertEqual(path.read_text(), before)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_failure_before_replace_preserves_previous_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            path.write_text("old")
            with mock.patch.object(sweep.os, "fsync", side_effect=OSError("disk error")), \
                    mock.patch.object(sweep.os, "replace") as replace:
                with self.assertRaises(OSError):
                    sweep.write_atomic(path, {"martinis": []})
                replace.assert_not_called()
            self.assertEqual(path.read_text(), "old")
            self.assertEqual(list(path.parent.iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
