# Web Analyst OS v1.5 — 競合比較充実・P3称賛分離・重複排除強化
作成日: 2026-04-27  
対象ディレクトリ: `~/Projects/web-analyst-os`

## 背景・目的

scaryhippo.jp × qoollc.co.jp の競合比較テストで以下の問題が発覚した：

1. **競合比較セクションが空洞**：`--competitor-url` 指定時にレポートの競合比較欄が
   「（詳細な差分はCompetitive Positioning Analystのスコアに反映されています）」
   の1行のみで、スコア比較表も戦略的示唆もゼロ。商用提示に耐えない。

2. **P3に称賛観察が混在**：「ロード時間693ms、TTFB 8msは非常に優れている」等、
   改善アクションではなく称賛の観察が `→` 付きでP3に残り、
   強みセクションに入るべき内容が誤分類されている。

3. **英日混在の指摘が同一レポート内で4回重複**：`DEDUP_TOPIC_GROUPS` が
   「英語・日本語の混在トーン」を単一トピックとして認識できていない。

---

## Fix A：競合比較セクションの充実（最重要）

### 対象ファイル1：`agents/competitive_analyst.py`

競合比較モード（`state.get("competitor_url")` が存在する場合）のシステムプロンプト末尾に
以下の指示を追加する：

```
【競合比較モード時の追加出力】
competitor_url が state に存在する場合、通常の分析出力の末尾に
以下の XML タグで囲まれた競合比較サマリーを必ず出力すること。

<competitive_summary>
自社優位軸:
- [評価軸名]: [1文で根拠を示す。例：「技術・パフォーマンス: ロード432ms vs 競合693msで1.6倍高速」]
- ...（最大3点、具体的なデータまたはコピー・機能の差を根拠として示すこと）

競合優位軸:
- [評価軸名]: [1文で根拠を示す。例：「社会的証明: QooScore導入企業数・自治体名の公開実績あり」]
- ...（最大3点、同様に根拠必須）

戦略的示唆:
[2〜3文で「自社が取るべき差別化アクション」を具体的に述べること。
 競合が強い軸で真っ向勝負せず、自社優位軸をどう活かすかの方向性を示す。]
</competitive_summary>

注意：
- 推測ではなく収集したサイトデータに基づいて記述すること
- スコアの数値差だけでなく、コンテンツ・機能・コピーの差を根拠として使うこと
- 「総じて」「概して」等の抽象表現は使わないこと
```

### 対象ファイル2：`core/report.py`

#### 追加関数1：competitive_summary の抽出

```python
import re

def extract_competitive_summary(competitive_analysis: str) -> str:
    """
    competitive_analyst の出力から <competitive_summary> タグの内容を抽出する。
    タグが存在しない場合は空文字を返す。
    """
    match = re.search(
        r'<competitive_summary>(.*?)</competitive_summary>',
        competitive_analysis,
        re.DOTALL
    )
    if match:
        return match.group(1).strip()
    return ""
```

#### 追加関数2：スコア比較テーブルの生成

```python
def generate_score_comparison_table(
    self_scores: dict,
    competitor_scores: dict,
    competitor_title: str = "競合サイト"
) -> str:
    """
    自社と競合のスコアを横並びで比較するMarkdownテーブルを生成する。
    """
    AXES = [
        ("conversion", "コンバージョン設計"),
        ("ux",         "UX・使いやすさ"),
        ("brand",      "ブランド・コピー"),
        ("technical",  "技術・パフォーマンス"),
        ("competitive","競合ポジショニング"),
    ]
    
    lines = [
        "### スコア比較\n",
        f"| 評価軸 | 自社 | {competitor_title} | 差分 |",
        "|---|---|---|---|",
    ]
    
    total_self = 0
    total_comp = 0
    
    for key, label in AXES:
        s = self_scores.get(key, 0)
        c = competitor_scores.get(key, 0)
        diff = s - c
        diff_str = f"**+{diff}**" if diff > 0 else (f"**{diff}**" if diff < 0 else "±0")
        lines.append(f"| {label} | {s}/100 | {c}/100 | {diff_str} |")
        total_self += s
        total_comp += c
    
    avg_s = total_self // len(AXES)
    avg_c = total_comp // len(AXES)
    diff_total = avg_s - avg_c
    diff_str = f"**+{diff_total}**" if diff_total > 0 else (f"**{diff_total}**" if diff_total < 0 else "±0")
    lines.append(f"| **総合** | **{avg_s}/100** | **{avg_c}/100** | {diff_str} |")
    
    return "\n".join(lines)
```

#### 競合比較セクションの組み立て修正

`generate_report()` 内の競合比較セクション生成箇所を探し、現状の
「（詳細な差分はCompetitive Positioning Analystのスコアに反映されています）」
を以下に置き換える：

```python
# 競合比較セクション（competitor_url が存在する場合のみ出力）
competitor_url = state.get("competitor_url", "")
if competitor_url:
    competitor_title = state.get("competitor_title", "競合サイト")
    
    sections.append("## 競合比較\n")
    sections.append(f"競合 URL: {competitor_url}")
    sections.append(f"競合サイトタイトル: {competitor_title}\n")
    
    # スコア比較テーブル（competitor_scores が state に存在する場合）
    competitor_scores = state.get("competitor_scores", {})
    self_scores = state.get("scores", {})
    if competitor_scores and self_scores:
        sections.append(generate_score_comparison_table(
            self_scores, competitor_scores, competitor_title
        ))
        sections.append("")
    
    # 競合比較サマリー（competitive_analyst の出力から抽出）
    competitive_analysis = state.get("competitive_analysis", "")
    competitive_summary = extract_competitive_summary(competitive_analysis)
    if competitive_summary:
        sections.append("### 競合比較分析\n")
        sections.append(competitive_summary)
    else:
        sections.append("_競合比較データを取得できませんでした。competitive_analyst の出力を確認してください。_")
```

**注意**：`state["competitor_scores"]` と `state["scores"]` のキー名は
実装のスコア格納方法に合わせて適宜読み替えること。
スコアが辞書形式でない場合（例：`state["conversion_score"]` のようにフラットな場合）は
`self_scores` の組み立て部分を対応するキーで構成する。

---

## Fix B：P3称賛アイテムの自動検出と強みセクションへの分離

### 対象ファイル：`core/report.py`

#### 追加関数：称賛アイテムの検出

```python
def is_positive_observation(item: str) -> bool:
    """
    P3 アイテムの中で「改善アクション」ではなく「称賛観察」を検出する。
    対象：「→ 〇〇は非常に優れている」「→ 適切に設定されている」のような
    現状肯定文が矢印の後に来るパターン。
    """
    POSITIVE_PATTERNS = [
        r'は非常に優れ',
        r'は優れ(た|てい)',
        r'は良好',
        r'は適切に設定',
        r'は正しく実装',
        r'は十分',
        r'は高水準',
        r'は優秀',
        r'問題はない',
        r'に問題が?な[いく]',
        r'は許容範囲',
        r'は優位',
        r'非常に高速',
    ]
    
    if '→' not in item:
        return False
    
    after_arrow = item.split('→', 1)[1]
    for pattern in POSITIVE_PATTERNS:
        if re.search(pattern, after_arrow):
            return True
    return False
```

#### `filter_section_quality()` の修正

既存の `filter_section_quality()` を以下に置き換える：

```python
def filter_section_quality(items: list) -> tuple[list, list]:
    """
    スコアのみの項目を除去し、称賛観察を強みセクション用に分離する。
    
    Returns:
        (改善推奨アイテムリスト, 強みとして追加すべきアイテムリスト)
    """
    filtered = []
    praise_items = []
    
    for item in items:
        # 称賛観察を検出して強みリストへ
        if is_positive_observation(item):
            praise_items.append(item)
            continue
        
        # 具体的アクション（→）を含む → 残す
        if "→" in item:
            filtered.append(item)
            continue
        
        # [agent_name] 形式で始まり、60文字超 → 残す
        if re.match(r"- \[(?!スコア)[^\]]+\]", item) and len(item) > 60:
            filtered.append(item)
            continue
        
        # それ以外（スコアのみ・短すぎる） → 破棄
    
    return filtered, praise_items
```

#### `generate_report()` での適用

P2・P3のフィルタリング後、称賛アイテムを強みセクションに追加する：

```python
# P2・P3フィルタリング
p2_items, p2_praise = filter_section_quality(p2_items)
p3_items, p3_praise = filter_section_quality(p3_items)

# 称賛アイテムを強みセクションに追記
auto_strengths = p2_praise + p3_praise
# strengths_items（強みと継承すべき点）の末尾に追加
strengths_items.extend(auto_strengths)
```

**注意**：既存コードが `filter_section_quality()` の戻り値を1つの値として受けている場合、
呼び出し側を `filtered, praise = filter_section_quality(...)` に変更すること。

---

## Fix C：DEDUP_TOPIC_GROUPSの拡充

### 対象ファイル：`core/report.py`（または `DEDUP_TOPIC_GROUPS` が定義されているファイル）

`DEDUP_TOPIC_GROUPS` リストに以下のグループを追加する：

```python
# 既存の DEDUP_TOPIC_GROUPS に追加
DEDUP_TOPIC_GROUPS = [
    # --- 既存グループはそのまま維持 ---
    
    # 新規追加グループ
    {
        "name": "英日混在トーン",
        "keywords": ["英日混在", "英語・日本語", "言語統一", "トーン統一",
                     "英語混在", "バイリンガル", "英語主体", "日本語主体"],
    },
    {
        "name": "ナビゲーション不在",
        "keywords": ["グローバルナビ", "ナビゲーションが", "固定ヘッダー", 
                     "スティッキー", "ナビがない"],
    },
    {
        "name": "フォーム設計",
        "keywords": ["フォームバリデーション", "インラインバリデーション",
                     "送信後", "サンクスページ", "フォーム摩擦", "入力ガイダンス"],
    },
    {
        "name": "セキュリティ認証",
        "keywords": ["ISO27001", "ISMS", "第三者認証", "セキュリティ認証", 
                     "第三者監査"],
    },
    {
        "name": "定休日例外",
        "keywords": ["定休日", "日曜・祝日", "日祝", "要予約で承"],
    },
]
```

**適用対象**：P1・P2・P3のクロス優先重複排除（`build_prioritized_items()` 内）に
既存グループと同様に組み込むこと。グループ内キーワードが1つでも一致すれば同一トピックと判定する
（既存の閾値 threshold=1 を維持）。

---

## 確認用テストコマンド

```bash
cd ~/Projects/web-analyst-os

# Fix A の確認：競合比較セクションに内容が出力されること
python main.py https://www.scaryhippo.jp \
  --competitor-url https://qoollc.co.jp/ \
  > /tmp/scaryhippo_vs_qoo_v15.md

# 確認ポイント：
# - "### スコア比較" テーブルが出力されること
# - "### 競合比較分析" セクションに自社優位軸・競合優位軸・戦略的示唆が出力されること
grep -A 20 "## 競合比較" /tmp/scaryhippo_vs_qoo_v15.md

# Fix B の確認：P3にポジティブ観察が残らないこと
python main.py https://qoollc.co.jp/ > /tmp/qoo_v15.md
grep -E "非常に優れ|適切に設定|正しく実装" /tmp/qoo_v15.md
# P3セクション内に上記パターンがないことを確認
# 強みセクションに移動されていることを確認

# Fix C の確認：英日混在の指摘が1件に統合されること
python main.py https://www.scaryhippo.jp > /tmp/scaryhippo_v15.md
grep -c "英日混在\|英語.*日本語.*混在\|言語統一" /tmp/scaryhippo_v15.md
# 出力が2以下（P1かP2に1件 + P3に0件）であることを確認

# 回帰テスト：atelier-a3・sunphotoで既存品質の維持確認
python main.py https://atelier-a3.jp --site-type portfolio --crawl-subpages
python main.py https://sunphototakahashi.com/ --crawl-subpages
```

---

## 確認の判定基準

| 確認項目 | 合格基準 |
|---|---|
| 競合比較スコアテーブル | `## 競合比較` セクション内に4列テーブルが存在する |
| 競合比較サマリー | 自社優位軸・競合優位軸・戦略的示唆の3ブロックが存在する |
| P3称賛アイテム除去 | 「〇〇は非常に優れている」等がP3に出力されない |
| 強みセクション自動補完 | P3から分離した称賛アイテムが強みセクションに存在する |
| 英日混在重複排除 | 同一レポート内での英日混在言及が2件以下 |
| 回帰：atelier-a3 | v1.4と同等の品質・スコア（±5点以内） |

---

## バージョン管理

```bash
git add -A
git commit -m "v1.5: competitive summary section, P3 praise auto-separation, dedup group expansion"
git push origin main
```
