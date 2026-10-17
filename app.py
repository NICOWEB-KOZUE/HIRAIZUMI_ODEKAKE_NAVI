import json
from datetime import date
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, url_for

import planner

app = Flask(__name__)

SETTINGS_FILE = Path(__file__).parent / "data" / "user_settings.json"

PLACE_GROUPS = {
    "hospital": [
        {"title": "町内の医院", "ids": ["hiraizumi_naika", "hiraizumi_shika", "sasaki_shika", "asuka_yakkyoku"]},
        {"title": "一関・水沢の病院", "ids": ["iwai_hospital", "iwate_hospital", "isawa_hospital", "mizusawa_hospital"]},
        {"title": "一関・水沢の医院", "ids": ["area_ichinoseki_station", "area_yamanome", "area_mizusawa_station"]},
    ],
}


def load_settings():
    if not SETTINGS_FILE.exists():
        return None
    with open(SETTINGS_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def home_label(settings):
    if settings.get("mode") == "bus" and settings.get("stop"):
        return f"自宅（バス停：{settings['stop']}）"
    return "自宅"


@app.template_filter("hhmm")
def hhmm_filter(minutes):
    return planner.to_hhmm(minutes) if minutes is not None else ""


SEASONS = ("spring", "summer", "autumn", "winter")


def season_of(day):
    if day.month in (4, 5):
        return "spring"
    if day.month in (6, 7, 8):
        return "summer"
    if day.month in (9, 10, 11):
        return "autumn"
    return "winter"


def page_season(day=None):
    requested = request.args.get("season")
    if requested in SEASONS:
        return requested
    return season_of(day or date.today())


@app.context_processor
def inject_season():
    return {"season": page_season()}


@app.template_global()
def static_url(filename):
    path = Path(app.static_folder) / filename
    version = int(path.stat().st_mtime) if path.exists() else 0
    return url_for("static", filename=filename, v=version)


@app.route("/")
def index():
    settings = load_settings()
    if settings is None:
        return redirect(url_for("stop"))
    stop = settings.get("stop") if settings.get("mode") == "bus" else None
    return render_template("home.html", stop=stop, categories=planner.CATEGORIES)


@app.route("/stop", methods=["GET", "POST"])
def stop():
    if request.method == "POST":
        if request.form.get("mode") == "taxi":
            save_settings({"mode": "taxi"})
        else:
            route = planner.find_route(request.form.get("route_id"))
            stop_name = request.form.get("stop")
            if route is None or stop_name not in route["district_stops"]:
                abort(400)
            save_settings({"mode": "bus", "route_id": route["id"], "stop": stop_name})
        return redirect(url_for("index"))

    route = planner.find_route(request.args.get("route", ""))
    return render_template("stop.html", routes=planner.COMMUNITY["routes"], route=route,
                           registration=planner.COMMUNITY["registration"],
                           has_settings=load_settings() is not None)


@app.route("/places")
def places():
    origin = request.args.get("origin", "home")
    category_id = request.args.get("category")
    category = next((c for c in planner.CATEGORIES if c["id"] == category_id), None)
    if category is None:
        return redirect(url_for("index"))
    items = [p for p in planner.PLACES.values() if p["category"] == category_id]
    if len(items) == 1:
        return redirect(url_for("when", origin=origin, place=items[0]["id"]))
    groups = PLACE_GROUPS.get(category_id)
    if groups:
        sections = [{"title": g["title"], "places": [planner.PLACES[i] for i in g["ids"]]} for g in groups]
    else:
        sections = [{"title": None, "places": items}]
    return render_template("places.html", origin=origin, category=category, sections=sections)


@app.route("/when")
def when():
    settings = load_settings()
    if settings is None:
        return redirect(url_for("stop"))
    place = planner.PLACES.get(request.args.get("place", ""))
    if place is None:
        return redirect(url_for("index"))
    origin = request.args.get("origin", "home")
    today = date.today()
    guide = planner.direct_guide(settings, origin, place)
    choices = planner.date_choices(settings, today, guide)
    later = planner.later_choices(settings, today, guide, choices)
    nearby = [c for c in choices if not c["next_run"]]
    selected = next((c["value"] for c in nearby if c["direct"]),
                    next((c["value"] for c in nearby if c["runs"]), nearby[0]["value"]))
    direct_day = planner.next_direct_day(settings, today, guide)
    return render_template("when.html", origin=origin, place=place,
                           choices=choices, later=later, selected=selected, guide=guide,
                           next_direct_day=planner.date_label(direct_day) if direct_day else None,
                           uses_bus=settings.get("mode") == "bus")


@app.route("/result")
def result():
    settings = load_settings()
    if settings is None:
        return redirect(url_for("stop"))
    place_id = request.args.get("place", "")
    if place_id not in planner.PLACES:
        return redirect(url_for("index"))
    origin = request.args.get("origin", "home")
    if origin != "home" and origin not in planner.CENTER_POINTS:
        origin = "home"
    period = request.args.get("period", "am")
    if period not in planner.PERIOD_START:
        period = "am"
    date_text = request.args.get("date", "")
    try:
        day = date.fromisoformat(date_text)
    except ValueError:
        return redirect(url_for("when", origin=origin, place=place_id))

    plan = planner.plan(settings, origin, place_id, day, period)
    origin_label = home_label(settings) if origin == "home" else origin
    return render_template("result.html", plan=plan, origin_label=origin_label,
                           origin=origin, place_id=place_id, season=page_season(day))


TIMES_PAGES = {
    "jr": {"title": "JR東北本線（平泉駅）", "segments": [
        "jr_hiraizumi_to_ichinoseki", "jr_ichinoseki_to_hiraizumi",
        "jr_hiraizumi_to_mizusawa", "jr_mizusawa_to_hiraizumi"]},
    "ichihira": {"title": "路線バス 一関平泉線", "segments": [
        "bus_hiraizumi_to_ichinoseki", "bus_ichinoseki_to_hiraizumi",
        "bus_hiraizumi_to_sehara", "bus_sehara_to_hiraizumi"]},
    "ichinoseki_hospital": {"title": "一関駅から病院へのバス", "segments": [
        "bus_ichinoseki_to_iwate_hospital", "bus_iwate_hospital_to_ichinoseki",
        "bus_ichinoseki_to_iwai_left", "bus_ichinoseki_to_iwai_right", "bus_iwai_to_ichinoseki",
        "bus_ichinoseki_to_iwai_shuttle", "bus_iwai_to_ichinoseki_shuttle"]},
    "mizusawa_hospital": {"title": "水沢駅から病院へのバス（水岩線）", "segments": [
        "bus_mizusawa_to_isawa", "bus_isawa_to_mizusawa",
        "bus_mizusawa_to_mizusawa_hospital", "bus_mizusawa_hospital_to_mizusawa"]},
    "geibikei": {
        "title": "路線バス 東磐交通 平泉・げいび渓線",
        "note": "2026年4月29日〜11月23日。火・水曜は運休（5月5日・6日、8月11日、9月22日・23日、11月3日は運行）。8月13日〜16日は運休。みちのくあじさい園へは水上で降車",
        "segments": [
            "toban_hiraizumi_to_michinoeki", "toban_hiraizumi_to_nanamagari",
            "toban_hiraizumi_to_minakami", "toban_hiraizumi_to_geibikei",
            "toban_geibikei_to_hiraizumi", "toban_geibikei_to_michinoeki",
            "toban_geibikei_to_nanamagari", "toban_geibikei_to_minakami"]},
    "toban_ichinoseki": {
        "title": "路線バス 東磐交通 一関線",
        "note": "平日のみ（土・日は運休）。一関駅と長島方面。公式サイトの時刻表（平成26年3月15日改正）をもとにしています",
        "segments": [
            "toban_ichi_to_nagashima", "toban_nagashima_to_ichi",
            "toban_ichi_to_suzaki", "toban_suzaki_to_ichi",
            "toban_ichi_to_tomatsuji", "toban_tomatsuji_to_ichi",
            "toban_ichi_to_akabushi", "toban_akabushi_to_ichi",
            "toban_ichi_to_sanno", "toban_sanno_to_ichi",
            "toban_ichi_to_noda", "toban_noda_to_ichi",
            "toban_ichi_to_takinosawa", "toban_takinosawa_to_ichi",
            "toban_ichi_to_nitanda", "toban_nitanda_to_ichi",
            "toban_ichi_to_tsukidate", "toban_tsukidate_to_ichi",
            "toban_ichi_to_hakoshi", "toban_hakoshi_to_ichi"]},
}


@app.route("/times/<kind>")
def times(kind):
    page = TIMES_PAGES.get(kind)
    if page is None:
        abort(404)
    tables = []
    for seg_id in page["segments"]:
        seg = planner.SEGMENTS[seg_id]
        note = "平日のみ" if seg["days"] == "weekday" else None
        if seg.get("weekday_only_first"):
            note = f"はじめの{seg['weekday_only_first']}本は土・日・祝日は運休"
        sub = seg["name"] + (f"　{seg['fare']}円" if seg.get("fare") else "")
        tables.append({"title": f"{seg['from']} → {seg['to']}", "sub": sub, "note": note,
                       "headers": [f"{seg['from']} 発", f"{seg['to']} 着"], "rows": seg["times"]})
    return render_template("times.html", title=page["title"], tables=tables, note=page.get("note"))


if __name__ == "__main__":
    app.run(debug=True, port=8000)
