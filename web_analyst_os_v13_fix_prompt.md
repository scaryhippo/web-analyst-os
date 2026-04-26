# Web Analyst OS v1.3 — 最終商用化修正プロンプト
作成日: 2026-04-26  
対象ディレクトリ: `~/Projects/web-analyst-os`

## 目的
クライアントへの直接提示を可能にするための最終修正。3点のみ対象とし、
それ以外の変更は行わないこと。

---

## Fix 1: Skeptical First-Timerの自己修正表示の除去

### 問題
agents/skeptical_firsttimer.py（またはレポート生成側）が、エージェントの
内部的な判断修正プロセス（「判定: RESOLVED」→「再判定: PARTIALLY_RESOLVED」）
を出力に含めている。クライアント向けレポートとして不適切。

### 修正内容

**`core/report.py`** のSkeptical First-Timerセクション組み立て処理に、
後処理クリーニングを追加する：

```python
import re

def clean_skeptical_output(text: str) -> str:
    """
    Skeptical First-Timerの出力から自己修正（再判定）の痕跡を除去する。
    
    対象パターン:
    - 「判定: RESOLVED\n\n---\n\n**再判定: PARTIALLY_RESOLVED**」のような
      二段階判定を、最終判定のみに統一する。
    - 「---」区切りで分かれた再評価テキストも、最終版のみ残す。
    """
    # パターン1: 「判定: XXX」が2回以上出現する場合、最後のものを採用
    judgments = re.findall(r'判定:\s*(RESOLVED|PARTIALLY_RESOLVED|UNRESOLVED)', text)
    if len(judgments) >= 2:
        # 最終判定のみを残し、途中の修正プロセスを削除
        final_judgment = judgments[-1]
        # 「---」以降の再判定ブロックを削除
        text = re.sub(r'\n+---\n+\*\*再判定.*', '', text, flags=re.DOTALL)
        # 最初の判定を最終判定に書き換え
        text = re.sub(
            r'判定:\s*(RESOLVED|PARTIALLY_RESOLVED|UNRESOLVED)',
            f'判定: {final_judgment}',
            text,
            count=1
        )
    
    # パターン2: 「**再判定: XXX**」という表記そのものを除去
    text = re.sub(r'\*\*再判定:\s*(RESOLVED|PARTIALLY_RESOLVED|UNRESOLVED)\*\*\n*', '', text)
    
    return text.strip()
```

この関数を `generate_report()` 内の各Skeptical First-Timerセクション生成後に適用する：

```python
# Skeptical First-Timerセクションのクリーニング
for attack_key in ["clarity_attacker", "trust_destroyer", "action_blocker"]:
    if attack_key in state.get("skeptical_analyses", {}):
        state["skeptical_analyses"][attack_key] = clean_skeptical_output(
            state["skeptical_analyses"][attack_key]
        )
```

また、**`agents/skeptical_firsttimer.py`** のシステムプロンプトに以下を追加する：

```
【判定の確定性】
- 評価・判定は一度だけ出力すること。
- 「再判定」「訂正」「上記を修正して」などの自己修正プロセスを出力に含めないこと。
- 迷いがある場合は最初から慎重に判断し、確定した判定のみを出力する。
- 判定フォーマット: 「判定: RESOLVED / PARTIALLY_RESOLVED / UNRESOLVED のいずれか1つ」
```

---

## Fix 2: P3のスコアのみ項目を除去

### 問題
`[スコア XX/100] ... — 次スプリントで対応推奨` という行がP3に残存している。
v1.1で実装したFix 3（P2品質フィルタ）がP3に適用されていないことが原因。

### 修正内容

**`core/report.py`** の `filter_p2_quality()` 関数（またはその相当処理）を
P3にも適用する。関数名を汎用化して再利用する：

```python
def filter_section_quality(items: list) -> list:
    """
    スコアのみの項目（アクション指示「→」を持たない）をフィルタする。
    P2・P3の両方に適用する。
    """
    filtered = []
    for item in items:
        # 「→」を含む = 具体的アクションあり → 残す
        if "→" in item:
            filtered.append(item)
        # [agent_name]形式で始まり、60文字超のコンテンツがある → 残す
        elif re.match(r"- \[(?!スコア)[^\]]+\]", item) and len(item) > 60:
            filtered.append(item)
        # それ以外（スコアのみ・短すぎる） → 破棄
        # 例: "- [スコア 41/100] UX・使いやすさ — 次スプリントで対応推奨"
    return filtered
```

`generate_report()` 内でP2とP3の両方に適用する：

```python
p2_items = filter_section_quality(p2_items)
p3_items = filter_section_quality(p3_items)  # ← この行を追加
```

---

## Fix 3: サブページ収集の品質フィルタ強化

### 問題
sunphototakahashi.comで以下の誤収集が発生した：
- 同一ドメインのトップページが2回収集される
- 「Menu」などコンテンツのないナビ専用ページが収集される
- 実際のコンテンツページ（/gallery/, /service/, /fee/ 等）に届かない

### 修正内容

**`core/browser.py`** の `crawl_subpages()` メソッドを以下のように強化する：

```python
async def crawl_subpages(self, page, base_url: str, max_pages: int = 3) -> list[dict]:
    from urllib.parse import urljoin, urlparse
    import re
    
    base_domain = urlparse(base_url).netloc
    base_path = urlparse(base_url).path.rstrip('/')
    
    # 収集除外パターン
    EXCLUDE_PATTERNS = [
        r'^#',                          # アンカーリンク
        r'javascript:',                 # JavaScriptリンク
        r'\.(jpg|png|pdf|svg|gif|zip|mp4|webp)$',  # ファイル直リンク
        r'/(wp-admin|admin|login|logout|cart|checkout)',  # 管理・決済ページ
        r'[?&](page|p)=\d+',           # ページネーション
        r'#.*$',                        # URLのアンカー部分
    ]
    
    # コンテンツページらしさを判定するキーワード
    CONTENT_INDICATORS = [
        'service', 'works', 'gallery', 'portfolio', 'about', 'contact',
        'fee', 'price', 'menu', 'product', 'news', 'blog', 'profile',
        'サービス', '料金', '実績', '会社', 'ギャラリー', '作品',
    ]
    
    nav_links = await page.evaluate("""
        () => {
            const links = [];
            const seen = new Set();
            
            // nav・header内のリンクを優先取得
            const selectors = ['nav a[href]', 'header a[href]', '.menu a[href]', '#menu a[href]'];
            for (const sel of selectors) {
                document.querySelectorAll(sel).forEach(a => {
                    const href = a.getAttribute('href');
                    const text = a.innerText.trim();
                    if (href && text && !seen.has(href)) {
                        seen.add(href);
                        links.push({href: a.href, text: text, pathname: a.pathname});
                    }
                });
            }
            return links;
        }
    """)
    
    # フィルタリング
    def is_valid_subpage(link: dict) -> bool:
        href = link.get('href', '')
        text = link.get('text', '')
        pathname = link.get('pathname', '').rstrip('/')
        
        # 除外パターンチェック
        for pattern in EXCLUDE_PATTERNS:
            if re.search(pattern, href, re.IGNORECASE):
                return False
        
        # 外部ドメインを除外
        if urlparse(href).netloc != base_domain:
            return False
        
        # トップページと同一URLを除外
        if pathname == base_path or pathname == '' or pathname == '/':
            return False
        
        # テキストが1文字以下（アイコンリンク等）を除外
        if len(text) <= 1:
            return False
        
        # ナビテキストが「Menu」「HOME」「TOP」「×」等の汎用ラベルのみを除外
        generic_labels = {'menu', 'home', 'top', '×', 'close', 'open', 'toggle', 'back'}
        if text.lower() in generic_labels:
            return False
        
        return True
    
    # コンテンツらしさでソート（コンテンツキーワードを含むURLを優先）
    def content_score(link: dict) -> int:
        score = 0
        combined = (link.get('href', '') + link.get('text', '')).lower()
        for kw in CONTENT_INDICATORS:
            if kw in combined:
                score += 1
        return score
    
    valid_links = [l for l in nav_links if is_valid_subpage(l)]
    valid_links.sort(key=content_score, reverse=True)
    
    # URL重複を除去（パスが同一のものは最初の1件のみ）
    seen_paths = set()
    unique_links = []
    for link in valid_links:
        path = urlparse(link['href']).path.rstrip('/')
        if path not in seen_paths:
            seen_paths.add(path)
            unique_links.append(link)
    
    subpage_data = []
    for link in unique_links[:max_pages]:
        try:
            sub_page = await self.browser.new_page()
            await sub_page.goto(link['href'], wait_until='domcontentloaded', timeout=15000)
            await sub_page.wait_for_timeout(1500)
            
            sub_text = await sub_page.inner_text('body')
            sub_html = await sub_page.content()
            sub_size = len(sub_html.encode('utf-8'))
            
            # コンテンツが極端に少ないページは除外（200文字未満はナビのみのページと判断）
            if len(sub_text.strip()) < 200:
                await sub_page.close()
                continue
            
            subpage_data.append({
                'url': link['href'],
                'nav_label': link['text'],
                'text_content': sub_text[:3000],
                'page_size_bytes': sub_size,
            })
            await sub_page.close()
        except Exception as e:
            print(f"[Browser] サブページ収集スキップ: {link['href']} ({e})")
    
    return subpage_data
```

---

## 確認用テストコマンド

```bash
cd ~/Projects/web-analyst-os

# Fix 1確認: atelier-a3で「再判定」が出なくなること
python main.py https://atelier-a3.jp --site-type portfolio --crawl-subpages 2>&1 | grep -i "再判定"
# 出力ゼロになることを確認

# Fix 2確認: byheartでP3にスコアのみ項目が出ないこと
python main.py https://www.byheart.jp/ > /tmp/byheart_v13.md
grep "スコア.*次スプリント" /tmp/byheart_v13.md
# 出力ゼロになることを確認

# Fix 3確認: sunphotoで正しいサブページが収集されること
python main.py https://sunphototakahashi.com/ --crawl-subpages
# 「収集サブページ」行に /gallery/ /fee/ /service/ 等が表示されること
# 同一ドメイン重複がないこと
```

---

## バージョン管理とリリース

```bash
git add -A
git commit -m "v1.3: skeptical self-correction cleanup, P3 quality filter, subpage dedup"
git push origin main
```

---

## v1.3完了後の宣言

上記3点の修正完了をもって **Web Analyst OS v1.3 を商用リリース版とする。**

以降の改善はユーザーフィードバックに基づく個別対応とし、
機能追加・大規模改修は v2.0 以降として切り離すこと。
