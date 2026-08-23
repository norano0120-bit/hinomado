#!/usr/bin/env python3
"""気象庁の公開JSONから、日野町向けの天気と警報を data/weather.json に保存する。

日野町は滋賀県南部の予報区に入る。区域コードは変わりうるので、コードを直に
書かず「南部」を名前で探し、見つからなければ先頭の区域を使う。
警報も同じく「日野」を名前で探す。

気象庁のJSONは公式APIとして提供されているものではないため、仕様が変わる
可能性がある。取得に失敗しても他の欄が出るよう、例外は握りつぶして空で返す。
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
JST = timezone(timedelta(hours=9))
# HTTPヘッダーはASCIIしか送れないため、日本語を入れてはいけない。
# 連絡先は自分のものに書き換えること（配信元から連絡を受けられるようにする）。
UA = "hinomado/1.0 (+https://github.com/norano0120-bit/hinomado_1)"
assert UA.isascii(), "User-Agent に日本語は使えません"

PREF = "250000"          # 滋賀県
AREA_HINT = "南部"        # 日野町が属する予報区
CITY_HINT = "日野"        # 警報を見る市町村
FORECAST = f"https://www.jma.go.jp/bosai/forecast/data/forecast/{PREF}.json"
OVERVIEW = f"https://www.jma.go.jp/bosai/forecast/data/overview_forecast/{PREF}.json"
WARNING = f"https://www.jma.go.jp/bosai/warning/data/warning/{PREF}.json"

WEEKDAYS = "月火水木金土日"


def get_json(url):
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=20) as res:
        return json.loads(res.read())


def pick_area(series, hint):
    """areas から名前に hint を含むものを選ぶ。無ければ先頭。"""
    areas = series.get("areas", [])
    for a in areas:
        if hint in a.get("area", {}).get("name", ""):
            return a
    return areas[0] if areas else None


def build_days(forecast):
    """当日から3日分の天気・気温・降水確率をまとめる。"""
    near = forecast[0]
    ts_weather = near["timeSeries"][0]
    ts_pop = near["timeSeries"][1] if len(near["timeSeries"]) > 1 else None
    ts_temp = near["timeSeries"][2] if len(near["timeSeries"]) > 2 else None

    area = pick_area(ts_weather, AREA_HINT)
    if not area:
        return [], ""

    days = []
    for i, stamp in enumerate(ts_weather["timeDefines"][:3]):
        d = datetime.fromisoformat(stamp).astimezone(JST)
        days.append(
            {
                "date": d.date().isoformat(),
                "label": "きょう" if i == 0 else ("あす" if i == 1 else "あさって"),
                "md": f"{d.month}/{d.day}（{WEEKDAYS[d.weekday()]}）",
                "weather": area["weathers"][i].replace("　", " ").strip(),
                "code": area["weatherCodes"][i],
                "pops": [],
                "high": None,
                "low": None,
            }
        )

    # 降水確率は6時間ごと。日付ごとにまとめ直す
    if ts_pop:
        pop_area = pick_area(ts_pop, AREA_HINT)
        if pop_area:
            for stamp, value in zip(ts_pop["timeDefines"], pop_area.get("pops", [])):
                d = datetime.fromisoformat(stamp).astimezone(JST)
                for day in days:
                    if day["date"] == d.date().isoformat() and value != "":
                        day["pops"].append({"hour": d.hour, "value": int(value)})

    # 気温は「今日の最低・最高」「明日の最低・最高」の順に並ぶ
    if ts_temp:
        temp_area = pick_area(ts_temp, "彦根") or pick_area(ts_temp, AREA_HINT)
        if temp_area:
            for stamp, value in zip(ts_temp["timeDefines"], temp_area.get("temps", [])):
                d = datetime.fromisoformat(stamp).astimezone(JST)
                for day in days:
                    if day["date"] != d.date().isoformat() or value == "":
                        continue
                    if d.hour < 12:
                        day["low"] = int(value)
                    else:
                        day["high"] = int(value)

    return days, area["area"]["name"]


def build_warnings(warning):
    """発表中の警報・注意報だけを取り出す。解除済みは含めない。"""
    out = []
    for at in warning.get("areaTypes", []):
        for area in at.get("areas", []):
            name = area.get("area", {}).get("name", "")
            if CITY_HINT not in name:
                continue
            for w in area.get("warnings", []):
                if w.get("status") in ("解除", "発表警報・注意報はなし"):
                    continue
                kind = w.get("kindName") or w.get("code", "")
                if kind and kind not in out:
                    out.append(kind)
    return out


WEATHER_WORD = {
    "1": "晴れ", "2": "くもり", "3": "雨", "4": "雪",
}


def build_week(forecast, days):
    """週間予報（3日目以降）を days に足す。日付が重なる分は上書きしない。"""
    if len(forecast) < 2:
        return
    weekly = forecast[1]
    ts_w = weekly["timeSeries"][0]
    ts_t = weekly["timeSeries"][1] if len(weekly["timeSeries"]) > 1 else None

    area = pick_area(ts_w, AREA_HINT)
    if not area:
        return

    have = {d["date"] for d in days}
    temps = {}
    if ts_t:
        t_area = pick_area(ts_t, "彦根") or (ts_t.get("areas") or [None])[0]
        if t_area:
            for stamp, lo, hi in zip(ts_t["timeDefines"],
                                     t_area.get("tempsMin", []),
                                     t_area.get("tempsMax", [])):
                d = datetime.fromisoformat(stamp).astimezone(JST).date().isoformat()
                temps[d] = (lo, hi)

    for i, stamp in enumerate(ts_w["timeDefines"]):
        d = datetime.fromisoformat(stamp).astimezone(JST)
        iso = d.date().isoformat()
        if iso in have:
            continue
        code = (area.get("weatherCodes") or [""] * 20)[i]
        pop = (area.get("pops") or [""] * 20)[i]
        lo, hi = temps.get(iso, ("", ""))
        days.append({
            "date": iso,
            "label": f"{d.month}/{d.day}",
            "md": f"{d.month}/{d.day}（{WEEKDAYS[d.weekday()]}）",
            "weather": WEATHER_WORD.get(str(code)[:1], "くもり"),
            "code": code,
            "pops": [{"hour": 0, "value": int(pop)}] if pop not in ("", None) else [],
            "high": int(hi) if str(hi).lstrip("-").isdigit() else None,
            "low": int(lo) if str(lo).lstrip("-").isdigit() else None,
            "weekly": True,
        })
    days.sort(key=lambda x: x["date"])


def main() -> int:
    result = {
        "updated_at": datetime.now(JST).isoformat(),
        "days": [],
        "area_name": "",
        "overview": "",
        "warnings": [],
        "ok": False,
    }
    try:
        forecast = get_json(FORECAST)
        result["days"], result["area_name"] = build_days(forecast)
        build_week(forecast, result["days"])      # 3日目以降を週間予報で埋める
        result["days"] = result["days"][:7]
        result["ok"] = bool(result["days"])
    except Exception as exc:  # noqa: BLE001
        print(f"予報の取得に失敗: {exc}")

    try:
        ov = get_json(OVERVIEW)
        result["overview"] = (ov.get("text") or "").replace("\n", "").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"概況の取得に失敗: {exc}")

    try:
        result["warnings"] = build_warnings(get_json(WARNING))
    except Exception as exc:  # noqa: BLE001
        print(f"警報の取得に失敗: {exc}")

    (DATA / "weather.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    if result["warnings"]:
        print(f"発表中: {'、'.join(result['warnings'])}")
    print(f"天気 {len(result['days'])}日分を保存しました（{result['area_name']}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
