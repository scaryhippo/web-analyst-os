# Web Analyst OS v1.4 — コンテンツ収集精度修正プロンプト
作成日: 2026-04-26  
対象ディレクトリ: `~/Projects/web-analyst-os`

## 背景・目的

sunphototakahashi.comの分析で以下の誤出力が発生した：
- 「料金が掲載されていない」→ 実際は明確な料金表が存在
- 「日祝の矛盾」→ 実際は「スタジオ撮影は要予約で承る」と明記
- 「社会的証明ゼロ」→ GoogleマップにGoogle Maps 4.6★（48件）が存在

原因：WordPressの翻訳プラグイン（200言語リスト）がDOM上で本文より先に展開され、
`inner_text('body')` の先頭3,000文字を占有。実コンテンツが取得範囲外に押し出された。

本修正で誤情報出力を防止し、v1.4を正式商用リリース版とする。

---

## Fix A：ノイズ除去付きコンテンツ抽出（最重要）

### 対象ファイル：`core/browser.py`

**修正箇所1：メインページの本文取得**

既存の `inner_text('body')` 呼び出しを以下の関数に置き換える。
メインページ収集処理（`collect()` または相当のメソッド）内を探して修正すること。

```python
async def extract_main_content(self, page) -> str:
    """
    ナビゲーション・翻訳ウィジェット等のノイズを除去した上で
    本文テキストを取得する。
    DOM操作はページのコピー上で行い、元のページ描画には影響しない。
    """
    text = await page.evaluate("""
        () => {
            // ノイズ要素のセレクタリスト（除去対象）
            const NOISE_SELECTORS = [
                // Google翻訳ウィジェット関連
                '#google_translate_element',
                '.goog-te-combo',
                '.goog-te-banner-frame',
                '.skiptranslate',
                '.goog-te-gadget',
                // 言語選択系（汎用）
                'select',
                '[class*="language"]',
                '[id*="language"]',
                '[class*="translate"]',
                '[id*="translate"]',
                // ページ構造ノイズ
                'nav',
                'header',
                'footer',
                'script',
                'style',
                'noscript',
                'iframe',
                // WordPress系プラグインノイズ
                '#wpadminbar',
                '.wp-admin-bar',
            ];
            
            // クローンを作成してDOM操作（元ページへの影響を避ける）
            const clone = document.body.cloneNode(true);
            NOISE_SELECTORS.forEach(sel => {
                clone.querySelectorAll(sel).forEach(el => el.remove());
            });
            
            // メインコンテンツ領域を優先的に取得
            const mainSelectors = ['main', 'article', '#content', '.content', 
                                   '#main', '.main', '[role="main"]'];
            for (const sel of mainSelectors) {
                const el = clone.querySelector(sel);
                if (el && el.innerText.trim().length > 200) {
                    return el.innerText.trim();
                }
            }
            
            // メイン要素が見つからない場合はclone全体を返す
            return clone.innerText.trim();
        }
    """)
    return text
```

**修正箇所2：メインページ収集でこの関数を使用**

メインページの `page_text_content` を収集している箇所を探し、
`await page.inner_text('body')` を `await self.extract_main_content(page)` に置き換える。

**修正箇所3：`crawl_subpages()` でも同様に適用**

`crawl_subpages()` 内の以下の行を修正する：

```python
# 変更前
sub_text = await sub_page.inner_text('body')

# 変更後
sub_text = await self.extract_main_content(sub_page)
```

---

## Fix B：JSON-LD構造化データの取得と活用

### 対象ファイル1：`core/browser.py`

`collect()` メソッド内に以下のJSON-LD取得処理を追加する：

```python
async def extract_structured_data(self, page) -> dict:
    """
    JSON-LD構造化データを取得し、分析に有用なフィールドを抽出する。
    Schema.org準拠のデータを持つサイトでは、営業時間・料金・評価等が
    本文テキストより信頼性の高い形式で取得できる。
    """
    raw_jsonld = await page.evaluate("""
        () => {
            const scripts = document.querySelectorAll('script[type="application/ld+json"]');
            return Array.from(scripts).map(s => {
                try { return JSON.parse(s.textContent); }
                catch(e) { return null; }
            }).filter(Boolean);
        }
    """)
    
    # 有用なフィールドを平坦化して抽出
    extracted = {}
    for item in raw_jsonld:
        if not isinstance(item, dict):
            continue
        
        # 基本情報
        if item.get('@type') in ['LocalBusiness', 'Store', 'Restaurant', 
                                   'PhotoStudio', 'Organization', 'ProfessionalService']:
            extracted['business_name'] = item.get('name', '')
            extracted['address'] = item.get('address', {})
            extracted['telephone'] = item.get('telephone', '')
            extracted['price_range'] = item.get('priceRange', '')
            extracted['founding_date'] = item.get('foundingDate', '')
            
            # 営業時間
            hours = item.get('openingHours', item.get('openingHoursSpecification', []))
            if hours:
                extracted['opening_hours'] = hours
            
            # 集計評価（Googleなど外部レビューがSchema.orgで埋め込まれている場合）
            rating = item.get('aggregateRating', {})
            if rating:
                extracted['aggregate_rating'] = {
                    'value': rating.get('ratingValue', ''),
                    'count': rating.get('reviewCount', rating.get('ratingCount', '')),
                    'best': rating.get('bestRating', 5),
                }
        
        # 価格情報（Offer / PriceSpecification）
        offers = item.get('offers', item.get('hasOfferCatalog', {}))
        if offers:
            extracted['offers'] = offers
    
    return extracted
```

### 対象ファイル2：`core/state.py`

`AnalystState` TypedDictに以下を追加：

```python
structured_data: dict  # JSON-LD構造化データ（空の場合は{}）
```

`main.py` の `build_initial_state()` にも `"structured_data": {}` を追加する。

### 対象ファイル3：`core/graph.py` または Phase 0 処理

Phase 0のブラウザ収集後に構造化データを取得してstateに格納する：

```python
structured_data = await collector.extract_structured_data(page)
state.update({"structured_data": structured_data})
```

### 対象ファイル4：各エージェント（`agents/*.py`）

**全エージェントのシステムプロンプト末尾**に以下の指示を追加する：

```
【構造化データの優先利用】
state["structured_data"] にJSON-LD由来のデータが存在する場合、
営業時間・料金・評価・住所に関する記述はこのデータを一次情報として使用すること。

特に以下の誤りを防ぐこと：
- opening_hours に特定曜日の例外規定がある場合、それを無視して
  「定休日との矛盾」を指摘してはならない
- price_range や offers にデータがある場合、
  「料金が掲載されていない」と断言してはならない
- aggregate_rating にデータがある場合、
  「社会的証明がない」とは言わず「Webページ上に口コミ表示がない」と表現すること

structured_dataが空の場合は従来通りテキストコンテンツから推論する。
```

---

## Fix C：テキスト取得文字数の拡張

### 対象ファイル：`core/browser.py`

Fix Aのノイズ除去により実質的なコンテンツ密度が上がるため、
上限文字数を同時に拡張する。

**サブページ収集部分：**
```python
# 変更前
'text_content': sub_text[:3000],

# 変更後
'text_content': sub_text[:8000],
```

**メインページ収集部分**も同様に確認し、文字数上限があれば8,000〜10,000に拡張する。

---

## Fix D：外部プラットフォーム免責注記の追加

### 対象ファイル：`core/report.py`

レポートの末尾（パフォーマンスメトリクスセクションの後）に以下を追加する：

```python
disclaimer = """
## 分析上の注記

本レポートは対象WebページのHTMLテキストコンテンツおよびJSON-LD構造化データに基づく分析です。
以下の情報は本システムの収集範囲外となります：

- Google マップ / 食べログ / Yelp 等の外部プラットフォームのレビュー・評価
- SNS（Instagram / X / Facebook 等）の投稿・フォロワー数
- iframe内に表示される外部コンテンツ
- ログイン・会員登録が必要なページのコンテンツ

これらの情報は別途手動で確認し、分析を補完することを推奨します。
"""
```

---

## 実施順序と確認方法

```bash
cd ~/Projects/web-analyst-os

# 1. Fix A + C の確認（ノイズ除去と文字数拡張）
# sunphotoを再実行し、料金情報が正しく取得されているか確認
python main.py https://sunphototakahashi.com/ --crawl-subpages > /tmp/sunphoto_v14.md

# 確認ポイント：
# - P1から「料金が掲載されていない」という誤った指摘が消えていること
# - 料金ページから具体的な金額（5,500円・7,700円等）が分析に反映されていること
grep -i "料金\|5,500\|7,700\|価格" /tmp/sunphoto_v14.md

# 2. Fix B の確認（JSON-LD活用）
# 構造化データが取得されているか確認（デバッグ出力を一時的に追加して確認）
python -c "
import asyncio
from core.browser import BrowserCollector
async def test():
    collector = BrowserCollector()
    await collector.setup()
    page = await collector.browser.new_page()
    await page.goto('https://sunphototakahashi.com/')
    data = await collector.extract_structured_data(page)
    print(data)
    await collector.teardown()
asyncio.run(test())
"
# opening_hours・aggregateRating等が出力されることを確認

# 3. Fix D の確認（免責注記）
grep "外部プラットフォーム" /tmp/sunphoto_v14.md
# 注記が存在することを確認

# 4. 回帰テスト（atelier-a3 / byheart で既存の品質が維持されているか）
python main.py https://atelier-a3.jp --site-type portfolio --crawl-subpages
python main.py https://www.byheart.jp/
```

---

## 確認の判定基準

v1.4リリース判定のために以下を確認する：

| 確認項目 | 合格基準 |
|---|---|
| sunphoto料金情報 | 「料金が掲載されていない」という誤指摘が消えている |
| sunphoto日祝対応 | 「要予約で対応可能」が分析に反映されている |
| atelier-a3回帰 | v1.3と同等のスコア・指摘内容が維持されている |
| byheart回帰 | v1.3と同等のスコア・指摘内容が維持されている |
| 免責注記 | 全レポートの末尾に外部プラットフォーム注記が存在する |

---

## バージョン管理

```bash
git add -A
git commit -m "v1.4: noise-aware content extraction, JSON-LD integration, external platform disclaimer"
git push origin main
```
