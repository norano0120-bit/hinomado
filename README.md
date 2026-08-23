# ひのまど

滋賀県蒲生郡日野町のお知らせ・イベント・お出かけ情報を毎日集めて、1ページにまとめる静的サイトです。

サーバーは要りません。GitHub Actions が毎朝6時（日本時間）に各配信元の RSS を取りに行き、HTML を組み立てて GitHub Pages に公開します。運用費はゼロです。

## 構成

```
scripts/fetch_news.py   配信元から取得して data/news.json に正規化
scripts/fetch_weather.py 気象庁から天気と警報を取って data/weather.json に
scripts/check_gomi.py   ごみ収集ルールをカレンダーに描いてPDFと照合する
scripts/fetch_gikai.py  議会の会議録を集め、任意でAI要約して data/gikai.json に
scripts/check_gomi.py   ごみ収集日をPDFと照合するための確認ツール
scripts/gomi_rules.py   収集日の判定（build と check の共通部分）
scripts/build_site.py   data/ から public/ を生成
data/sources.json       取得元の定義（ここを増やせばソースが増える）
data/spots.json         お出かけスポット（手で書く。ここが独自の価値になる）
data/furusato.json      ふるさと納税の入口リンクと拾うキーワード
data/gikai.json         会議録の一覧と要約（fetch_gikai.py が書く）
data/gomi.json          ごみ収集日のルール（手で書く。要確認）
data/kurashi.json       暮らしの連絡先
data/kosodate.json      子育てページの内容
data/site.json          公開先URL、アクセス解析、問い合わせ先の設定
data/hojokin.json       事業者向け補助金の内容
posts/                  記事（.md）。ここに置くと自動でページになる
data/kosodate.json      子育て情報（手で書く）
data/weather.json       天気（fetch_weather.py が書く）
data/news.sample.json   動作確認用のサンプル
templates/base.html.j2  全ページ共通の骨組み（ヘッダー・目次・フッター・アイコン）
templates/index.html.j2 トップ（お知らせ→時事ニュース→きょうの暮らし→お出かけ）
templates/kosodate.html.j2  子育てページ
templates/furusato.html.j2  ふるさと納税ページ
templates/gikai.html.j2     議会ページ
static/style.css        スタイル（ビルド時にHTMLへ埋め込まれる）
public/                 生成物。GitHub Pages が公開する
```

出力は index.html のほか、まとめた RSS（`feed.xml`）、日付つきイベントのカレンダー（`events.ics`）、正規化済みデータ（`news.json`）です。

## 手元で動かす

```bash
pip install -r requirements.txt
python scripts/fetch_news.py     # ネットに出て取得する
python scripts/fetch_weather.py  # 気象庁から天気と警報を取る
python scripts/fetch_gikai.py    # 議会の会議録を集める（要約は下記参照）
python scripts/build_site.py     # public/ を作る
python -m http.server -d public  # http://localhost:8000 で確認
```

ネットにつながない状態で見た目だけ確認したいときは、取得を飛ばしてサンプルを使ってください。

```bash
cp data/news.sample.json data/news.json && python scripts/build_site.py
```

## 公開する

### 1. リポジトリを作る

GitHubにログインし、右上の「+」→「New repository」。

- Repository name … `hinomado`
- **Public** を選ぶ（Privateだと無料でPages公開できません）
- READMEやgitignoreの追加にはチェックを入れない

「Create repository」を押します。

### 2. ファイルを上げる

**GitHub Desktopを使う方法（おすすめ）**

コマンドを打たずに済みます。

1. https://desktop.github.com/ からインストールしてGitHubにサインイン
2. File → Clone repository → いま作った `hinomado` を選ぶ
3. 空のフォルダができるので、ZIPを展開した中身を**すべて**そこにコピーする（`.github` フォルダを忘れずに。隠しフォルダなのでエクスプローラーの「表示」→「隠しファイル」をオンに）
4. GitHub Desktopに変更が並ぶので、左下に「最初の公開」などと書いて「Commit to main」
5. 「Push origin」を押す

**コマンドで行う方法**

```bash
cd C:\Users\idya0\Downloads\hinomado
git init
git add .
git commit -m "ひのまど 公開"
git branch -M main
git remote add origin https://github.com/ユーザー名/hinomado.git
git push -u origin main
```

### 3. Pagesを有効にする

リポジトリの **Settings → Pages** を開き、Source を **GitHub Actions** に変更します。

### 4. 書き込み権限を許可する

取得したデータをリポジトリに保存するために必要です。ここを忘れると毎回失敗します。

**Settings → Actions → General** の一番下、**Workflow permissions** で
**Read and write permissions** を選んで Save。

### 5. 議会の要約を使う場合（任意）

**Settings → Secrets and variables → Actions → New repository secret**

- Name … `ANTHROPIC_API_KEY`
- Secret … APIキー

設定しなくてもサイトは動きます。その場合は会議録の一覧とリンクだけになります。

### 6. 動かす

**Actions** タブ →「毎日更新して公開する」→ 右の **Run workflow**。

3〜5分で緑のチェックが付き、`https://ユーザー名.github.io/hinomado/` で見られるようになります。以降は毎朝6時と夕方6時に自動で動きます。

### 7. 公開先URLを書き込む

`data/site.json` の `site_url` を実際のURLに書き換えて、もう一度push。RSSとカレンダーのリンクが正しくなります。

### つまずきやすいところ

- **Actionsが赤くなる** … 手順4の書き込み権限がいちばん多い原因です。ログの最後に `permission denied` と出ていたらこれ
- **404が出る** … Pagesの反映に数分かかります。Actionsが緑になってから待ってみてください
- **`.github` が上がっていない** … 隠しフォルダなのでコピー漏れしやすいです。リポジトリのファイル一覧に `.github` があるか確認を
- **CSSが効かない** … スタイルはHTMLに埋め込んであるので、この症状は基本的に出ません

## 公開先URLを変える

リポジトリ名を変えるとURLも変わります。`hinomado_1` を `hinomado` にしたい場合はこうします。

1. GitHubでリポジトリの **Settings** → 一番上の **Repository name** を書き換えて **Rename**
2. `data/site.json` の `site_url` を新しいURLに直す
3. `scripts/fetch_news.py` などの `UA` に入れているURLも直す（任意）
4. GitHub Desktop で Commit → Push

新しいURLは `https://ユーザー名.github.io/新しい名前/` です。

**注意点**

- 古いURLはしばらく新しいURLへ転送されますが、いずれ切れます。人に知らせたあとで変えると混乱するので、**変えるなら早いうちに**
- GitHub Desktop 側のフォルダ名は自動では変わりません。気になる場合は一度リポジトリを削除して Clone し直すのが簡単です
- アクセス解析を設定済みなら、Cloudflare 側の登録URLも変更が要ります

### 独自ドメインを使う場合

`hinomado.jp` のようなドメインを取れば、そちらでも公開できます。Settings → Pages の Custom domain に入力し、ドメイン側でDNSを設定します。年間1,000〜3,000円ほどかかりますが、覚えやすく、リポジトリ名を変えてもURLが変わらなくなります。

## 記事を書く

`posts/` に `.md` ファイルを置くだけです。ファイル名がそのままURLになります。

```markdown
---
title: 記事の見出し
date: 2026-08-16
summary: 一覧に出る短い説明。
tags: おしらせ ごみ
---

本文をマークダウンで書きます。

## 見出し

- 箇条書き
- **強調** や [リンク](https://example.com) が使えます
```

先頭の `---` で囲む部分は必須です。`date` を未来の日付にしておくと、その日が来るまで公開されません（予約投稿）。

書いたら Commit → Push。次のビルドで `kiji.html` の一覧と、記事ごとのページができます。

日付は書いた日ではなく「公開したい日」を入れてください。並び順に使われます。

## お問い合わせフォーム

静的サイトなのでサーバーがありません。外部のフォーム配信サービスを使います。

### Formspree を使う（無料・おすすめ）

1. https://formspree.io/ に登録し、New Form でフォームを作る
2. 表示される送信先URL `https://formspree.io/f/xxxxxxx` の **末尾のIDだけ**をコピー
3. `data/site.json` に入れる

```json
"contact": {
  "provider": "formspree",
  "formspree_id": "xxxxxxx"
}
```

無料枠は月50件まで。届いた内容は登録したメールアドレスに転送されます。

### メールアドレスを載せるだけにする

```json
"contact": {
  "provider": "mailto",
  "email": "your-address@example.com"
}
```

手軽ですが、迷惑メールが増えやすい点に注意してください。

`provider` を空にすると、お問い合わせページに手段が出ません。

## 事業者向けの補助金

`data/hojokin.json` を手で書きます。**制度は年度ごとに変わるので、年に一度は見直してください。**

同梱分は町・商工会・県の入口をまとめたもので、金額や締切はあえて書いていません。すぐ古くなって害になるためです。「どこに何があるか」と「まず商工会に相談」を伝えることに絞っています。

## アクセス解析

Cookieを使わない方式を2つ用意しています。どちらも同意バナーが不要で、個人を特定する情報を集めません。既定では**何も出力されません**。

### Cloudflare Web Analytics（おすすめ・無料）

1. https://dash.cloudflare.com/ に登録
2. 左メニューの Analytics & Logs → Web Analytics → Add a site
3. 公開したURL（`ユーザー名.github.io/hinomado` など）を登録
4. 表示されるスニペットの中の `token` の値（英数字の長い文字列）をコピー

`data/site.json` を書き換えます。

```json
"analytics": {
  "provider": "cloudflare",
  "token": "ここにトークン"
}
```

### GoatCounter（オープンソース・個人利用は無料）

1. https://www.goatcounter.com/ でサイトコードを決めて登録（例 `hinomado`）
2. そのコードを入れる

```json
"analytics": {
  "provider": "goatcounter",
  "token": "hinomado"
}
```

設定するとフッターに「Cookieを使わない解析を利用しています」という一文が自動で出ます。`provider` を空にすれば解析タグもこの一文も消えます。

**Googleアナリティクスは入れていません。** Cookieを使うため同意バナーが必要になり、公共性の高い情報を載せるこのサイトの性格と合わないためです。必要なら `analytics_tag()` に追加できますが、その場合は同意管理の実装が要ります。

## ページ構成

- **トップ（index.html）** — 今日の3つの窓（天気・全地区のごみ・催し）／お知らせ／時事ニュース／きょうの暮らし／お出かけ
- **子育て（kosodate.html）** — 年齢別・目的別に整理した支援の入口と、子育てタグの新着
- **ふるさと納税（furusato.html）** — 寄附の入口と、町の発信から拾った関連お知らせ
- **子育て（kosodate.html）** — 相談先、時期ごとの手続き、行ける場所、お金の制度、子育て関連のお知らせ
- **議会（gikai.html）** — 会議録の要点、原文・議会だより・中継への入口

子育てページのリンクは、実在を確かめられた町の公式ページだけを直接リンクし、それ以外は「子育て支援」のまとめページに寄せています。個別事業のページはURLが変わりやすいためです。リンクを増やすときは、必ず開いて確認してから `data/kosodate.json` に追加してください。

上部の目次バーは全ページ共通です。ページを増やすときは `templates/base.html.j2` を継承して、`build_site.py` の `pages` リストに1行足してください。

## 天気アイコンについて

気象庁が配信しているアイコンはライセンスが明示されていないため使っていません。予報文（「晴れ 昼過ぎから 夕方 雷雨」など）から自前のSVGを選んでいます。判定は `build_site.py` の `weather_icon()` にあり、雷→雪→雨→晴れ／くもり の順に見ます。

予報文は主部（晴れ）と補足（昼過ぎから夕方雷雨）に分けて表示し、どちらも折り返さないようにしています。補足が長い場合は末尾が省略されます。

## 取得元を足す

`data/sources.json` に1件足すだけです。RSS があるなら `type` は `rss`。

```json
{
  "id": "example",
  "name": "配信元の名前",
  "short": "略称",
  "type": "rss",
  "url": "https://example.com/feed",
  "site": "https://example.com/",
  "category": "town"
}
```

RSS がない一覧ページからは `"type": "html"` と `link_pattern`（拾いたいリンクURLの正規表現）で見出しを拾えます。日野町のイベント一覧がこの方式です。

`category` は `town` / `event` / `alert` / `life` / `business` のいずれか。絞り込みボタンに対応します。子育て・高齢者などの細かいタグは `fetch_news.py` の `TAG_RULES` がタイトルから自動で付けます。ここに単語を足せば分類の精度が上がります。

## お出かけ情報の育て方

`data/spots.json` が唯一の手作業です。ここを丁寧に書くほどサイトの価値が上がります。

- `season` に月を入れると、その月にトップの「見ごろ」欄とカードのバッジに出ます（`nature` と `festival` のみ対象）
- `schedule` を入れた祭りは、開催月に入るとページの先頭に大きく出ます。終わると自動で消えます

```json
"schedule": { "type": "fixed", "month": 5, "days": [2, 3], "label": "5月2日（宵祭）・3日（本祭）" }
"schedule": { "type": "nth_weekday", "month": 9, "weekday": 6, "nth": 1, "label": "9月の第1日曜" }
"schedule": { "type": "range", "start": [2, 8], "end": [3, 8], "approximate": true }
```

`weekday` は 0=月曜、6=日曜。`approximate` を `true` にすると「年により前後します」と添えられます。**日程は必ず公式ページで確認してから入れてください。** 同梱分は日野祭・火ふり祭・芋競べ祭り・ひなまつり紀行の4件で、いずれも町または観光協会の記載に基づいています。
- `blurb` は必ず自分の言葉で書きます。他サイトの説明文を写さないでください
- `source` は情報のもとになった場所。フッターの出典表記につながります
- `links` に公式サイトやSNSを入れると、カードの下にアイコン付きのボタンが出ます

```json
"links": [
  { "label": "Instagram", "icon": "inst", "url": "https://www.instagram.com/..." },
  { "label": "X", "icon": "x", "url": "https://twitter.com/..." },
  { "label": "公式サイト", "icon": "web", "url": "https://..." }
]
```

`icon` は `inst` / `x` / `fb` / `web` から選びます。**実在を確認したアカウントだけ入れてください。** 同梱分は、なないろ・ツバメカフェ・ブルーメの丘・近江日野商人館・ふるさと館・みかく・日野曳山保存会のみ確認済みで、残りは空にしてあります。個人店は閉店やアカウント変更が起きやすいので、半年に一度は見直すことをおすすめします。

## ごみ収集日について

**令和8年度（2026年度）の4地区ぶんは確認済みです。** 公式カレンダーPDFから全740日を書き起こし、`verified` は `true` になっています。

| 地区 | 対象 | 燃えるごみ | 登録 |
|---|---|---|---|
| A | 村井・大窪・河原・松尾・大谷・中道 | 月・木 | 185日 |
| B | 小井口・寺尻・木津・椿野台・上野田・いせの・日田・五月台・西大路・鎌掛 | 火・金 | 185日 |
| C | 東西桜谷・山本・湖南サンライズ | 月・木 | 185日 |
| D | 南比都佐・必佐（山本・湖南サンライズを除く） | 火・金 | 185日 |

品目は8種類（燃えるごみ／びん／ペットボトル／スチール缶・アルミ缶／古紙／不燃ごみ（袋）／不燃ごみ（粗大）／使用済乾電池）に分けて登録しています。

規則ではなく **日付を1つずつ書き並べる方式（`"type": "dates"`）** を使っています。この町のカレンダーは「第2・第4水曜」のような規則にあてはまらず、祝日でずれる日も多いためです。祝日による例外は全32日あり、すべて日付として登録済みです。

### 翌年度への更新（年1回・必須）

**4月に新しいカレンダーが出たら、必ず更新してください。** 日付を直接持っているため、放置すると収集日が表示されなくなります。

1. `data/gomi.json` の `verified` を `false` に戻す
2. 一覧ページ（https://www.town.shiga-hino.lg.jp/0000008171.html ）から新年度のPDFを開き、`fiscal_year` と各地区の `pdf` を書き換える
3. 各地区・各品目の `dates` を新しい日付に置き換える
4. `python scripts/check_gomi.py --area A 2027 9` などで月ごとに描画し、PDFと照合する
5. 全地区・全月が合ったら `python scripts/check_gomi.py --verify`

`verified` が `false` のあいだは、サイトに赤い注意書きが出て収集日が薄く表示されます。**間違った日を確定表示しないための仕組みなので、この動作は変えないでください。**

### 照合ツールの使い方

```bash
python scripts/check_gomi.py                  # 全地区の今月と来月
python scripts/check_gomi.py --area B         # B地区だけ
python scripts/check_gomi.py --area A 2026 9  # 地区と年月を指定
python scripts/check_gomi.py --verify         # 確認済みとして記録
```

Windows では `python3` ではなく `python`（または `py`）です。

### 書式

```json
{ "label": "燃えるごみ", "kind": "burn", "type": "dates",
  "dates": ["2026-04-02", "2026-04-06"] }
```

`kind` は `burn`（燃える・赤系）／`resource`（資源・青系）／`other`（不燃や古紙・茶系）で、色分けに使います。規則で表せる地区があれば `weekly`（`"weekdays": [0, 3]` = 月・木）や `monthly`（`"weekday": 2, "nth": [1, 3]` = 第1・3水曜）も使えます。臨時の休止・追加は `skip` と `add` で指定できます。

### 検証の考え方

書き起こしの正しさは、次の2つで確かめました。翌年度の更新時も同じ方法が使えます。

- **例外日が祝日と一致するか** … 基本の曜日から外れた日が、祝日の前後に集中しているか。32日すべてが一致しました
- **地区どうしの照合** … A・Cの燃えるごみが完全一致、B・Dも完全一致。品目ごとの日数も4地区で揃っています

## 天気について

気象庁が公開しているJSONを使います。公式APIとして提供されているものではないので、仕様変更で壊れる可能性があります。取得に失敗しても他の欄は普通に出るようにしてあります。

日野町は滋賀県南部の予報区です。区域コードは直に書かず「南部」という名前で探すようにしているので、コードが変わっても動きます。警報は市町村名に「日野」を含む区域を見ています。

警報が発表されているときだけ、ページ上部に朱色の帯が出ます。天気は1日2回（朝6時と夕方6時）更新します。

## 時事ニュースの絞り込み

「日野町」は東京都日野市・鳥取県日野町とも紛れます。報道系の取得元には `include` と `exclude` を付けて、タイトルと概要でふるいにかけています。

```json
"include": ["日野町"],
"exclude": ["日野市", "鳥取", "東京都", "日野自動車"]
```

`include` は1語でも含めば通し、`exclude` は1語でも触れれば落とします。誤って混じる記事を見つけたら `exclude` に足してください。Googleニュース経由の記事はリンク先が転送になるので、`rel="nofollow"` を付けています。

## 議会の要約について

`scripts/fetch_gikai.py` は次の順に動きます。

1. 会議録の一覧ページから、公開されている会議録のリンクを集める
2. まだ要約していないものを新しい順に選ぶ
3. `ANTHROPIC_API_KEY` があれば、そのページのPDFを読んで要点をまとめる
4. `data/gikai.json` に書き出す（一度要約したものは再実行しない）

1回の実行で新しく要約するのは `MAX_NEW_SUMMARIES`（既定2件）までです。APIキーが無い場合は一覧とリンクだけを作ります。GitHub Actions で使うときは、リポジトリの Settings → Secrets に `ANTHROPIC_API_KEY` を登録してください。

**会議録は公開まで数か月かかります。** 令和7年12月定例会議の会議録が公開されたのは2026年4月でした。「いま何が議論されているか」を知るには議会だよりかインターネット配信のほうが早いので、そちらへの導線も同じ欄に置いています。

要約は機械が作ったものなので、各カードに原文へのリンクと注意書きを必ず添えています。この表示は消さないでください。

## 著作権と運用のきまり

このサイトは各配信元の**見出し・日付・リンク**だけを表示し、本文は転載しません。紹介文はすべて独自に書いています。

- 日野町のサイトは著作権が町または情報提供者に帰属します。リンクは自由ですが、本文や写真の転載はできません
- 新聞社の記事はより厳しいので、見出しとリンクのみにとどめます。要約も作りません
- 議会の会議録は、公開の場で行われた議員・町側の発言の記録です。要約して紹介する余地は新聞記事より広いと考えられますが、判断に迷う場合は議会事務局（0748-52-6551）に確認してください
- 議会の要約では、賛否が分かれた論点はどちらの立場も同じ扱いで書くようスクリプトのプロンプトに明記しています
- 取得は1日1回。`fetch_news.py` の `REQUEST_INTERVAL` で配信元への間隔を空けています
- User-Agent に連絡先を書いてください（`fetch_news.py` の `UA`）
- フッターに「非公式」と明記しています。消さないでください

公開したら、日野町の企画振興課と日野観光協会に一報を入れておくと安心です。

## 壊れたときのふるまい

- 1つの配信元が落ちても他は取得を続け、失敗はページ上部に控えめに表示されます
- `data/news.json` は毎回マージされるので、配信元が古い記事を落としても履歴は残ります
- すべての配信元が失敗したときだけ Actions が赤くなり、通知が届きます
