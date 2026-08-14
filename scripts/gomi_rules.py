"""ごみ収集日の判定。build_site.py と check_gomi.py の両方から使う。"""

from datetime import date


def nth_weekday_of_month(d: date) -> int:
    """その日が「第何週の○曜日」かを返す（1始まり）。"""
    return (d.day - 1) // 7 + 1


def kinds_on(area: dict, d: date, gomi: dict) -> list:
    """その日に出せるごみの種類を返す。無ければ空リスト。

    skip に書いた日は収集なし、add に書いた日は臨時の収集として扱う。
    地区ごとの指定が全体の指定より優先される。
    """
    iso = d.isoformat()

    for entry in list(area.get("add", [])) + list(gomi.get("add", [])):
        if entry.get("date") == iso:
            return [
                {"label": lb, "kind": entry.get("kind", "other")}
                for lb in entry.get("labels", [])
            ]

    if iso in area.get("skip", []) or iso in gomi.get("skip", []):
        return []

    out = []
    for rule in area["rules"]:
        if rule["type"] == "dates":
            # カレンダーから読み取った日付をそのまま並べる方式。
            # 祝日のずれや不規則な間隔をそのまま表現できるので一番確実。
            hit = iso in rule["dates"]
        elif rule["type"] == "weekly":
            hit = d.weekday() in rule["weekdays"]
        else:
            hit = (
                d.weekday() == rule["weekday"]
                and nth_weekday_of_month(d) in rule["nth"]
            )
        if hit:
            out.append({"label": rule["label"], "kind": rule["kind"]})
    return out
