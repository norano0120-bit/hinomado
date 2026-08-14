#!/usr/bin/env python3
"""日野町議会の会議録・議会だより・本会議の予定を集めて data/gikai.json に保存する。

ANTHROPIC_API_KEY を環境変数に入れておくと、まだ要約していない会議録の PDF を
読んで論点と一般質問の要旨をまとめる。キーが無ければ一覧とリンクだけを作る。

会議録は公開まで数か月かかる（例：令和7年12月定例会議の会議録が公開されたのは
2026年4月）。「今の議論」ではなく「記録の入口」として扱うこと。
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
JST = timezone(timedelta(hours=9))
UA = "hinomado/1.0 (+https://example.com/about; 日野町の情報をまとめる個人サイト)"

INDEX_MINUTES = "https://www.town.shiga-hino.lg.jp/category/32-3-6-0-0-0-0-0-0-0.html"
INDEX_SCHEDULE = "https://www.town.shiga-hino.lg.jp/category/32-3-5-18-0-0-0-0-0-0.html"
PAGE_DAYORI = "https://www.town.shiga-hino.lg.jp/0000007081.html"
PAGE_SHITSUMON = "https://www.town.shiga-hino.lg.jp/0000007323.html"
STREAM = "https://hino-town.stream.jfit.co.jp/"

PAGE_RE = r"town\.shiga-hino\.lg\.jp/\d{10}\.html$"
PDF_RE = r"\.pdf$"

MAX_NEW_SUMMARIES = 2      # 1回の実行で新しく要約する会議録の数
MAX_CHARS = 120_000        # APIに渡す本文の上限


class Links(HTMLParser):
    def __init__(self, pattern, base):
        super().__init__()
        self.re = re.compile(pattern, re.I)
        self.base = base
        self.out = []
        self._href = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href", "")
        full = urljoin(self.base, href)
        if self.re.search(full):
            self._href, self._buf = full, []

    def handle_data(self, data):
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if text:
                self.out.append((self._href, text))
            self._href = None


def get(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=30) as res:
        return res.read()


def links_on(url: str, pattern: str):
    raw = get(url)
    try:
        html = raw.decode("utf-8")
    except UnicodeDecodeError:
        html = raw.decode("shift_jis", errors="replace")
    p = Links(pattern, url)
    p.feed(html)
    seen, out = set(), []
    for href, text in p.out:
        if href in seen:
            continue
        seen.add(href)
        out.append({"url": href, "title": text})
    return out


def pdf_text(url: str) -> str:
    from pypdf import PdfReader
    from io import BytesIO

    reader = PdfReader(BytesIO(get(url)))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


PROMPT = """あなたは地方議会の会議録を、その町に住む人が読める形に整理する編集者です。

以下は滋賀県蒲生郡日野町議会の会議録です。これを読んで、JSONだけを出力してください。
前置き、説明、コードブロックの記号は一切書かないでください。

{{
  "overview": "この会議で何が決まり何が議論されたかを2〜3文で。専門用語は言い換える。",
  "topics": [
    {{"title": "論点の名前（15字以内）", "detail": "何が問題で、どういう方向になったかを2文以内で"}}
  ],
  "questions": [
    {{"member": "質問した議員名", "theme": "質問のテーマ（20字以内）", "gist": "質問の趣旨と町側の答えを2文以内で"}}
  ],
  "decisions": ["可決・否決・承認された議案を短く。金額や対象がわかるように。"]
}}

守ること:
- topics は多くても6件、questions は多くても8件。重要なものだけ選ぶ。
- 会議録の文章をそのまま写さず、必ず自分の言葉で言い換える。
- 会議録に書かれていないことは推測して足さない。わからない項目は空の配列にする。
- 賛否が分かれた論点は、どちらの立場も同じ扱いで書く。どちらかに肩入れしない。

会議録:
---
{body}
---"""


def summarize(body: str, api_key: str) -> dict:
    import urllib.error

    payload = {
        "model": "claude-sonnet-4-6",
        "max_tokens": 3000,
        "messages": [{"role": "user", "content": PROMPT.format(body=body[:MAX_CHARS])}],
    }
    req = Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urlopen(req, timeout=180) as res:
        data = json.loads(res.read())
    text = "".join(b.get("text", "") for b in data.get("content", []))
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text)


def main() -> int:
    store_path = DATA / "gikai.json"
    store = {"minutes": [], "schedule": [], "documents": []}
    if store_path.exists():
        store = json.loads(store_path.read_text(encoding="utf-8"))
    known = {m["url"]: m for m in store.get("minutes", [])}

    # 会議録の一覧
    try:
        for row in links_on(INDEX_MINUTES, PAGE_RE):
            if "会議録" not in row["title"]:
                continue
            known.setdefault(row["url"], {**row, "summary": None, "pdfs": []})
        print(f"会議録 {len(known)}件を把握")
    except Exception as exc:  # noqa: BLE001
        print(f"会議録一覧の取得に失敗: {exc}", file=sys.stderr)

    # 本会議の予定
    schedule = []
    try:
        schedule = links_on(INDEX_SCHEDULE, PAGE_RE)[:8]
    except Exception as exc:  # noqa: BLE001
        print(f"本会議予定の取得に失敗: {exc}", file=sys.stderr)

    documents = [
        {"title": "議会だより", "url": PAGE_DAYORI,
         "note": "定例会ごとの紙面。会議録より早く要点がまとまる。"},
        {"title": "一般質問に係る配付資料", "url": PAGE_SHITSUMON,
         "note": "議員が質問時に使った資料。数字の出どころを確かめられる。"},
        {"title": "議会のインターネット配信", "url": STREAM,
         "note": "本会議のライブ中継と録画。会議録より先に中身がわかる。"},
    ]

    # 新しい会議録を要約する（APIキーがあるときだけ）
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    todo = [m for m in known.values() if not m.get("summary")]
    todo.sort(key=lambda m: m["url"], reverse=True)  # 新しい記事番号から

    if not api_key:
        print(f"ANTHROPIC_API_KEY が無いので要約は飛ばします（未要約 {len(todo)}件）")
    else:
        for entry in todo[:MAX_NEW_SUMMARIES]:
            try:
                pdfs = links_on(entry["url"], PDF_RE)
                if not pdfs:
                    print(f"  - PDFが見つかりません: {entry['title']}")
                    continue
                entry["pdfs"] = pdfs
                body = "\n\n".join(pdf_text(p["url"]) for p in pdfs[:4])
                if len(body) < 500:
                    print(f"  - 本文を取り出せません（画像PDFの可能性）: {entry['title']}")
                    continue
                entry["summary"] = summarize(body, api_key)
                entry["generated_at"] = datetime.now(JST).isoformat()
                print(f"  ○ 要約しました: {entry['title']}")
                time.sleep(2)
            except Exception as exc:  # noqa: BLE001
                print(f"  × 要約に失敗: {entry['title']} / {exc}", file=sys.stderr)

    minutes = sorted(known.values(), key=lambda m: m["url"], reverse=True)
    store_path.write_text(
        json.dumps(
            {
                "updated_at": datetime.now(JST).isoformat(),
                "minutes": minutes,
                "schedule": schedule,
                "documents": documents,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    summarized = sum(1 for m in minutes if m.get("summary"))
    print(f"会議録 {len(minutes)}件（うち要約済み {summarized}件）を保存しました")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
