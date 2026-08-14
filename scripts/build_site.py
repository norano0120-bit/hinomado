#!/usr/bin/env python3
"""data/ の JSON から public/ に静的サイトを書き出す。

出力:
  public/index.html   サイト本体
  public/feed.xml     まとめたお知らせのRSS
  public/events.ics   日付つきイベントのカレンダー（Googleカレンダー等に登録できる）
  public/news.json    正規化済みデータ（そのまま再利用できるように公開する）
"""

import json
import re
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gomi_rules import kinds_on  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PUBLIC = ROOT / "public"
JST = timezone(timedelta(hours=9))

SITE_NAME = "ひのまど"
SITE_TAGLINE = "滋賀県蒲生郡日野町の今日を、ひとつの窓から"
# 公開先URLと解析の設定は data/site.json に置く

CAT_LABELS = {
    "town": "町から",
    "alert": "防災・注意",
    "event": "イベント",
    "life": "暮らし・移住",
    "business": "事業者",
    "press": "報道",
}

# お知らせ欄に出す分類（報道とふるさと納税は別の欄で扱う）
NOTICE_CATS = ["town", "event", "alert", "life", "business"]
COLLAPSE_AT = 7   # お知らせを最初に見せる件数

SPOT_CATS = [
    ("cafe", "カフェ・喫茶"),
    ("food", "食べる"),
    ("sight", "観る"),
    ("nature", "自然・花"),
    ("play", "遊ぶ"),
    ("festival", "祭り"),
]

DATE_IN_TITLE = re.compile(r"[【\[]\s*(\d{1,2})月(\d{1,2})日")
WEEKDAYS = "月火水木金土日"


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def event_date(title: str, today: date):
    """タイトル先頭の【8月26日】から日付を取り出す。無ければ None。"""
    m = DATE_IN_TITLE.search(title)
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    for year in (today.year, today.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if candidate >= today - timedelta(days=1):
            return candidate
    return None


def jp_date(d: date) -> str:
    return f"{d.month}月{d.day}日（{WEEKDAYS[d.weekday()]}）"


def analytics_tag(cfg: dict) -> str:
    """アクセス解析のタグを組み立てる。設定が無ければ空文字を返す。

    どちらもCookieを使わず、個人を特定する情報を集めない方式を選んでいる。
    そのため同意バナーを出さずに設置できる。
    """
    provider = (cfg.get("provider") or "").strip().lower()
    token = (cfg.get("token") or "").strip()
    if not provider or provider == "none" or not token:
        return ""

    if provider == "cloudflare":
        return (
            '<!-- Cloudflare Web Analytics（Cookieなし） -->\n'
            '<script defer src="https://static.cloudflareinsights.com/beacon.min.js" '
            f'data-cf-beacon=\'{{"token": "{token}"}}\'></script>'
        )
    if provider == "goatcounter":
        return (
            '<!-- GoatCounter（Cookieなし） -->\n'
            f'<script data-goatcounter="https://{token}.goatcounter.com/count" '
            'async src="//gc.zgo.at/count.js"></script>'
        )
    print(f"  ※ 解析の provider が不明です: {provider}")
    return ""


def weather_icon(text: str) -> str:
    """予報文からアイコンを選ぶ。気象庁のアイコンはライセンス表示がないため自作を使う。"""
    t = text.replace(" ", "").replace("　", "")
    sunny = t.startswith("晴")
    if "雷" in t:
        return "thunder"
    if "雪" in t:
        return "snow"
    if "雨" in t:
        return "sun-rain" if sunny else "rain"
    if sunny and ("くもり" in t or "曇" in t):
        return "sun-cloud"
    if sunny:
        return "sun"
    return "cloud"


def split_weather(text: str):
    """「晴れ 昼過ぎから 夕方 雷雨」を主部と補足に分ける。折り返さないよう短く保つ。"""
    parts = [p for p in text.replace("　", " ").split(" ") if p]
    if not parts:
        return "", ""
    return parts[0], "".join(parts[1:])


def gomi_days(area: dict, gomi: dict, start: date, span: int = 21) -> list:
    """今日から span 日分の収集予定を、日付順に返す。"""
    out = []
    for offset in range(span):
        d = start + timedelta(days=offset)
        kinds = kinds_on(area, d, gomi)
        if kinds:
            out.append({
                "date": d,
                "md": f"{d.month}/{d.day}",
                "wd": WEEKDAYS[d.weekday()],
                "in_days": offset,
                "when": "きょう" if offset == 0 else ("あす" if offset == 1 else f"{offset}日後"),
                "kinds": kinds,
            })
    return out


def build():
    now = datetime.now(JST)
    today = now.date()

    news = load("news.json")
    spots = load("spots.json")
    sources = load("sources.json")
    furusato = load("furusato.json")
    site = load("site.json")
    gomi = load("gomi.json")
    kurashi = load("kurashi.json")
    kosodate = load("kosodate.json")
    try:
        weather = load("weather.json")
    except FileNotFoundError:
        weather = {"ok": False, "days": [], "warnings": [], "overview": ""}
    try:
        gikai = load("gikai.json")
    except FileNotFoundError:
        gikai = {"minutes": [], "schedule": [], "documents": []}

    items = news["items"]
    for item in items:
        d = datetime.fromisoformat(item["date"]).date()
        item["date_obj"] = d
        item["date_label"] = f"{d.month}/{d.day}"
        item["is_new"] = (today - d).days <= 3
        item["cat_label"] = CAT_LABELS.get(item["category"], item["category"])

    # 報道とふるさと納税は専用の欄に振り分ける
    press_items = [i for i in items if i["category"] == "press"][:20]
    fk = furusato["keywords"]
    furusato_items = [
        i for i in items
        if any(w in i["title"] + i["summary"] for w in fk)
    ][:6]
    notice_items = [i for i in items if i["category"] in NOTICE_CATS]
    kosodate_items = [i for i in items if "kosodate" in i["tags"]][:10]

    # 日付つきイベントを拾って、これから来る順に並べる
    upcoming = []
    for item in items:
        d = event_date(item["title"], today)
        if d:
            upcoming.append({**item, "event_date": d})
    upcoming.sort(key=lambda x: x["event_date"])
    seen, dedup = set(), []
    for e in upcoming:
        if e["url"] in seen:
            continue
        seen.add(e["url"])
        dedup.append(e)
    upcoming = dedup[:8]

    # 今月が見ごろ・開催時期にあたるスポット（花や山、祭りだけを対象にする）
    SEASONAL_CATS = {"nature", "festival"}
    in_season = [
        s for s in spots
        if s["cat"] in SEASONAL_CATS and now.month in s.get("season", [])
    ]
    for s in spots:
        s["in_season"] = s in in_season
        s["season_label"] = "今月開催" if s["cat"] == "festival" else "いま見ごろ"

    for day in weather.get("days", []):
        day["icon"] = weather_icon(day["weather"])
        day["main"], day["rest"] = split_weather(day["weather"])

    for area in gomi["areas"]:
        area["short"] = area["name"].split("・")[0]
        area["upcoming"] = gomi_days(area, gomi, today)
        area["next"] = area["upcoming"][0] if area["upcoming"] else None

    spot_groups = [
        {"key": key, "label": label, "spots": [s for s in spots if s["cat"] == key]}
        for key, label in SPOT_CATS
    ]

    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html", "j2"]),
    )

    # スタイルは1ファイルに埋め込む。読み込みが1回で済み、キャッシュのずれも起きない。
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")

    analytics = analytics_tag(site.get("analytics", {}))
    shared = dict(
        css=css,
        analytics=analytics,
        privacy_note=site.get("privacy_note", "") if analytics else "",
        site_name=SITE_NAME,
        tagline=SITE_TAGLINE,
        home="index.html",
        now=now,
        today_label=jp_date(today),
        total_items=len(items),
        sources=sources,
        weather=weather,
        furusato=furusato,
        furusato_items=furusato_items,
        gikai=gikai,
        gikai_summarized=[m for m in gikai.get("minutes", []) if m.get("summary")][:4],
        kosodate=kosodate,
        kosodate_items=kosodate_items,
    )

    PUBLIC.mkdir(exist_ok=True)

    pages = [
        ("index.html", "index.html.j2", dict(
            page="index",
            compact=False,
            items=notice_items[:60],
            press_items=press_items,
            gomi=gomi,
            kurashi=kurashi,
            collapse_at=COLLAPSE_AT,
            upcoming=upcoming,
            in_season=in_season,
            month=now.month,
            spot_groups=spot_groups,
            errors=news.get("errors", []),
            cat_labels={k: v for k, v in CAT_LABELS.items() if k in NOTICE_CATS},
        )),
        ("kosodate.html", "kosodate.html.j2", dict(page="kosodate", compact=True)),
        ("furusato.html", "furusato.html.j2", dict(page="furusato", compact=True)),
        ("gikai.html", "gikai.html.j2", dict(page="gikai", compact=True)),
    ]
    for filename, template, extra in pages:
        html = env.get_template(template).render(**shared, **extra)
        (PUBLIC / filename).write_text(html, encoding="utf-8")

    shutil.copy(DATA / "news.json", PUBLIC / "news.json")
    write_feed(items[:50], now, site["site_url"])
    write_ics(upcoming, now)
    print(f"公開ファイルを書き出しました: {PUBLIC}")


def write_feed(items, now, site_url):
    entries = []
    for item in items:
        pub = datetime.fromisoformat(item["date"]).strftime("%a, %d %b %Y %H:%M:%S +0900")
        entries.append(
            "<item>"
            f"<title>[{escape(item['source_short'])}] {escape(item['title'])}</title>"
            f"<link>{escape(item['url'])}</link>"
            f"<guid isPermaLink=\"true\">{escape(item['url'])}</guid>"
            f"<pubDate>{pub}</pubDate>"
            f"<description>{escape(item['summary'])}</description>"
            "</item>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        f"<title>{SITE_NAME} - 日野町のお知らせまとめ</title>"
        f"<link>{escape(site_url)}</link>"
        f"<description>{escape(SITE_TAGLINE)}</description>"
        f"<lastBuildDate>{now.strftime('%a, %d %b %Y %H:%M:%S +0900')}</lastBuildDate>"
        + "".join(entries)
        + "</channel></rss>"
    )
    (PUBLIC / "feed.xml").write_text(xml, encoding="utf-8")


def write_ics(events, now):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{SITE_NAME}//JP",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:日野町のイベント（{SITE_NAME}）",
    ]
    for i, e in enumerate(events):
        d = e["event_date"]
        title = re.sub(r"^[【\[][^】\]]*[】\]]\s*", "", e["title"])
        lines += [
            "BEGIN:VEVENT",
            f"UID:hinomado-{d:%Y%m%d}-{i}@example.com",
            f"DTSTAMP:{now.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}",
            f"DTSTART;VALUE=DATE:{d:%Y%m%d}",
            f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{title}",
            f"DESCRIPTION:出典 {e['source_name']}",
            f"URL:{e['url']}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    (PUBLIC / "events.ics").write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")


if __name__ == "__main__":
    build()
