"""時刻表データから、行きと帰りの乗り換え候補を作る"""

import json
import math
from datetime import date, timedelta
from pathlib import Path

import jpholiday

DATA_DIR = Path(__file__).parent / "data"

WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]

TRANSFER_MINUTES = 5
ELDERLY_WALK_RATE = 1.5  # data の walk_minutes は一般的な「徒歩○分」（分速80m）。高齢者はその1.5倍かかるとみる
LONG_WALK_MINUTES = 20
MIN_STAY_TOWN = 30
MIN_STAY_OUT = 60
DEFAULT_STAY_OUT = 120
NEAR_STOP_MINUTES = 3
NEARBY_LABEL = "帰りは別のルートのバスで帰る"
TOBAN_LABEL = "帰りは一関駅をまわって、路線バスで帰る"
OTHER_BACK_HINT = "タクシーのほかに、バスで帰る方法もあります（下の候補）"
PERIOD_START = {"am": "9:00", "pm": "13:00"}
PERIOD_LABEL = {"am": "午前中", "pm": "午後"}
TRIP_LABEL = {"am": "午前", "pm": "午後"}

CENTER_POINTS = ["平泉駅", "役場", "ジョイス", "道の駅", "町民温泉"]

CATEGORIES = [
    {"id": "hospital", "label": "病院", "icon": "🏥"},
    {"id": "shopping", "label": "買い物", "icon": "🛒"},
    {"id": "town_office", "label": "役場", "icon": "🏛️"},
    {"id": "post_bank", "label": "郵便局・銀行", "icon": "📮"},
    {"id": "onsen", "label": "温泉", "icon": "♨️"},
    {"id": "station", "label": "平泉駅", "icon": "🚉"},
]

JR_TO_ICHI = ["jr_hiraizumi_to_ichinoseki"]
JR_FROM_ICHI = ["jr_ichinoseki_to_hiraizumi"]
BUS_TO_ICHI = ["bus_hiraizumi_to_ichinoseki"]
BUS_FROM_ICHI = ["bus_ichinoseki_to_hiraizumi"]
JR_TO_MIZU = ["jr_hiraizumi_to_mizusawa"]
JR_FROM_MIZU = ["jr_mizusawa_to_hiraizumi"]
IWAI_GO = ["bus_ichinoseki_to_iwai_left", "bus_ichinoseki_to_iwai_right", "bus_ichinoseki_to_iwai_shuttle"]
IWAI_BACK = ["bus_iwai_to_ichinoseki", "bus_iwai_to_ichinoseki_shuttle"]
IWATE_GO = ["bus_ichinoseki_to_iwate_hospital"]
IWATE_BACK = ["bus_iwate_hospital_to_ichinoseki"]

OUT_OPTIONS = {
    "iwai_hospital": [
        {"label": "JR で行く", "go": [JR_TO_ICHI, IWAI_GO], "back": [IWAI_BACK, JR_FROM_ICHI]},
        {"label": "路線バスで行く", "go": [BUS_TO_ICHI, IWAI_GO], "back": [IWAI_BACK, BUS_FROM_ICHI]},
    ],
    "iwate_hospital": [
        {"label": "JR で行く", "go": [JR_TO_ICHI, IWATE_GO], "back": [IWATE_BACK, JR_FROM_ICHI]},
        {"label": "路線バスで行く", "go": [BUS_TO_ICHI, IWATE_GO], "back": [IWATE_BACK, BUS_FROM_ICHI]},
    ],
    "isawa_hospital": [
        {"label": "JR で行く", "go": [JR_TO_MIZU, ["bus_mizusawa_to_isawa"]],
         "back": [["bus_isawa_to_mizusawa"], JR_FROM_MIZU]},
    ],
    "mizusawa_hospital": [
        {"label": "JR で行く", "go": [JR_TO_MIZU, ["bus_mizusawa_to_mizusawa_hospital"]],
         "back": [["bus_mizusawa_hospital_to_mizusawa"], JR_FROM_MIZU]},
    ],
    "area_ichinoseki_station": [
        {"label": "JR で行く", "go": [JR_TO_ICHI], "back": [JR_FROM_ICHI]},
        {"label": "路線バスで行く", "go": [BUS_TO_ICHI], "back": [BUS_FROM_ICHI]},
    ],
    "area_yamanome": [
        {"label": "路線バスで行く", "go": [BUS_TO_ICHI], "back": [BUS_FROM_ICHI], "yamanome": True},
    ],
    "area_mizusawa_station": [
        {"label": "JR で行く", "go": [JR_TO_MIZU], "back": [JR_FROM_MIZU]},
    ],
}

YAMANOME_FARE = 360

# コミュニティバスの停留所 → 東磐交通一関線で一関駅から帰る区間
# 時刻表の停留所名が違うときは、その名前を使う
TOBAN_HOME_STOPS = {
    "月舘": "toban_ichi_to_tsukidate",
    "二反田": "toban_ichi_to_nitanda",
    "滝の沢下": "toban_ichi_to_takinosawa",
    "滝の沢上": "toban_ichi_to_takinosawa",
    "須崎": "toban_ichi_to_suzaki",
    "下平": "toban_ichi_to_suzaki",
    "東松寺前": "toban_ichi_to_tomatsuji",
    "赤伏": "toban_ichi_to_akabushi",
    "山王": "toban_ichi_to_sanno",
    "野田": "toban_ichi_to_noda",
}


def load_json(name):
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


COMMUNITY = load_json("community_bus.json")
TRANSIT = load_json("transit.json")
PLACES_DATA = load_json("places.json")
SEGMENTS = {seg["id"]: seg for seg in TRANSIT["segments"]}
PLACES = {p["id"]: p for p in PLACES_DATA["places"]}
TAXIS = PLACES_DATA["taxis"]
STATION_WALK = PLACES_DATA["walk_from_station"]["minutes"]
BUS_FARE = COMMUNITY["fare"]["age_65_and_over"]


def to_min(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def to_hhmm(minutes):
    return f"{minutes // 60}:{minutes % 60:02d}"


def duration_text(minutes):
    h, m = divmod(minutes, 60)
    if h and m:
        return f"約{h}時間{m}分"
    if h:
        return f"約{h}時間"
    return f"約{m}分"


def date_label(d):
    return f"{d.month}月{d.day}日（{WEEKDAY_JA[d.weekday()]}）"


def is_holiday(d):
    return jpholiday.is_holiday(d)


def is_year_end(d):
    return (d.month == 12 and d.day >= 29) or (d.month == 1 and d.day <= 3)


def is_weekday_service(d):
    return d.weekday() < 5 and not is_holiday(d)


def find_route(route_id):
    for route in COMMUNITY["routes"]:
        if route["id"] == route_id:
            return route
    return None


def community_runs(route, d):
    if is_holiday(d) or is_year_end(d):
        return False
    return WEEKDAY_KEYS[d.weekday()] in route["days"]


def short_name(name):
    return name.split("（")[0]


def elderly_walk_minutes(place):
    """高齢者が歩いてかかる時間（分）。データがなければ None"""
    minutes = place["access"].get("walk_minutes")
    if minutes is None:
        return None
    return math.ceil(minutes * ELDERLY_WALK_RATE)


def walk_leg(from_stop, minutes):
    leg = text_leg("🚶", f"{from_stop}から歩いて約{minutes}分（ゆっくり歩いた場合）", "walk")
    leg["minutes"] = minutes
    return leg


def walk_between(a, b):
    """町の中心どうしを高齢者が歩いてかかる時間（分）。平泉駅をはさまない組み合わせは分からないので None"""
    if a == b:
        return 0
    if a == "平泉駅":
        minutes = STATION_WALK.get(b)
    elif b == "平泉駅":
        minutes = STATION_WALK.get(a)
    else:
        return None
    return math.ceil(minutes * ELDERLY_WALK_RATE) if minutes is not None else None


def walk_or_taxi_leg(a, b):
    minutes = walk_between(a, b)
    if minutes is None:
        return text_leg("🚶", f"{a}から{b}までは歩くかタクシー", "walk")
    if minutes > LONG_WALK_MINUTES:
        text = f"{a}から{b}まで歩くと約{minutes}分（ゆっくり歩いた場合）。遠いのでタクシーもおすすめします"
    else:
        text = f"{a}から{b}まで歩いて約{minutes}分（ゆっくり歩いた場合）"
    leg = text_leg("🚶", text, "walk")
    leg["minutes"] = minutes
    return leg


# ---------- 乗りもの1本ぶん（leg）を作る ----------

def ride_leg(icon, line, from_stop, dep, to_stop, arr, fare, fare_note=None):
    return {"kind": "ride", "icon": icon, "line": line, "from": from_stop, "dep": dep,
            "to": to_stop, "arr": arr, "fare": fare, "fare_note": fare_note, "show_arr": True}


def text_leg(icon, text, kind="taxi"):
    return {"kind": kind, "icon": icon, "text": text, "fare": None}


def trip_stops(route, trip):
    stops = [tuple(s) for s in trip["start"]]
    stops += list(zip(route["district_stops"], trip["district_times"]))
    stops += [tuple(s) for s in trip["end"]]
    return stops


def community_rides(d, from_stop, to_stop, route_ids=None):
    """その日のコミュニティバスで from_stop から to_stop へ行ける便を、出発の早い順に返す"""
    key = WEEKDAY_KEYS[d.weekday()]
    rides = []
    for route in COMMUNITY["routes"]:
        if route_ids and route["id"] not in route_ids:
            continue
        if not community_runs(route, d):
            continue
        for trip in route["trips"]:
            if trip["day"] != key:
                continue
            stops = trip_stops(route, trip)
            for i, (stop, time) in enumerate(stops):
                if stop != from_stop:
                    continue
                later = [t for s, t in stops[i + 1:] if s == to_stop]
                if later:
                    leg = ride_leg("🚌", f"コミュニティバス {route['name']}", from_stop, to_min(time),
                                   to_stop, to_min(later[0]), BUS_FARE)
                    leg["period"] = trip["period"]
                    leg["trip"] = (route["id"], trip["day"], trip["period"])
                    rides.append(leg)
                    break
    rides.sort(key=lambda leg: leg["dep"])
    return rides


def segment_rides(seg_id, d):
    seg = SEGMENTS[seg_id]
    weekday_ok = is_weekday_service(d)
    if seg["days"] == "weekday" and not weekday_ok:
        return []
    icon = "🚃" if seg["name"].startswith("JR") else "🚌"
    rides = []
    for i, (dep, arr) in enumerate(seg["times"]):
        if i < seg.get("weekday_only_first", 0) and not weekday_ok:
            continue
        rides.append(ride_leg(icon, seg["name"], seg["from"], to_min(dep), seg["to"], to_min(arr),
                              seg["fare"], seg.get("fare_note")))
    return rides


def leg_rides(seg_ids, d):
    rides = []
    for seg_id in seg_ids:
        rides += segment_rides(seg_id, d)
    rides.sort(key=lambda leg: (leg["dep"], leg["arr"]))
    return rides


def earliest_chain(legs_spec, d, after):
    """legs_spec の順に乗り継いで、after 以降でいちばん早くつながる組み合わせ"""
    chain = []
    t = after
    for seg_ids in legs_spec:
        ride = next((r for r in leg_rides(seg_ids, d) if r["dep"] >= t), None)
        if ride is None:
            return None
        chain.append(dict(ride))
        t = ride["arr"] + TRANSFER_MINUTES
    return chain


def all_chains(legs_spec, d):
    chains = []
    for first in leg_rides(legs_spec[0], d):
        rest = earliest_chain(legs_spec[1:], d, first["arr"] + TRANSFER_MINUTES)
        if rest is not None:
            chains.append([dict(first)] + rest)
    return chains


# ---------- 営業時間・受付時間 ----------

def hours_on(place, d):
    """その日の営業時間を [(開始, 終了)] で返す。休みなら []、分からなければ None"""
    if "seasonal_hours" in place:
        for season in place["seasonal_hours"]:
            if d.month in season["months"]:
                start, end = season["shop"].split("-")
                return [(to_min(start), to_min(end))]
        return None
    hours = place.get("hours")
    if hours is None:
        return None
    if is_holiday(d):
        if "holiday" in hours:
            return [tuple(to_min(x) for x in r.split("-")) for r in hours["holiday"]]
        if place.get("closed_on_holidays"):
            return []
    ranges = hours.get(WEEKDAY_KEYS[d.weekday()], [])
    return [tuple(to_min(x) for x in r.split("-")) for r in ranges]


def hours_text(ranges):
    return "・".join(f"{to_hhmm(a)}〜{to_hhmm(b)}" for a, b in ranges)


def open_check(place, d, arrive):
    """着く時刻に開いているかを {"ok": bool, "text": str} で返す"""
    ranges = hours_on(place, d)
    name = short_name(place["name"])
    if ranges is None:
        return None
    if not ranges:
        return {"ok": False, "text": f"{name}はこの日はお休みです"}
    for start, end in ranges:
        if start <= arrive < end:
            return {"ok": True, "text": None}
    if arrive < ranges[0][0]:
        return {"ok": True, "text": None}
    for (_, end), (start, _) in zip(ranges, ranges[1:]):
        if end <= arrive < start:
            return {"ok": False, "text": f"着く時刻（{to_hhmm(arrive)}）はお昼休みです。{to_hhmm(start)} から開きます"}
    return {"ok": False, "text": f"着く時刻（{to_hhmm(arrive)}）には閉まっています（{hours_text(ranges)}）"}


def reception_check(place, d):
    reception = place.get("reception")
    if reception is None:
        return None
    key = WEEKDAY_KEYS[d.weekday()]
    if key not in reception["days"] or (is_holiday(d) and place.get("closed_on_holidays")):
        return {"closed": True, "until": None, "note": reception.get("note")}
    until = to_min(reception["until"]) if reception["until"] else None
    return {"closed": False, "until": until, "note": reception.get("note")}


# ---------- 運賃 ----------

def fare_summary(legs):
    parts = []
    total = 0
    unknown = []
    for leg in legs:
        if leg["kind"] == "taxi":
            unknown.append("タクシー代")
        elif leg["kind"] == "ride":
            if leg["fare"] is None:
                unknown.append(f"{leg['line']}（確認中）")
            else:
                total += leg["fare"]
                kind = "JR" if leg["icon"] == "🚃" else "バス"
                parts.append(f"{kind}{leg['fare']}円")
    if not parts and not unknown:
        return "0円（歩き）"
    if not parts:
        return "・".join(unknown) + "（電話で確認）"
    text = f"{total}円"
    if len(parts) > 1:
        text += f"（{' + '.join(parts)}）"
    if unknown:
        text += " ＋ " + "・".join(unknown)
    return text


# ---------- 行きの最初の部分（家や町の中心から平泉駅などへ） ----------

def first_part(settings, origin, d, period, to_stop):
    """出発地から町の中の to_stop まで。(legs, 着く時刻, お知らせ) を返す"""
    notices = []
    start = to_min(PERIOD_START[period])
    uses_bus = settings.get("mode") == "bus"

    if origin == "home":
        if uses_bus:
            route = find_route(settings["route_id"])
            if community_runs(route, d):
                rides = [r for r in community_rides(d, settings["stop"], to_stop, [route["id"]])
                         if r["period"] == period]
                if rides:
                    return [rides[0]], rides[0]["arr"], notices
                if to_stop != "平泉駅":
                    rides = [r for r in community_rides(d, settings["stop"], "平泉駅", [route["id"]])
                             if r["period"] == period]
                    if rides:
                        walk = walk_or_taxi_leg("平泉駅", to_stop)
                        return [rides[0], walk], rides[0]["arr"] + (walk.get("minutes") or 10), notices
            else:
                notices.append(f"この日は{route['name']}のコミュニティバスが走りません。家からはタクシーをおすすめします")
        return [text_leg("🚕", f"家から{to_stop}までタクシー（{to_hhmm(start)}ごろに着くとして調べています）")], start, notices

    if origin == to_stop:
        return [], start, notices

    rides = [r for r in community_rides(d, origin, to_stop) if r["period"] == period]
    if rides and to_stop == "平泉駅":
        return [rides[0]], rides[0]["arr"], notices
    walk = walk_or_taxi_leg(origin, to_stop)
    return [walk], start + (walk.get("minutes") or 0), notices


def home_bus_rides(settings, d, from_stop, after):
    if settings.get("mode") != "bus":
        return []
    route = find_route(settings["route_id"])
    return [r for r in community_rides(d, from_stop, settings["stop"], [route["id"]]) if r["dep"] >= after]


DAY_JA = {"mon": "月曜", "tue": "火曜", "wed": "水曜", "thu": "木曜", "fri": "金曜", "sat": "土曜", "sun": "日曜"}


def direct_trips(settings, stop):
    """家のバス停から乗って、stop で直接降りられる便"""
    route = find_route(settings["route_id"])
    trips = []
    for trip in route["trips"]:
        stops = trip_stops(route, trip)
        for i, (s, _) in enumerate(stops):
            if s == settings["stop"]:
                later = [t for s2, t in stops[i + 1:] if s2 == stop]
                if later:
                    trips.append({"day": trip["day"], "period": trip["period"], "arr": later[0],
                                  "label": f"{DAY_JA[trip['day']]}の{TRIP_LABEL[trip['period']]}の便（{later[0]} 着）"})
                break
    return trips


def direct_guide(settings, origin, place):
    """行き先のバス停に直接止まる便が一部の曜日だけのとき、その案内を返す"""
    if origin != "home" or settings.get("mode") != "bus" or place["area"] != "town":
        return None
    stop = place["access"]["stop"]
    if stop == "平泉駅":
        return None
    route = find_route(settings["route_id"])
    trips = direct_trips(settings, stop)
    if len(trips) == len(route["trips"]):
        return None
    return {"stop": stop, "trips": trips, "days": {t["day"] for t in trips},
            "walk": walk_between("平泉駅", stop)}


LAST_BUS_NOTE = "帰りのバスはこの1本だけです。もっとゆっくりしたいときは、帰りはタクシーになります"


def is_last_home_bus(settings, d, ride):
    """この便のあとに、家に帰るコミュニティバスがもうないか"""
    for stop in {ride["from"], "平泉駅"}:
        if any(r["trip"] != ride["trip"] for r in home_bus_rides(settings, d, stop, ride["dep"] + 1)):
            return False
    return True


def taxi_home_leg(from_stop):
    return text_leg("🚕", f"{from_stop}から家まではタクシーをおすすめします")


def nearby_stops(settings):
    """家のバス停の近くに止まる、ほかのルートのバス停。[(route_id, バス停, 家のバス停からバスで何分)]
    位置のデータがないので、家のルートでバスで NEAR_STOP_MINUTES 分以内に通るバス停を近いとみる"""
    if settings.get("mode") != "bus":
        return []
    route = find_route(settings["route_id"])
    times = dict(zip(route["district_stops"], route["trips"][0]["district_times"]))
    home = settings.get("stop")
    if home not in times:
        return []
    near = []
    for other in COMMUNITY["routes"]:
        if other["id"] == route["id"]:
            continue
        for stop in other["district_stops"]:
            if stop in times:
                minutes = abs(to_min(times[stop]) - to_min(times[home]))
                if minutes <= NEAR_STOP_MINUTES:
                    near.append((other["id"], stop, minutes))
    return near


def nearby_home_rides(settings, d, from_stop, after):
    """家に帰るバスがないときに使える、家の近くのバス停まで行くほかのルートの便"""
    rides = []
    for route_id, stop, minutes in nearby_stops(settings):
        for ride in community_rides(d, from_stop, stop, [route_id]):
            if ride["dep"] >= after:
                ride["near_minutes"] = minutes
                rides.append(ride)
    rides.sort(key=lambda r: r["dep"])
    return rides


def from_nearby_stop_leg(settings, ride):
    if ride["near_minutes"] == 0:
        return None
    return text_leg("🚕", f"{ride['to']}から家までは、歩くかタクシー"
                          f"（「{ride['to']}」は、家のバス停「{settings['stop']}」からバスで約{ride['near_minutes']}分のところです）")


def back_candidate(base, back, ready_at, label):
    """候補 base の帰りを、家のバス停か家の近くのバス停まで帰る back に入れかえた候補"""
    ride = next(leg for leg in back if leg.get("near_minutes") is not None)
    first = next(i for i, leg in enumerate(back) if leg["kind"] == "ride")
    stay = back[first]["dep"] - sum(leg.get("minutes") or 0 for leg in back[:first]) - ready_at
    where = "家のバス停" if ride["near_minutes"] == 0 else f"家の近くのバス停「{ride['to']}」"
    return dict(base, label=label, back=back, back_warnings=[],
                back_note=f"いつものバスでは帰れませんが、{ride['line']}で{where}まで帰れます",
                stay=duration_text(stay) if stay > 0 else None, fare_back=fare_summary(back),
                recommended=False)


# ---------- 町の中の行き先 ----------

def plan_town(settings, origin, place, d, period):
    stop = place["access"]["stop"]
    walk = elderly_walk_minutes(place) or 0
    go, arrive_stop, notices = first_part(settings, origin, d, period, stop)
    arrive = arrive_stop + walk
    if walk:
        go.append(walk_leg(stop, walk))
    elif place["access"].get("walk_minutes") is None and place["category"] != "station":
        go.append(text_leg("🚶", f"{stop}から歩きます", "walk"))

    warnings = []
    check = open_check(place, d, arrive)
    if check and not check["ok"]:
        warnings.append(check["text"])

    ready = arrive + MIN_STAY_TOWN + walk
    back = []
    stay = None
    rides = home_bus_rides(settings, d, stop, ready)
    if not rides and stop != "平泉駅":
        to_station = walk_or_taxi_leg(stop, "平泉駅")
        rides = home_bus_rides(settings, d, "平泉駅", ready + (to_station.get("minutes") or 10))
        if rides:
            back.append(to_station)
    back_note = None
    back_warnings = []
    if rides:
        back.append(rides[0])
        stay = rides[0]["dep"] - arrive - walk
        if is_last_home_bus(settings, d, rides[0]):
            back_note = LAST_BUS_NOTE
    else:
        back.append(taxi_home_leg(short_name(place["name"])))
        if settings.get("mode") == "bus":
            back_warnings.append("この日は帰りのコミュニティバスがありません。帰りはタクシーをおすすめします")

    candidate = {
        "label": "コミュニティバスで行く" if any(l["kind"] == "ride" for l in go) else "行き方",
        "go": go, "back": back, "warnings": warnings, "back_warnings": back_warnings,
        "info": None, "back_note": back_note,
        "stay": duration_text(stay) if stay else None,
        "fare_go": fare_summary(go), "fare_back": fare_summary(back),
    }
    candidates = [candidate]
    if not rides:
        near_back = nearby_town_back(settings, d, stop, ready)
        if near_back:
            candidates.append(back_candidate(candidate, near_back, arrive + walk, NEARBY_LABEL))
        toban_back = toban_town_back(settings, d, stop, ready)
        if toban_back:
            candidates.append(back_candidate(candidate, toban_back, arrive + walk, TOBAN_LABEL))
        if len(candidates) > 1:
            candidate["back_warnings"] = ["家のバス停まで帰るコミュニティバスはありません"]
            candidate["back_note"] = OTHER_BACK_HINT
    return candidates, notices


def nearby_town_back(settings, d, stop, ready):
    """町の中の行き先から、ほかのルートのバスで家の近くのバス停まで帰る。乗るバス停でも平泉駅からでもよい"""
    back = []
    rides = nearby_home_rides(settings, d, stop, ready)
    if not rides and stop != "平泉駅":
        to_station = walk_or_taxi_leg(stop, "平泉駅")
        rides = nearby_home_rides(settings, d, "平泉駅", ready + (to_station.get("minutes") or 10))
        if rides:
            back.append(to_station)
    if not rides:
        return None
    back.append(rides[0])
    home_leg = from_nearby_stop_leg(settings, rides[0])
    if home_leg:
        back.append(home_leg)
    return back


# ---------- 一関・水沢の行き先 ----------

def last_bus_note(settings, d, back):
    """帰りの最後に乗るコミュニティバスが、その日最後の便ならお知らせを返す"""
    if not back or back[-1].get("kind") != "ride" or not back[-1]["line"].startswith("コミュニティバス"):
        return None
    return LAST_BUS_NOTE if is_last_home_bus(settings, d, back[-1]) else None


def ichinoseki_back_parts(option):
    """帰りのうち、一関に着くところまで。平泉へ戻る電車や路線バスは含めない"""
    parts = []
    for group in option["back"]:
        if SEGMENTS[group[0]]["to"] in ("平泉", "平泉駅前"):
            break
        parts.append(group)
    return parts


def toban_home(settings):
    """家に帰るのに使える東磐交通一関線の区間。(区間, 一関線が止まるバス停, 家のバス停からバスで何分)
    家のバス停に止まらなければ、家のルートでバスで NEAR_STOP_MINUTES 分以内のバス停を探す"""
    home = settings.get("stop")
    if home in TOBAN_HOME_STOPS:
        return TOBAN_HOME_STOPS[home], home, 0
    if settings.get("mode") != "bus":
        return None
    route = find_route(settings["route_id"])
    times = dict(zip(route["district_stops"], route["trips"][0]["district_times"]))
    if home not in times:
        return None
    near = [(abs(to_min(times[s]) - to_min(times[home])), s) for s in TOBAN_HOME_STOPS if s in times]
    near = [(minutes, s) for minutes, s in near if minutes <= NEAR_STOP_MINUTES]
    if not near:
        return None
    minutes, stop = min(near)
    return TOBAN_HOME_STOPS[stop], stop, minutes


def finish_toban_back(settings, back, minutes):
    """一関線に乗る帰りに、乗り場と停留所のお知らせ、近くの停留所から家までをつける"""
    ride = back[-1]
    ride["near_minutes"] = minutes
    notes = ["一関駅前から乗ります"]
    if minutes == 0 and settings.get("stop") != ride["to"]:
        notes.append(f"停留所の名前は「{ride['to']}」です")
    ride["note"] = "。".join(notes)
    home_leg = from_nearby_stop_leg(settings, ride)
    return back + [home_leg] if home_leg else back


def toban_town_back(settings, d, stop, ready):
    """町の中の行き先から、平泉駅→一関駅とまわって、東磐交通一関線で家の近くまで帰る"""
    home = toban_home(settings)
    if home is None:
        return None
    seg_id, _, minutes = home
    back = []
    if stop != "平泉駅":
        to_station = walk_or_taxi_leg(stop, "平泉駅")
        back.append(to_station)
        ready += to_station.get("minutes") or 10
    chains = [c for c in all_chains([JR_TO_ICHI + BUS_TO_ICHI, [seg_id]], d) if c[0]["dep"] >= ready]
    if not chains:
        return None
    soonest = min(c[-1]["arr"] for c in chains)
    chain = max((c for c in chains if c[-1]["arr"] == soonest), key=lambda c: (c[0]["dep"], -c[0]["fare"]))
    return finish_toban_back(settings, back + chain, minutes)


def toban_return(settings, d, option, ready):
    """一関駅から東磐交通で、自宅付近の停留所まで帰る便。乗れる中でいちばん遅く帰れる組み合わせ"""
    home = toban_home(settings)
    if home is None or option.get("yamanome"):
        return None
    seg_id, _, minutes = home
    buses = segment_rides(seg_id, d)
    if not buses:
        return None
    parts = ichinoseki_back_parts(option)
    if parts:
        matched = []
        for chain in all_chains(parts, d):
            if chain[0]["dep"] < ready or chain[-1]["to"] not in ("一関駅前", "一関駅", "一ノ関"):
                continue
            usable = [b for b in buses if b["dep"] >= chain[-1]["arr"] + TRANSFER_MINUTES]
            if usable:
                matched.append(chain + [dict(usable[0])])
        if not matched:
            return None
        back = max(matched, key=lambda chain: chain[0]["dep"])
    else:
        usable = [b for b in buses if b["dep"] >= ready + TRANSFER_MINUTES]
        if not usable:
            return None
        back = [dict(usable[-1])]
    return finish_toban_back(settings, back, minutes)


def hiraizumi_bus_return(d, option, ready):
    """一関駅前から一関平泉線で平泉駅前まで帰る。乗れる中でいちばん遅く帰れる組み合わせ"""
    if option.get("yamanome"):
        return None
    buses = segment_rides("bus_ichinoseki_to_hiraizumi", d)
    parts = ichinoseki_back_parts(option)
    if not buses or not parts:
        return None
    matched = []
    for chain in all_chains(parts, d):
        if chain[0]["dep"] < ready or chain[-1]["to"] not in ("一関駅前", "一関駅", "一ノ関"):
            continue
        usable = [b for b in buses if b["dep"] >= chain[-1]["arr"] + TRANSFER_MINUTES]
        if usable:
            matched.append(chain + [dict(usable[-1])])
    if not matched:
        return None
    back = max(matched, key=lambda chain: chain[0]["dep"])
    back.append(taxi_home_leg("平泉駅"))
    return back


def choose_back(settings, d, option, ready, place):
    """帰りの便を選ぶ。家に帰るコミュニティバスに間に合う中で、いちばん遅い便にする"""
    chains = [c for c in all_chains(option["back"], d) if c[0]["dep"] >= ready]
    if not chains:
        return None, ["この時間から帰る電車・バスがありません。タクシーで帰ることになります"]
    for home_bus in home_bus_rides(settings, d, "平泉駅", 0):
        ok = [c for c in chains if c[-1]["arr"] <= home_bus["dep"] - TRANSFER_MINUTES]
        if ok:
            chain = max(ok, key=lambda c: c[0]["dep"])
            return chain + [home_bus], []
    late = [c for c in chains if c[0]["dep"] >= ready - MIN_STAY_OUT + DEFAULT_STAY_OUT]
    chain = late[0] if late else chains[-1]
    warnings = []
    if settings.get("mode") == "bus":
        warnings.append("帰りのコミュニティバスに間に合いません。平泉駅から家まではタクシーをおすすめします")
    return chain + [taxi_home_leg("平泉駅")], warnings


def community_legs_home(settings, back):
    return [leg for leg in back if leg.get("kind") == "ride" and leg["line"].startswith("コミュニティバス")
            and leg["to"] == settings.get("stop")]


def nearby_out_back(settings, d, option, ready):
    """平泉駅まで電車やバスで戻って、ほかのルートのコミュニティバスで家の近くのバス停まで帰る"""
    chains = [c for c in all_chains(option["back"], d) if c[0]["dep"] >= ready]
    for ride in nearby_home_rides(settings, d, "平泉駅", 0):
        ok = [c for c in chains if c[-1]["arr"] <= ride["dep"] - TRANSFER_MINUTES]
        if ok:
            back = max(ok, key=lambda c: c[0]["dep"]) + [ride]
            if option.get("yamanome"):
                apply_yamanome(back)
            home_leg = from_nearby_stop_leg(settings, ride)
            return back + [home_leg] if home_leg else back
    return None


def apply_yamanome(legs):
    for leg in legs:
        if leg.get("line", "").startswith("一関平泉線"):
            if leg["to"] == "一関駅前":
                leg["to"] = "山目駅前"
                leg["show_arr"] = False
                leg["note"] = f"一関駅前 {to_hhmm(leg['arr'])} 着のバスです。山目駅前はその少し前に着きます"
            elif leg["from"] == "一関駅前":
                leg["from"] = "山目駅前"
                leg["note"] = f"一関駅前を {to_hhmm(leg['dep'])} に出るバスです。山目駅前にはその少しあとに来ます"
            leg["fare"] = YAMANOME_FARE


def plan_out(settings, origin, place, d, period):
    go_start, at_station, notices = first_part(settings, origin, d, period, "平泉駅")
    walk = elderly_walk_minutes(place)
    reception = reception_check(place, d)
    if reception and reception["closed"]:
        notices.append(f"{short_name(place['name'])}の外来は、この日はお休みです")

    candidates = []
    for option in OUT_OPTIONS[place["id"]]:
        chain = earliest_chain(option["go"], d, at_station + TRANSFER_MINUTES)
        if chain is None:
            continue
        if option.get("yamanome"):
            apply_yamanome(chain)
        arrive_stop = chain[-1]["arr"]
        arrive = arrive_stop + (walk or 0)
        go = go_start + chain
        warnings = []
        late = bool(reception and reception["until"] and arrive > reception["until"])
        if late:
            warnings.append(f"受付に間に合いません（受付は {to_hhmm(reception['until'])} まで。着くのは {to_hhmm(arrive)}）")
        if walk:
            go.append(walk_leg(chain[-1]["to"], walk))
        elif walk is None:
            go.append(text_leg("🚶", f"{chain[-1]['to']}から医院までは、歩くかタクシー", "walk"))

        trip_warnings = list(warnings)
        back, back_warnings = choose_back(settings, d, option, arrive_stop + MIN_STAY_OUT, place)
        if back is None:
            back = [text_leg("🚕", "帰りはタクシーをおすすめします")]
        stay = None
        if back[0]["kind"] == "ride":
            stay = back[0]["dep"] - arrive_stop
        if option.get("yamanome"):
            apply_yamanome(back)

        info = None
        if reception and reception["until"] and not late:
            info = f"病院の受付は{to_hhmm(reception['until'])}までです"
        back_note = last_bus_note(settings, d, back)
        toban_back = toban_return(settings, d, option, arrive_stop + MIN_STAY_OUT)
        taxi_home = bool(back_warnings) or any(leg.get("kind") == "taxi" for leg in back)
        # 路線バスの行き、またはコミュニティバスに間に合わない帰りは、東磐交通で帰る
        used_toban = False
        if toban_back and (option["label"] == "路線バスで行く" or taxi_home):
            back = toban_back
            back_warnings = []
            stay = toban_back[0]["dep"] - arrive_stop if toban_back[0]["kind"] == "ride" else None
            back_note = None
            used_toban = True
        elif toban_back and back_note == LAST_BUS_NOTE:
            back_note = "コミュニティバスの帰りはこの1本だけです。もっとゆっくりするときは、路線バスで帰れます"
        bus_back = None
        if toban_back is None:
            later = hiraizumi_bus_return(d, option, arrive_stop + MIN_STAY_OUT)
            longer = later and (back[0].get("kind") != "ride" or later[0]["dep"] > back[0]["dep"])
            if longer and option["label"] == "路線バスで行く" and taxi_home:
                bus_back = later
            elif longer and option["label"] != "路線バスで行く":
                bus_back = later
                if back_note == LAST_BUS_NOTE:
                    back_note = "コミュニティバスの帰りはこの1本だけです。もっとゆっくりするときは、路線バスで平泉駅まで帰って、そこからタクシーになります"
        candidates.append({
            "label": option["label"], "go": go, "back": back, "warnings": warnings,
            "back_warnings": back_warnings, "info": info, "back_note": back_note,
            "stay": duration_text(stay) if stay else None, "late": late,
            "fare_go": fare_summary(go), "fare_back": fare_summary(back),
        })
        main = candidates[-1]
        if bus_back and not taxi_home:
            bus_stay = bus_back[0]["dep"] - arrive_stop if bus_back[0]["kind"] == "ride" else None
            by = option["label"].removesuffix("で行く")
            candidates.append({
                "label": f"{by}で行って、路線バスで帰る",
                "go": go, "back": bus_back, "warnings": trip_warnings, "back_warnings": [],
                "info": info, "back_note": None,
                "stay": duration_text(bus_stay) if bus_stay else None, "late": late,
                "fare_go": fare_summary(go), "fare_back": fare_summary(bus_back),
            })
        elif taxi_home and bus_back:
            back = bus_back
            back_warnings = []
            stay = bus_back[0]["dep"] - arrive_stop if bus_back[0]["kind"] == "ride" else None
            back_note = None
            candidates[-1].update({
                "back": back, "back_warnings": back_warnings, "back_note": back_note,
                "stay": duration_text(stay) if stay else None, "fare_back": fare_summary(back),
            })
        if not community_legs_home(settings, main["back"]):
            near_back = nearby_out_back(settings, d, option, arrive_stop + MIN_STAY_OUT)
            if near_back:
                candidates.append(back_candidate(main, near_back, arrive_stop, NEARBY_LABEL))
                if not used_toban:
                    main["back_note"] = OTHER_BACK_HINT
        if toban_back and not used_toban:
            toban_stay = toban_back[0]["dep"] - arrive_stop if toban_back[0]["kind"] == "ride" else None
            by = option["label"].removesuffix("で行く")
            candidates.append({
                "label": f"{by}で行って、路線バスで帰る",
                "go": go, "back": toban_back, "warnings": trip_warnings, "back_warnings": [],
                "info": info, "back_note": None,
                "stay": duration_text(toban_stay) if toban_stay else None, "late": late,
                "fare_go": fare_summary(go), "fare_back": fare_summary(toban_back),
            })

    if candidates and all(c.get("late") for c in candidates):
        candidates.insert(0, taxi_candidate(go_start, at_station, place, d, reception))
    if not candidates:
        notices.append("この日・この時間からは、乗りつげる電車やバスがありません。タクシーをおすすめします")
    return candidates, notices


def taxi_candidate(go_start, at_station, place, d, reception):
    first_seg = OUT_OPTIONS[place["id"]][0]["go"][0]
    chain = earliest_chain([first_seg], d, at_station + TRANSFER_MINUTES)
    go = list(go_start)
    warnings = []
    if chain:
        go += chain
        go.append(text_leg("🚕", f"{chain[0]['to']}駅から{short_name(place['name'])}までタクシー（時間と運賃は電話で確認）"))
        if chain[0]["arr"] > reception["until"]:
            warnings.append("駅に着く時刻で、もう受付に間に合いません。別の日をおすすめします")
    else:
        go.append(text_leg("🚕", f"{short_name(place['name'])}までタクシー"))
    info = f"受付は {to_hhmm(reception['until'])} まで。駅からタクシーにすると早く着きます"
    return {
        "label": "駅からタクシーで行く（おすすめ）", "go": go, "back": [], "warnings": warnings,
        "back_warnings": [], "info": info, "stay": None, "late": False,
        "fare_go": fare_summary(go), "fare_back": None, "recommended": True,
    }


# ---------- 画面4に出すまとめ ----------

def journey_icons(origin, settings, candidate, place, category):
    if origin == "home" and settings.get("stop"):
        steps = [{"icon": "🚏", "label": settings["stop"]}]
    elif origin == "home":
        steps = [{"icon": "🏠", "label": "出発"}]
    else:
        steps = [{"icon": "📍", "label": origin}]
    names = {"🚌": "バス", "🚃": "JR", "🚕": "タクシー", "🚶": "歩く"}
    for leg in candidate["go"]:
        label = names.get(leg["icon"], "")
        if leg.get("minutes"):
            label += f"{leg['minutes']}分"
        steps.append({"icon": leg["icon"], "label": label})
    steps.append({"icon": category["icon"], "label": short_name(place["name"])})
    return steps


def ride_lines(candidates):
    """候補に実際に出てくる路線名。タクシーの案内も数える"""
    lines = []
    for candidate in candidates or []:
        for leg in list(candidate.get("go") or []) + list(candidate.get("back") or []):
            if leg.get("line"):
                lines.append(leg["line"])
            elif leg.get("kind") == "taxi":
                lines.append("タクシー")
    return lines


def transports_for(place, d, settings, candidates):
    lines = ride_lines(candidates)
    items = []
    if is_runrun_day(d):
        items.append({
            "icon": "🚌", "name": "平泉巡回バス るんるん",
            "fare": None, "note": "土日祝日の季節運行。平泉駅前から 10:15 から 30分おき",
            "phones": [{"label": "岩手県交通 一関営業所", "number": "0191-23-4250"}], "times": None,
        })
    if place["area"] == "ichinoseki":
        items.append({
            "icon": "🚌", "name": "路線バス（岩手県交通 一関平泉線）",
            "fare": "平泉駅前から一関駅前まで370円（山目駅前まで360円）", "note": None,
            "phones": [{"label": "岩手県交通 一関営業所", "number": "0191-23-4250"}], "times": "ichihira",
        })
    if place["area"] in ("ichinoseki", "mizusawa"):
        items.append({
            "icon": "🚃", "name": "鉄道（JR東北本線・平泉駅）",
            "fare": "平泉から一ノ関まで210円、水沢まで330円", "note": None, "phones": [], "times": "jr",
        })
    if place["category"] == "hospital" and place["area"] == "ichinoseki" and "access" in place and place["access"].get("via"):
        items.append({
            "icon": "🚌", "name": "一関駅から病院へのバス（岩手県交通）",
            "fare": "岩手病院前まで310円、磐井・南光病院まで320円", "note": "平日のみ",
            "phones": [{"label": "岩手県交通 一関営業所", "number": "0191-23-4250"}], "times": "ichinoseki_hospital",
        })
    if place["category"] == "hospital" and place["area"] == "mizusawa" and place["access"].get("via"):
        items.append({
            "icon": "🚌", "name": "水沢駅から病院へのバス（水岩線）",
            "fare": "胆沢病院まで310円", "note": "平日のみ",
            "phones": [{"label": "岩手県交通 胆江営業所", "number": "0197-35-2185"}], "times": "mizusawa_hospital",
        })
    if place["area"] == "ichinoseki" or settings.get("route_id") in ("nagashima_east_west", "nagashima_north_south"):
        items.append({
            "icon": "🚌", "name": "路線バス（東磐交通 一関線）",
            "fare": "一関駅から長島まで480円、月館まで660円",
            "note": "平日のみ（土・日は運休）。一関駅と長島・須崎下平・東松寺前・赤伏・山王方面",
            "phones": [{"label": "東磐交通", "number": "0191-47-3434"}], "times": "toban_ichinoseki",
        })
    items.append({
        "icon": "🚌", "name": "路線バス（東磐交通 平泉・げいび渓線）",
        "fare": "平泉駅前からげいび渓まで800円（道の駅平泉まで300円）",
        "note": "観光向けの季節運行。2026年4月29日〜11月23日。火・水曜は原則運休",
        "phones": [{"label": "東磐交通", "number": "0191-47-3434"}], "times": "geibikei",
    })
    items.append({
        "icon": "🚕", "name": "タクシー", "fare": None, "note": None,
        "phones": [{"label": t["name"], "number": t["phone"]} for t in TAXIS], "times": None,
    })
    def used(item):
        name = item["name"]
        if "一関平泉線" in name:
            return any("一関平泉線" in line for line in lines)
        if name.startswith("鉄道"):
            return any(line.startswith("JR") for line in lines)
        if "水岩線" in name:
            return any("水岩線" in line for line in lines)
        if "病院へのバス" in name:
            return any(any(word in line for word in ("循環", "磐井", "岩手病院")) for line in lines)
        if "東磐交通 一関線" in name:
            return any("一関線（東磐交通）" in line for line in lines)
        if "げいび渓" in name:
            return any("げいび渓" in line for line in lines)
        if "るんるん" in name:
            return any("るんるん" in line for line in lines)
        if name == "タクシー":
            return True
        return False
    return [item for item in items if used(item)]


def is_runrun_day(d):
    if d.year != 2026:
        return False
    if date(2026, 8, 13) <= d <= date(2026, 8, 16):
        return True
    in_season = date(2026, 4, 11) <= d <= date(2026, 11, 29)
    return in_season and (d.weekday() >= 5 or is_holiday(d))


def plan(settings, origin, place_id, d, period):
    place = PLACES[place_id]
    category = next(c for c in CATEGORIES if c["id"] == place["category"])
    if place["area"] == "town":
        candidates, notices = plan_town(settings, origin, place, d, period)
        guide = direct_guide(settings, origin, place)
        key = WEEKDAY_KEYS[d.weekday()]
        if guide and guide["trips"] and not any(t["day"] == key and t["period"] == period for t in guide["trips"]):
            labels = "、".join(t["label"] for t in guide["trips"])
            notices.append(f"{labels}なら、バス停「{guide['stop']}」で直接降りられます")
    else:
        candidates, notices = plan_out(settings, origin, place, d, period)
    journey = journey_icons(origin, settings, candidates[0], place, category) if candidates else []
    return {
        "place": place, "category": category,
        "date_label": date_label(d), "period_label": PERIOD_LABEL[period],
        "notices": notices, "candidates": candidates, "journey": journey,
        "transports": transports_for(place, d, settings, candidates),
    }


# ---------- 画面3の日にちボタン ----------

def day_choice(route, guide, d, label=None, next_run=False):
    runs = community_runs(route, d) if route else True
    return {
        "value": d.isoformat(),
        "label": f"{label}（{WEEKDAY_JA[d.weekday()]}）" if label else date_label(d),
        "sub": date_label(d) if label else "",
        "runs": runs,
        "direct": bool(guide and runs and WEEKDAY_KEYS[d.weekday()] in guide["days"]),
        "next_run": next_run,
    }


def date_choices(settings, today, guide=None):
    route = find_route(settings["route_id"]) if settings.get("mode") == "bus" else None
    choices = [day_choice(route, guide, today + timedelta(days=i), label)
               for i, label in enumerate(["今日", "明日", "あさって"])]
    if route and not any(c["runs"] for c in choices):
        d = next_bus_day(settings, today)
        if d:
            choices.append(day_choice(route, guide, d, next_run=True))
    return choices


def later_choices(settings, today, guide, shown, days=42):
    """「それ以外の日」で選べる、あさってより先の日"""
    route = find_route(settings["route_id"]) if settings.get("mode") == "bus" else None
    taken = {c["value"] for c in shown}
    return [c for c in (day_choice(route, guide, today + timedelta(days=i)) for i in range(3, days))
            if c["value"] not in taken]


def next_direct_day(settings, today, guide):
    if not guide or not guide["trips"]:
        return None
    route = find_route(settings["route_id"])
    for i in range(15):
        d = today + timedelta(days=i)
        if community_runs(route, d) and WEEKDAY_KEYS[d.weekday()] in guide["days"]:
            return d
    return None


def next_bus_day(settings, today):
    if settings.get("mode") != "bus":
        return None
    route = find_route(settings["route_id"])
    for i in range(15):
        d = today + timedelta(days=i)
        if community_runs(route, d):
            return d
    return None
