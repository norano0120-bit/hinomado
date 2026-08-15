#!/usr/bin/env python3
"""日野町関連のRSSを取得して data/news.json に正規化して保存する。

- 取得元は data/sources.json で定義する
- 1件でも取れたソースがあれば成功扱いにし、失敗したソースは errors に記録する
- 既存の news.json とマージするので、配信元が古い記事を落としても履歴は残る
"""

import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import feedparser

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
JST = timezone(timedelta(hours=9))

# HTTPヘッダーはASCIIしか送れないため、日本語を入れてはいけない。
# 連絡先は自分のものに書き換えること（配信元から連絡を受けられるようにする）。
UA = "hinomado/1.0 (+https://github.com/norano0120-bit/hinomado_1)"
assert UA.isascii(), "User-Agent に日本語は使えません"
KEEP_DAYS = 400          # これより古い記事は news.json から落とす
REQUEST_INTERVAL = 2.0   # 取得元に負荷をかけないための待ち時間（秒）

TAG_RULES = [
    ("alert", ["警報", "注意報", "避難", "地震", "災害", "不審", "詐欺", "停電", "断水", "食中毒"]),
    ("event", ["イベント", "まつり", "祭", "フェス", "教室", "講座", "コンサート", "上映", "展", "体験"]),
    ("kosodate", ["子育て", "保育", "こども", "子ども", "児童", "妊婦", "予防接種", "学校", "入園"]),
    ("senior", ["高齢", "介護", "年金", "健診", "検診", "認知症", "シニア"]),
    ("business", ["事業者", "入札", "補助金", "支援金", "融資", "商工", "求人", "採用"]),
    ("kurashi", ["ごみ", "水道", "下水", "税", "納付", "住民票", "マイナンバー", "住宅", "証明"]),
]


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def guess_tags(title: str, summary: str) -> list:
    blob = f"{title} {summary}"
    tags = [tag for tag, words in TAG_RULES if any(w in blob for w in words)]
    return tags


def to_iso(entry) -> str:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc).astimezone(JST).isoformat()
    return datetime.now(JST).isoformat()


def keep_item(source: dict, title: str, summary: str) -> bool:
    """include が指定されていれば1語以上を含むもの、exclude に触れるものは落とす。

    「日野町」は東京都日野市・鳥取県日野町とも紛れるので、報道系は必ずここで絞る。
    """
    blob = f"{title} {summary}"
    include = source.get("include")
    if include and not any(w in blob for w in include):
        return False
    if any(w in blob for w in source.get("exclude", [])):
        return False
    return True


class LinkCollector(HTMLParser):
    """<a href> のうち、パターンに合うものだけ (url, テキスト) で集める。"""

    def __init__(self, pattern: str, base: str):
        super().__init__()
        self.pattern = re.compile(pattern)
        self.base = base
        self.links = []
        self._href = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href", "")
        full = urljoin(self.base, href)
        if self.pattern.search(full):
            self._href, self._buf = full, []

    def handle_data(self, data):
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if text:
                self.links.append((self._href, text))
            self._href = None


def fetch_html_source(source: dict) -> list:
    """RSSがない配信元向け。一覧ページのリンクを見出しとして拾う。"""
    req = Request(source["url"], headers={"User-Agent": UA})
    with urlopen(req, timeout=20) as res:
        raw = res.read()
    charset = res.headers.get_content_charset() or "utf-8"
    try:
        html = raw.decode(charset, errors="replace")
    except LookupError:
        html = raw.decode("utf-8", errors="replace")

    parser = LinkCollector(source["link_pattern"], source["url"])
    parser.feed(html)

    now = datetime.now(JST).isoformat()
    items, seen = [], set()
    for url, title in parser.links:
        if url in seen or len(title) < 4:
            continue
        if not keep_item(source, title, ""):
            continue
        seen.add(url)
        items.append(
            {
                "id": url,
                "title": title,
                "url": url,
                "summary": "",
                "date": now,  # 初回取得日を掲載日の代わりに使う
                "source_id": source["id"],
                "source_name": source["name"],
                "source_short": source["short"],
                "category": source["category"],
                "tags": guess_tags(title, ""),
            }
        )
    return items


def fetch_source(source: dict) -> list:
    if source.get("type") == "html":
        return fetch_html_source(source)

    feed = feedparser.parse(source["url"], agent=UA)
    if feed.bozo and not feed.entries:
        raise RuntimeError(f"解析に失敗しました: {feed.bozo_exception}")

    items = []
    for entry in feed.entries:
        link = entry.get("link", "").strip()
        title = strip_html(entry.get("title", ""))
        if not link or not title:
            continue
        summary = strip_html(entry.get("summary", ""))[:160]
        if not keep_item(source, title, summary):
            continue
        items.append(
            {
                "id": link,
                "title": title,
                "url": link,
                "summary": summary,
                "date": to_iso(entry),
                "source_id": source["id"],
                "source_name": source["name"],
                "source_short": source["short"],
                "category": source["category"],
                "tags": guess_tags(title, summary),
            }
        )
    return items


def main() -> int:
    sources = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))

    existing = {}
    news_path = DATA / "news.json"
    if news_path.exists():
        old = json.loads(news_path.read_text(encoding="utf-8"))
        existing = {item["id"]: item for item in old.get("items", [])}

    fetched, errors = 0, []
    for i, source in enumerate(sources):
        if i:
            time.sleep(REQUEST_INTERVAL)
        try:
            items = fetch_source(source)
        except Exception as exc:  # noqa: BLE001 - 1つ失敗しても全体は続ける
            errors.append({"source": source["name"], "message": str(exc)})
            print(f"  × {source['name']}: {exc}", file=sys.stderr)
            continue
        for item in items:
            # 初出日を保つため、既知のIDは日付を上書きしない
            if item["id"] in existing:
                item["date"] = existing[item["id"]]["date"]
            existing[item["id"]] = item
        fetched += len(items)
        print(f"  ○ {source['name']}: {len(items)}件")

    cutoff = datetime.now(JST) - timedelta(days=KEEP_DAYS)
    items = [
        item for item in existing.values()
        if datetime.fromisoformat(item["date"]) >= cutoff
    ]
    items.sort(key=lambda x: x["date"], reverse=True)

    payload = {
        "updated_at": datetime.now(JST).isoformat(),
        "errors": errors,
        "items": items,
    }
    news_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"取得 {fetched}件 / 保存 {len(items)}件 / 失敗 {len(errors)}件")

    # 取得に失敗してもサイトは前回の内容で公開する。
    # 止めてしまうと、1つの不具合で全ページが出なくなるため。
    # 失敗はページ上部に表示され、ここでも目立つように警告を出す。
    if errors and len(errors) == len(sources):
        print("::warning::すべての配信元から取得できませんでした。"
              "前回のデータでサイトを作ります。ネットワークか取得元の仕様変更を確認してください。")
    elif errors:
        print(f"::warning::{len(errors)}件の配信元から取得できませんでした。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
