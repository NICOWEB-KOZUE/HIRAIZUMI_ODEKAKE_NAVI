"""帰りのバスがないとき、別のルートのバスで家の近くまで帰る候補のテスト

python3 -m unittest discover tests
"""

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import planner  # noqa: E402

MON = date(2026, 10, 19)
TUE = date(2026, 10, 20)
THU = date(2026, 10, 22)
FRI = date(2026, 10, 23)
SUN = date(2026, 10, 25)


def bus(route_id, stop):
    return {"mode": "bus", "route_id": route_id, "stop": stop}


def nearby(result):
    return [c for c in result["candidates"] if c["label"] == planner.NEARBY_LABEL]


def community_legs(legs):
    return [l for l in legs if l.get("kind") == "ride" and l["line"].startswith("コミュニティバス")]


class NearbyStopsTest(unittest.TestCase):
    def test_neighbors_of_shared_stop(self):
        near = planner.nearby_stops(bus("nagashima_east_west", "境田"))
        self.assertEqual(near, [("nagashima_north_south", "開田碑前", 1)])

    def test_same_stop_on_other_route(self):
        near = planner.nearby_stops(bus("nagashima_north_south", "開田碑前"))
        self.assertEqual(near, [("nagashima_east_west", "開田碑前", 0)])

    def test_far_stop_has_no_neighbors(self):
        self.assertEqual(planner.nearby_stops(bus("hiraizumi", "沢田橋")), [])
        self.assertEqual(planner.nearby_stops(bus("nagashima_north_south", "須崎")), [])

    def test_taxi_user_has_no_neighbors(self):
        self.assertEqual(planner.nearby_stops({"mode": "taxi"}), [])


class TownReturnTest(unittest.TestCase):
    def test_other_route_takes_user_near_home(self):
        # 長島東西ルートは火曜は走らないが、長島南北ルートが開田碑前まで行く
        result = planner.plan(bus("nagashima_east_west", "境田"), "home", "joice", TUE, "am")
        main, near = result["candidates"][0], nearby(result)
        self.assertEqual(len(near), 1)
        ride = community_legs(near[0]["back"])[0]
        self.assertEqual((ride["from"], ride["to"]), ("ジョイス", "開田碑前"))
        self.assertIn("長島南北ルート", ride["line"])
        self.assertIn("境田", near[0]["back"][-1]["text"])
        self.assertEqual(main["back_note"], planner.OTHER_BACK_HINT)
        self.assertEqual(near[0]["back_warnings"], [])

    def test_afternoon_on_other_routes_day(self):
        result = planner.plan(bus("nagashima_north_south", "山王"), "home", "town_office", THU, "pm")
        ride = community_legs(nearby(result)[0]["back"])[0]
        self.assertEqual((planner.to_hhmm(ride["dep"]), ride["from"], ride["to"]), ("13:30", "役場", "開田碑前"))

    def test_own_bus_comes_first(self):
        result = planner.plan(bus("nagashima_north_south", "須崎"), "home", "town_office", TUE, "am")
        self.assertEqual(nearby(result), [])
        self.assertEqual(community_legs(result["candidates"][0]["back"])[0]["to"], "須崎")

    def test_no_neighbor_keeps_taxi(self):
        result = planner.plan(bus("hiraizumi", "沢田橋"), "home", "town_office", TUE, "am")
        self.assertEqual(nearby(result), [])
        self.assertTrue(any("タクシー" in w for w in result["candidates"][0]["back_warnings"]))

    def test_no_bus_on_sunday(self):
        result = planner.plan(bus("nagashima_east_west", "境田"), "home", "joice", SUN, "am")
        self.assertEqual(nearby(result), [])


class OutReturnTest(unittest.TestCase):
    def test_same_name_stop_needs_no_last_leg(self):
        result = planner.plan(bus("nagashima_east_west", "開田碑前"), "home", "iwate_hospital", FRI, "am")
        near = nearby(result)
        self.assertEqual(len(near), 1)
        last = near[0]["back"][-1]
        self.assertEqual((last["from"], last["to"]), ("平泉駅", "開田碑前"))
        self.assertIn("家のバス停まで", near[0]["back_note"])

    def test_own_bus_on_shared_stop(self):
        # 大平は平泉ルートにも長島東西ルートにもあるが、自分のルートで帰れるなら出さない
        result = planner.plan(bus("hiraizumi", "大平"), "home", "iwai_hospital", THU, "am")
        self.assertEqual(nearby(result), [])


def toban(result):
    return [c for c in result["candidates"] if c["label"] == planner.TOBAN_LABEL]


class TobanReturnTest(unittest.TestCase):
    """東磐交通一関線（路線バス）で家の近くまで帰る"""

    def test_near_toban_stop(self):
        self.assertEqual(planner.toban_home(bus("nagashima_north_south", "須崎")),
                         ("toban_ichi_to_suzaki", "須崎", 0))
        self.assertEqual(planner.toban_home(bus("nagashima_north_south", "宿前")),
                         ("toban_ichi_to_suzaki", "下平", 1))
        self.assertEqual(planner.toban_home(bus("nagashima_east_west", "開田碑前")),
                         ("toban_ichi_to_noda", "野田", 2))
        self.assertIsNone(planner.toban_home(bus("hiraizumi", "沢田橋")))
        self.assertIsNone(planner.toban_home(bus("nagashima_north_south", "東岳")))

    def test_town_afternoon_by_route_bus(self):
        # 午後に出かけるとコミュニティバスの帰りはないが、平泉駅→一関駅→一関線で帰れる
        result = planner.plan(bus("nagashima_north_south", "須崎"), "home", "town_office", TUE, "pm")
        main, alt = result["candidates"][0], toban(result)
        self.assertEqual(len(alt), 1)
        lines = [l["line"] for l in alt[0]["back"] if l.get("kind") == "ride"]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[-1], "一関線（東磐交通）")
        last = [l for l in alt[0]["back"] if l.get("kind") == "ride"][-1]
        self.assertEqual(last["to"], "須崎下平")
        self.assertIn("停留所の名前は「須崎下平」", last["note"])
        self.assertEqual(main["back_note"], planner.OTHER_BACK_HINT)

    def test_town_near_stop_adds_last_leg(self):
        result = planner.plan(bus("nagashima_north_south", "宿前"), "home", "joice", FRI, "pm")
        back = toban(result)[0]["back"]
        self.assertIn("家のバス停「宿前」からバスで約1分", back[-1]["text"])

    def test_transfer_times_connect(self):
        result = planner.plan(bus("nagashima_east_west", "野田"), "home", "yukyu_no_yu", THU, "pm")
        rides = [l for l in toban(result)[0]["back"] if l.get("kind") == "ride"]
        self.assertGreaterEqual(rides[1]["dep"], rides[0]["arr"] + planner.TRANSFER_MINUTES)

    def test_no_route_bus_on_weekend(self):
        result = planner.plan(bus("nagashima_north_south", "須崎"), "home", "town_office", SUN, "pm")
        self.assertEqual(toban(result), [])

    def test_no_route_bus_for_far_stop(self):
        result = planner.plan(bus("hiraizumi", "沢田橋"), "home", "town_office", MON, "pm")
        self.assertEqual(toban(result), [])

    def test_out_trip_uses_near_toban_stop(self):
        result = planner.plan(bus("nagashima_north_south", "宿前"), "home", "area_ichinoseki_station", TUE, "pm")
        backs = [c["back"] for c in result["candidates"]]
        self.assertTrue(any(l.get("line") == "一関線（東磐交通）" for back in backs for l in back))


class AllPatternsTest(unittest.TestCase):
    """全ルート・全バス停・全行き先・曜日・時間帯で、候補のつじつまが合うか"""

    def test_every_pattern(self):
        checked = 0
        for route in planner.COMMUNITY["routes"]:
            for stop in route["district_stops"]:
                settings = bus(route["id"], stop)
                for d in (MON, TUE, THU, FRI, SUN):
                    for period in ("am", "pm"):
                        for place_id in planner.PLACES:
                            with self.subTest(stop=stop, d=d, period=period, place=place_id):
                                self.check(settings, place_id, d, period)
                            checked += 1
        self.assertGreater(checked, 1000)

    def check(self, settings, place_id, d, period):
        result = planner.plan(settings, "home", place_id, d, period)
        near = nearby(result)
        if not near:
            return
        own_route = planner.find_route(settings["route_id"])["name"]
        near_stops = [s for _, s, _ in planner.nearby_stops(settings)]
        for c in near:
            ride = community_legs(c["back"])[-1]
            # 自分のルートではなく、家の近くのバス停まで行く便
            self.assertNotIn(own_route, ride["line"])
            self.assertIn(ride["to"], near_stops)
            # 行きで着いたあとに出る便
            go_rides = [l for l in c["go"] if l.get("kind") == "ride"]
            arrive = go_rides[-1]["arr"] if go_rides else planner.to_min(planner.PERIOD_START[period])
            first_ride = next(l for l in c["back"] if l.get("kind") == "ride")
            self.assertGreater(first_ride["dep"], arrive)
            # もとの候補は、家のバス停まで帰るコミュニティバスがないもの
            main = next(m for m in result["candidates"] if m["go"] is c["go"] and m["label"] != planner.NEARBY_LABEL)
            self.assertFalse(any(l["to"] == settings["stop"] for l in community_legs(main["back"])))
            if not any(l.get("near_minutes") is not None for l in main["back"]):
                self.assertEqual(main["back_note"], planner.OTHER_BACK_HINT)


class ResultPageTest(unittest.TestCase):
    """結果画面に、別のルートで帰る候補が出るか"""

    def render(self, settings, place_id, d, period):
        import app
        original = app.load_settings
        app.load_settings = lambda: settings
        try:
            client = app.app.test_client()
            return client.get("/result", query_string={"origin": "home", "place": place_id,
                                                       "date": d.isoformat(), "period": period})
        finally:
            app.load_settings = original

    def test_page_shows_nearby_candidate(self):
        res = self.render(bus("nagashima_east_west", "境田"), "joice", TUE, "am")
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn(planner.NEARBY_LABEL, html)
        self.assertIn("開田碑前", html)

    def test_page_shows_route_bus_candidate(self):
        res = self.render(bus("nagashima_north_south", "須崎"), "town_office", TUE, "pm")
        html = res.get_data(as_text=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(planner.TOBAN_LABEL, html)
        self.assertIn("東磐交通 一関線", html)

    def test_pages_render_for_nearby_patterns(self):
        cases = [(bus("nagashima_north_south", "山王"), "town_office", THU, "pm"),
                 (bus("nagashima_east_west", "開田碑前"), "iwate_hospital", FRI, "am"),
                 (bus("nagashima_north_south", "赤伏"), "area_yamanome", THU, "am"),
                 (bus("hiraizumi", "大平"), "iwai_hospital", THU, "am")]
        for settings, place_id, d, period in cases:
            with self.subTest(stop=settings["stop"], place=place_id):
                self.assertEqual(self.render(settings, place_id, d, period).status_code, 200)


if __name__ == "__main__":
    unittest.main()
