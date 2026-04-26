# Web Analyst OS v1.2 — 改善指示プロンプト
作成日: 2026-04-26  
対象ディレクトリ: `~/Projects/web-analyst-os`

v1.1の3サイト実テスト（scaryhippo.jp / atelier-a3.jp / byheart.jp）で発見された問題を修正する。
修正は Fix A〜E の5項目。実施順は記載順に従うこと。

---

## Fix A: 重複除去の抜本的強化（最優先）

### 背景
v1.1の重複除去（DEDUP_KEYWORDS）はキーワードが狭すぎ、byheart.jpで「ページサイズ最適化」が7〜8回出現、scaryhippoで「経歴の検証不能」が4回出現した。意味的に同一のトピックをグループで捕捉できていない。

### 修正内容

**`core/report.py`** の `DEDUP_KEYWORDS` を以下の拡張版に置き換える：

```python
# トピックグループ: 各グループのキーワードが1つでもマッチすれば同一トピックとみなす
DEDUP_TOPIC_GROUPS = [
    # 画像・ページサイズ最適化（最多重複）
    ["WebP", "遅延読み込み", "Lazy", "lazy", "ページサイズ", "KB", "画像最適化", "300KB"],
    # 社会的証明・トラストシグナル
    ["社会的証明", "トラスト", "実績数", "クライアント名", "導入施設", "受賞歴", "ロゴ"],
    # CTA・コンバージョン導線
    ["CTA", "ファーストビュー.*CTA", "主CTA", "コンバージョン導線", "問い合わせ.*導線", "READ THE MANIFESTO"],
    # 経歴・プロフィール検証
    ["経歴", "LinkedI", "在籍期間", "MBB.*ファーム", "CIO.*在任", "プロフィール"],
    # なりすましメール・警告バナー
    ["なりすまし", "警告バナー", "警告.*配置", "フィッシング"],
    # WORKSページ・ポートフォリオ不在
    ["WORKSページ", "ポートフォリオ.*確認", "作品.*不在", "作品.*見え", "ビジュアル.*不在"],
    # ナビゲーション・メニュー
    ["グローバルナビ", "ナビゲーション.*ラベル", "ナビ.*英語", "ナビ.*日本語"],
    # 価格・料金
    ["価格", "料金", "価格帯", "費用", "有償"],
    # フォーム・送信体験
    ["フォーム.*バリデーション", "送信.*フィードバック", "返信.*日数", "エラーメッセージ"],
    # 構造化データ・SEO
    ["構造化データ", "JSON-LD", "OGP", "Twitter Card", "meta description"],
    # パンくず・現在地
    ["パンくず", "breadcrumb", "現在地"],
    # タップターゲット・モバイル操作性
    ["タップターゲット", "44×44", "48×48", "モバイル.*タップ"],
    # フォーカス・アクセシビリティ
    ["focus-visible", "フォーカス表示", "キーボードナビ", "スクリーンリーダー", "WCAG"],
    # ターゲット分離・BtoB/BtoC混在
    ["BtoB.*BtoC", "施設担当者.*求職者", "ターゲット.*分離", "ターゲット.*分岐"],
    # H1・ヒーローコピーの明確性
    ["H1.*コピー", "ヒーロー.*5秒", "ファーストビュー.*伝わらない", "5秒以内.*伝わら"],
]
```

**`dedup_recommendations()` 関数を以下に置き換える：**

```python
import re

def dedup_recommendations(items: list) -> list:
    """
    DEDUP_TOPIC_GROUPSに基づいてトピックレベルで重複除去する。
    各グループのキーワードが1つでもマッチすれば同一トピックとみなし、
    最初に出現したアイテム（通常、最も詳細で具体的なもの）のみを残す。
    グループ外のアイテムは全て保持する。
    """
    seen_groups: set[int] = set()
    result = []
    
    for item in items:
        item_lower = item.lower()
        matched_group_idx = None
        
        for group_idx, keywords in enumerate(DEDUP_TOPIC_GROUPS):
            for kw in keywords:
                # 正規表現として試みる（パターンに.*が含まれる場合）
                try:
                    if re.search(kw.lower(), item_lower):
                        matched_group_idx = group_idx
                        break
                except re.error:
                    if kw.lower() in item_lower:
                        matched_group_idx = group_idx
                        break
            if matched_group_idx is not None:
                break
        
        # マッチしたグループが未見なら追加、既見なら除去
        if matched_group_idx is None:
            # どのグループにも属さない → 常に保持
            result.append(item)
        elif matched_group_idx not in seen_groups:
            result.append(item)
            seen_groups.add(matched_group_idx)
        # else: 同トピックが既出 → 除去（ログ出力は任意）
    
    return result
```

**適用タイミングの変更：**
現状は P1・P2 それぞれに独立して適用しているが、以下の順序に変更する：

```python
# report.py の generate_report() 内
all_items = p1_items + p2_items + p3_items  # 全優先度を統合
all_items_deduped = dedup_recommendations(all_items)

# 再分離（元の優先度ラベルを保持するため、各アイテムに (priority, content) のタプルを使う）
```

**実装上の注意：** `dedup_recommendations()` を P1・P2・P3 を**統合した状態**で実行することで、P1に残ったトピックがP2・P3に重複して出現することを防ぐ。各アイテムに優先度タグを付けた上で統合→除去→再分離する実装に変更すること。

具体的な実装案：

```python
def build_prioritized_items(p1_raw, p2_raw, p3_raw):
    """優先度タグ付きで統合し、重複除去後に再分離する"""
    tagged = (
        [("P1", item) for item in p1_raw] +
        [("P2", item) for item in p2_raw] +
        [("P3", item) for item in p3_raw]
    )
    
    seen_groups: set[int] = set()
    result_tagged = []
    
    for priority, item in tagged:
        item_lower = item.lower()
        matched_group_idx = None
        
        for group_idx, keywords in enumerate(DEDUP_TOPIC_GROUPS):
            for kw in keywords:
                try:
                    if re.search(kw.lower(), item_lower):
                        matched_group_idx = group_idx
                        break
                except re.error:
                    if kw.lower() in item_lower:
                        matched_group_idx = group_idx
                        break
            if matched_group_idx is not None:
                break
        
        if matched_group_idx is None or matched_group_idx not in seen_groups:
            result_tagged.append((priority, item))
            if matched_group_idx is not None:
                seen_groups.add(matched_group_idx)
    
    p1_out = [item for p, item in result_tagged if p == "P1"]
    p2_out = [item for p, item in result_tagged if p == "P2"]
    p3_out = [item for p, item in result_tagged if p == "P3"]
    return p1_out, p2_out, p3_out
```

この関数を `generate_report()` 内の Fix B（P2キャップ）の前に呼び出す。

---

## Fix B: P2の上限キャップ追加

### 背景
byheart.jpのP2が20件に達した。P2も上限を設けて実用的な優先度リストにする必要がある。

### 修正内容

**`core/report.py`** に定数を追加：

```python
P1_MAX = 5   # 既存
P2_MAX = 10  # 新規追加
```

Fix 2（P1キャップ）と同様の処理をP2にも適用する。超過分はP3の先頭に移動する：

```python
def cap_p2_items(p2_items: list, p3_items: list) -> tuple[list, list]:
    """P2をP2_MAX件に絞り、超過分をP3の先頭に移動する"""
    if len(p2_items) <= P2_MAX:
        return p2_items, p3_items
    
    p2_final = p2_items[:P2_MAX]
    overflow = p2_items[P2_MAX:]
    p3_items = overflow + p3_items
    return p2_final, p3_items
```

適用順序（`generate_report()` 内）：
1. `build_prioritized_items()` で統合重複除去（Fix A）
2. `cap_p1_items()` でP1を5件にキャップ（既存）
3. `cap_p2_items()` でP2を10件にキャップ（新規）

---

## Fix C: `→ →` 二重矢印フォーマットバグの修正

### 背景
byheart.jpのtechnical_auditor出力に `→ →` の二重矢印が3箇所出現している。

### 調査と修正

まず原因を特定する：

1. **`agents/technical_auditor.py`** のシステムプロンプトを確認し、矢印の使用方法を確認する。プロンプト内に `→` を含む例示が二重になっていないか確認。

2. **`core/report.py`** のアイテム生成・結合処理で `→` の重複が発生していないか確認。

3. 修正方針：どちらが原因かに応じて対処。共通の安全策として `core/report.py` に後処理クリーニングを追加：

```python
def clean_arrow_formatting(text: str) -> str:
    """二重矢印 '→ →' を単一 '→' に正規化する"""
    import re
    # '→ →' '→→' '→　→' などのバリエーションを正規化
    text = re.sub(r'→\s*→', '→', text)
    return text
```

`generate_report()` 内でP1・P2・P3の各アイテムに対してこのクリーニングを適用する：

```python
def clean_items(items: list) -> list:
    return [clean_arrow_formatting(item) for item in items]
```

---

## Fix D: サブページクローリングオプションの追加

### 背景
atelier-a3.jpは `https://atelier-a3.jp/works/` にポートフォリオ写真（The Archives）があるが、OSがトップページのみ収集したため「ビジュアル不在・WORKSコンテンツ確認不可」と誤判定した。7.6KBという分析結果もトップページのサイズであり、作品ページの存在を反映していない。

### 修正内容

**`interface/cli.py`** に新オプションを追加：

```python
parser.add_argument(
    "--crawl-subpages",
    action="store_true",
    default=False,
    help="ナビゲーションリンクから最大3サブページを追加収集する（ポートフォリオ・WORKSページ等）"
)
parser.add_argument(
    "--crawl-max",
    type=int,
    default=3,
    help="--crawl-subpages使用時の最大収集サブページ数（デフォルト3）"
)
```

**`core/browser.py`** の `BrowserCollector` クラスに `crawl_subpages()` メソッドを追加：

```python
async def crawl_subpages(self, page, base_url: str, max_pages: int = 3) -> list[dict]:
    """
    ナビゲーションリンクを抽出し、最大max_pages件のサブページを収集する。
    収集対象: <nav>内のリンク優先、次いで<a>タグでhrefが内部リンクのもの。
    除外: #から始まるアンカーリンク、外部ドメイン、画像・PDFリンク。
    """
    from urllib.parse import urljoin, urlparse
    
    base_domain = urlparse(base_url).netloc
    
    # ナビゲーションリンクを優先取得
    nav_links = await page.evaluate("""
        () => {
            const links = [];
            // nav要素内のリンクを優先
            document.querySelectorAll('nav a[href], header a[href]').forEach(a => {
                if (a.href && !a.href.startsWith('#')) links.push({href: a.href, text: a.innerText.trim()});
            });
            // 不足する場合は全<a>から補完
            if (links.length < 5) {
                document.querySelectorAll('a[href]').forEach(a => {
                    if (a.href && !a.href.startsWith('#')) {
                        const exists = links.some(l => l.href === a.href);
                        if (!exists) links.push({href: a.href, text: a.innerText.trim()});
                    }
                });
            }
            return links;
        }
    """)
    
    # 内部リンクのみフィルタ
    internal_links = [
        l for l in nav_links
        if urlparse(l['href']).netloc == base_domain
        and not l['href'].endswith(('.jpg', '.png', '.pdf', '.svg'))
        and l['href'] != base_url
        and l['href'] != base_url.rstrip('/')
    ]
    
    subpage_data = []
    for link in internal_links[:max_pages]:
        try:
            sub_page = await self.browser.new_page()
            await sub_page.goto(link['href'], wait_until='domcontentloaded', timeout=15000)
            await sub_page.wait_for_timeout(1500)
            
            sub_text = await sub_page.inner_text('body')
            sub_html = await sub_page.content()
            sub_size = len(sub_html.encode('utf-8'))
            
            subpage_data.append({
                'url': link['href'],
                'nav_label': link['text'],
                'text_content': sub_text[:3000],  # 最大3000文字
                'page_size_bytes': sub_size,
            })
            await sub_page.close()
        except Exception as e:
            print(f"[Browser] サブページ収集スキップ: {link['href']} ({e})")
    
    return subpage_data
```

**`core/state.py`** の `AnalystState` に追加：

```python
subpages: list[dict]  # サブページ収集データ（--crawl-subpages時のみ）
```

**各エージェントのシステムプロンプト**に、`subpages` データが存在する場合にそれを参照する指示を追加する。たとえばux_auditor・competitive_analystのプロンプト末尾に：

```
サブページデータが提供されている場合（state["subpages"]が空でない場合）:
- 各サブページのURL・nav_label・text_contentを参照し、分析に反映させること
- 「コンテンツ確認不可」「ページ内容が不明」等の判定はサブページ確認後に行うこと
- サブページから確認できた情報は推奨の根拠として引用すること
```

**使用例：**
```bash
# atelier-a3.jpのWORKSページも含めて分析
python main.py https://atelier-a3.jp --site-type portfolio --crawl-subpages

# サブページ最大5件
python main.py https://example.com --crawl-subpages --crawl-max 5
```

**レポートヘッダーへの反映：**
`--crawl-subpages` 使用時、レポートの対象URL行の下に収集したサブページURLを列挙する：

```
対象 URL: https://atelier-a3.jp
収集サブページ: /works/ | /manifesto/ | /contact/
```

---

## Fix E: スコア多様性の改善

### 背景
scaryhippo.jp（consulting）とatelier-a3.jp（portfolio）でコンバージョン・ブランドコピーが共に72/100に収束した。独立したエージェントが同一値に収束するのは不自然で、エージェント間のアンカリングが起きている可能性がある。

### 修正内容

**各エージェント（`agents/*.py`）のスコアリング指示**に以下の文言を追加する：

```
【スコアリング独立性の確保】
- スコアは必ず5の倍数ではなく、実際の評価に基づいた値（例: 67, 73, 81）を使用すること。
- 他のエージェントのスコアを参照・調整しないこと（あなたは専門家として独立して評価する）。
- 70〜79の範囲に集中することを避け、サイトの実態に基づいて0〜100の全範囲を積極的に活用すること。
- 評価の根拠を1〜2文で示した上でスコアを確定すること（例: 「技術パフォーマンスは優秀（908ms / 39KB）だが、Core Web Vitalsデータが取得できないため満点とはしない。スコア: 87」）。
```

**`core/scorer.py`** の加重平均計算後に、スコアの妥当性チェックを追加する：

```python
def validate_score_diversity(scores: dict[str, int]) -> bool:
    """
    全エージェントのスコアが同一値または5点以内に収まっている場合に警告を出す。
    （エージェント間のアンカリングを検出）
    """
    values = list(scores.values())
    if len(values) < 3:
        return True
    score_range = max(values) - min(values)
    if score_range <= 5:
        print(f"[Scorer] ⚠️ スコア分布が狭すぎます（レンジ: {score_range}点）。エージェント独立性を確認してください。")
        return False
    return True
```

---

## 実施順序と確認方法

```bash
cd ~/Projects/web-analyst-os

# 1. Fix C（最小変更・二重矢印修正）を先に適用・確認
python main.py https://www.byheart.jp/ 2>&1 | grep "→ →"
# 出力ゼロになることを確認

# 2. Fix A（重複除去強化）を適用
# byheart.jpで「WebP」「ページサイズ」の出現回数を確認
python main.py https://www.byheart.jp/ 2>&1 | grep -c "WebP\|ページサイズ"
# 1〜2回以下になることを確認

# 3. Fix B（P2キャップ）を適用
# byheart.jpのP2が10件以下になることを確認
python main.py https://www.byheart.jp/ > /tmp/byheart_v12.md
grep -c "^- \[" /tmp/byheart_v12.md  # セクション別件数確認

# 4. Fix D（サブページクローリング）を適用
python main.py https://atelier-a3.jp --site-type portfolio --crawl-subpages
# レポートヘッダーに「収集サブページ」行が出ることを確認
# WORKSページのコンテンツが分析に反映されることを確認

# 5. Fix E（スコア多様性）を適用
# scaryhippo.jpを再実行してスコアが72に集中しないことを確認
python main.py https://scaryhippo.jp --site-type consulting
```

---

## バージョン管理

```bash
git add -A
git commit -m "v1.2: dedup overhaul, P2 cap, arrow fix, subpage crawl, score diversity"
git push origin main
```

---

## 注記: atelier-a3.jpの再評価

Fix D適用後、以下のコマンドで再テストを推奨する：

```bash
python main.py https://atelier-a3.jp --site-type portfolio --crawl-subpages
```

`/works/` の写真コンテンツが取得できた場合、エグゼクティブサマリーおよびSkeptical First-Timerの評価（現状「ビジュアル不在」）が実態と合致する内容に更新される見込み。
