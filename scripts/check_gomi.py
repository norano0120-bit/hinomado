#!/usr/bin/env python3
"""data/gomi.json のルールから月間カレンダーを描き、公式PDFと見比べるための道具。

使い方:
    python scripts/check_gomi.py              # 今月と来月を表示
    python scripts/check_gomi.py 2026 9       # 指定した年月を表示
    python scripts/check_gomi.py --area B     # 特定の地区だけ
    python scripts/check_gomi.py --verify     # 確認できたら verified を true にする

画面に出るカレンダーと、各地区のPDFを左右に並べて見比べてください。
記号がすべて一致したら --verify を実行します。
"""

import argparse
import json
import re
import sys
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gomi_rules import kinds_on  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
JST = timezone(timedelta(hours=9))
WEEKDAYS = "月火水木金土日"

# カレンダー上の記号。品目が多いので1文字にまとめる
MARKS = {"burn": "燃", "resource": "資", "other": "不"}


def validate(gomi: dict) -> list:
    """ルールの書き方の誤りを拾う。"""
    problems = []
    chips = {k["chip"] for k in gomi.get("kinds", [])} or {"burn", "resource", "other"}
    for area in gomi["areas"]:
        for i, rule in enumerate(area["rules"]):
            where = f"{area['id']}地区の{i + 1}番目（{rule.get('label', '無名')}）"
            if rule.get("kind") not in chips:
                problems.append(f"{where}: kind が {sorted(chips)} のどれでもありません")
            if rule.get("type") == "weekly":
                days = rule.get("weekdays") or []
                if not days or any(not 0 <= x <= 6 for x in days):
                    problems.append(f"{where}: weekdays は 0〜6 の配列にしてください")
            elif rule.get("type") == "monthly":
                if not 0 <= rule.get("weekday", -1) <= 6:
                    problems.append(f"{where}: weekday は 0〜6 にしてください")
                nth = rule.get("nth") or []
                if not nth or any(not 1 <= x <= 5 for x in nth):
                    problems.append(f"{where}: nth は 1〜5 の配列にしてください")
            elif rule.get("type") == "dates":
                bad = [d for d in rule.get("dates", [])
                       if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d))]
                if not rule.get("dates"):
                    problems.append(f"{where}: dates が空です")
                if bad:
                    problems.append(f"{where}: 日付の書き方が違います → {bad[:3]}")
            else:
                problems.append(f"{where}: type は weekly / monthly / dates のいずれかです")
    return problems


def draw_month(area: dict, gomi: dict, year: int, month: int) -> str:
    """1か月分のカレンダーを文字で描く。"""
    first_weekday, days_in_month = monthrange(year, month)
    lines = [
        f"  {area['id']}地区：{area['name']}",
        f"  {year}年{month}月",
        "  " + "".join(w + "    " for w in WEEKDAYS),
    ]
    cells = ["      "] * first_weekday
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        marks = ""
        for k in kinds_on(area, d, gomi):
            m = MARKS.get(k["kind"], "○")
            if m not in marks:
                marks += m
        pad = marks[:2] + "　" * (2 - len(marks[:2]))
        cells.append(f"{day:2d}{pad}")

    for i in range(0, len(cells), 7):
        lines.append("  " + "".join(cells[i:i + 7]))

    lines.append("")
    for rule in area["rules"]:
        if rule["type"] == "dates":
            ds = rule.get("dates", [])
            same_month = [d for d in ds if d.startswith(f"{year:04d}-{month:02d}")]
            lines.append(f"    {MARKS.get(rule['kind'],'○')} {rule['label']}　… "
                         f"日付指定（今月 {len(same_month)}日 / 登録 {len(ds)}日）")
            continue
        if rule["type"] == "weekly":
            when = "毎週" + "・".join(WEEKDAYS[w] for w in rule["weekdays"]) + "曜"
        else:
            when = "第" + "・".join(str(n) for n in rule["nth"]) + WEEKDAYS[rule["weekday"]] + "曜"
        lines.append(f"    {MARKS.get(rule['kind'], '○')} {rule['label']}　… {when}")
    lines.append(f"    PDF: {area['pdf']}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="ごみ収集ルールを目で確かめる")
    ap.add_argument("year", nargs="?", type=int)
    ap.add_argument("month", nargs="?", type=int)
    ap.add_argument("--area", help="地区ID（A / B / C / D）")
    ap.add_argument("--verify", action="store_true", help="確認できたので verified を true にする")
    args = ap.parse_args()

    path = DATA / "gomi.json"
    gomi = json.loads(path.read_text(encoding="utf-8"))

    problems = validate(gomi)
    if problems:
        print("■ ルールの書き方に問題があります\n")
        for p in problems:
            print(f"  × {p}")
        print("\n直してから、もう一度実行してください。")
        return 1

    if args.verify:
        gomi["verified"] = True
        gomi.pop("warning", None)
        path.write_text(json.dumps(gomi, ensure_ascii=False, indent=2), encoding="utf-8")
        print("verified を true にしました。build_site.py を実行すると注意書きが消えます。")
        return 0

    today = datetime.now(JST).date()
    if args.year and args.month:
        months = [(args.year, args.month)]
    else:
        nxt = date(today.year, today.month, 28) + timedelta(days=7)
        months = [(today.year, today.month), (nxt.year, nxt.month)]

    areas = gomi["areas"]
    if args.area:
        areas = [a for a in areas if a["id"].upper() == args.area.upper()]
        if not areas:
            print(f"地区 {args.area} が見つかりません")
            return 1

    print("=" * 58)
    print("  ごみ収集ルールの確認　燃=燃えるごみ 資=資源 不=不燃・古紙")
    print("=" * 58)
    for area in areas:
        for year, month in months:
            print()
            print(draw_month(area, gomi, year, month))
        print("\n" + "-" * 58)

    if gomi.get("verified"):
        print("\n状態：確認済み（サイトに注意書きは出ません）")
    else:
        print("\n状態：未確認。PDFと見比べて一致したら次を実行してください：")
        print("    python scripts/check_gomi.py --verify")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
