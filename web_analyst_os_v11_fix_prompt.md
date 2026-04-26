# Web Analyst OS v1.1 — 改善指示プロンプト
作成日: 2026-04-26  
対象ディレクトリ: `~/Projects/web-analyst-os`

以下の6つの修正を順番に実施してください。修正後、各修正が機能しているかをコードレビューで確認してから次へ進んでください。

---

## Fix 1: `--site-type` CLIオプションの追加（評価軸キャリブレーション）

### 背景
現状のOSはコンバージョン最適化を前提とした単一フレームで全サイトを評価している。高単価コンサルティング（選別型）・アートポートフォリオ・ブランドサイトに対して、トランザクション型と同じ評価軸を適用すると、設計意図と乖離した低スコアが出る。

### 修正内容

**`interface/cli.py`** にCLI引数を追加：

```python
parser.add_argument(
    "--site-type",
    choices=["transactional", "brand", "portfolio", "consulting"],
    default="transactional",
    help=(
        "サイトのビジネスモデルタイプ。"
        "transactional: 流入型BtoB/BtoC（デフォルト）"
        "brand: ブランディング・認知目的"
        "portfolio: 作品集・実績提示目的"
        "consulting: 高単価・選別型・要問合せ"
    )
)
```

**`core/state.py`** の `AnalystState` に追加：
```python
site_type: str  # transactional / brand / portfolio / consulting
```

**`analyst_config.yaml`** に `site_type_profiles` セクションを追加：

```yaml
site_type_profiles:
  transactional:
    score_weights:
      conversion: 30
      ux: 25
      brand_copy: 20
      technical: 15
      competitive: 10
    pricing_disclosure_required: true
    cta_density_target: high
    trust_signal_weight: high

  consulting:
    score_weights:
      conversion: 20
      ux: 20
      brand_copy: 25
      technical: 15
      competitive: 20
    pricing_disclosure_required: false  # 選別型は非掲載が業界慣行
    cta_density_target: low
    trust_signal_weight: very_high  # 代わりに実績・経歴が重要

  brand:
    score_weights:
      conversion: 15
      ux: 25
      brand_copy: 30
      technical: 15
      competitive: 15
    pricing_disclosure_required: false
    cta_density_target: low
    trust_signal_weight: medium

  portfolio:
    score_weights:
      conversion: 10
      ux: 20
      brand_copy: 25
      technical: 20
      competitive: 25
    pricing_disclosure_required: false
    cta_density_target: low
    trust_signal_weight: low
```

**`core/scorer.py`** で `site_type_profiles` から重みを動的に読み込む。現状のハードコードされた `weights` 辞書を削除し、`state["site_type"]` に基づいてプロファイルを選択する。

**各agentのシステムプロンプト**（`agents/*.py`）に `site_type` を渡す。各エージェントはシステムプロンプト末尾に以下のコンテキストを受け取る形にする：

```python
site_type_context = {
    "transactional": "このサイトはBtoB/BtoCの流入・問合せ獲得を主目的とする。価格透明性・CTAの明確さ・社会的証明を重視して評価せよ。",
    "consulting": "このサイトは高単価・選別型のコンサルティングサービスを扱う。価格非掲載は業界慣行であり減点しない。代わりに、経歴の具体性・実績の信頼性・差別化ポジショニングを重点的に評価せよ。",
    "brand": "このサイトはブランディング・認知形成を主目的とする。直接的なコンバージョン導線の欠如は必ずしも欠点ではない。ブランドボイスの一貫性・世界観の伝達力を重視して評価せよ。",
    "portfolio": "このサイトは作品・実績の提示を主目的とする。視覚的な強さ・作品の見やすさ・クリエイターとしての差別化を重視し、コンバージョン最適化は副次的に評価せよ。",
}
```

**使用例：**
```bash
python main.py https://scaryhippo.jp --site-type consulting
python main.py https://atelier-a3.jp --site-type portfolio
python main.py https://byheart.jp  # デフォルト: transactional
```

---

## Fix 2: P1項目数の上限キャップ（最大5件）

### 背景
atelier-a3.jpのP1が17件以上あり、「今すぐ対処」の優先度機能が失われている。

### 修正内容

**`core/report.py`** の P1 セクション生成ロジックを修正する。

現状の処理の後に以下のフィルタを追加する：

```python
P1_MAX = 5  # P1の最大件数

def cap_p1_items(p1_items: list, p2_items: list) -> tuple[list, list]:
    """
    P1をP1_MAX件に絞る。超過分はP2の先頭に移動する。
    インパクトスコア（各推奨内に含まれるスコア数値）が低いものを優先的にP2へ降格。
    スコアが取れない場合は後ろから削る。
    """
    if len(p1_items) <= P1_MAX:
        return p1_items, p2_items
    
    # スコアが含まれる推奨（[スコア XX/100]形式）を後回しにし、
    # 具体的な改善提案（[agent_name]形式）を優先してP1に残す
    specific = [item for item in p1_items if not item.strip().startswith("- [スコア")]
    score_only = [item for item in p1_items if item.strip().startswith("- [スコア")]
    
    # 具体的提案をP1_MAX件に絞る（超過分をP2へ）
    p1_final = specific[:P1_MAX]
    overflow = specific[P1_MAX:] + score_only  # スコアのみ項目はP2へ
    
    p2_items = overflow + p2_items
    return p1_final, p2_items
```

この関数を `generate_report()` 内の P1/P2 リスト確定後、レポート文字列生成前に呼び出す。

---

## Fix 3: P2セクションの最低品質基準（スコアのみ項目の禁止）

### 背景
初回ランのP2がスコアと優先度ラベルの羅列だけになっていた（「競合ポジショニング — 次スプリントで対応推奨」のみ）。これはFix 2でスコアのみ項目をP2に降格させる場合にも再発する。

### 修正内容

**`core/report.py`** の P2 セクション生成に品質フィルタを追加する：

```python
def filter_p2_quality(p2_items: list) -> list:
    """
    P2からスコア羅列のみの項目（[スコア XX/100] ... — 次スプリントで対応推奨）を除去する。
    Fix 2でオーバーフローしたスコアのみ項目はここで捨てる。
    具体的な改善アクション（→ 以降の指示）を含む項目のみP2に残す。
    """
    filtered = []
    for item in p2_items:
        # 「→」を含む項目 = 具体的アクションあり → 残す
        if "→" in item:
            filtered.append(item)
        # [agent_name]形式で始まり内容がある項目 → 残す
        elif re.match(r"- \[(?!スコア)[^\]]+\]", item) and len(item) > 60:
            filtered.append(item)
        # それ以外（スコアのみ・短すぎる） → 破棄
    return filtered
```

---

## Fix 4: クロスエージェント重複推奨の除去

### 背景
conversion_architect・brand_copy_analyst・competitive_analystが同一の問題点（CTAなし・社会的証明なし等）を重複して出力する。

### 修正内容

**`core/report.py`** に重複検出関数を追加する。P1・P2の全アイテムを対象に、意味的類似度が高いペアを検出して後者を除去する。完全一致ではなく、キーワードベースの簡易重複検出で対応する：

```python
DEDUP_KEYWORDS = [
    ["CTA", "コンバージョン", "問い合わせ導線", "CTAが"],
    ["社会的証明", "トラスト", "信頼", "実績", "クライアント名"],
    ["価格", "料金", "価格帯", "費用"],
    ["ナビゲーション", "ナビ", "グローバルナビ"],
    ["モバイル", "タップ", "スマートフォン"],
    ["パンくず", "breadcrumb"],
    ["フォーカス", "キーボードナビ", "focus-visible"],
]

def dedup_recommendations(items: list) -> list:
    """
    同一キーワードグループに属するアイテムが複数ある場合、
    最初に出現したもの（通常最も詳細）のみを残す。
    """
    seen_groups = set()
    result = []
    for item in items:
        item_lower = item.lower()
        matched_group = None
        for i, keywords in enumerate(DEDUP_KEYWORDS):
            if sum(1 for kw in keywords if kw.lower() in item_lower) >= 2:
                matched_group = i
                break
        if matched_group is None or matched_group not in seen_groups:
            result.append(item)
            if matched_group is not None:
                seen_groups.add(matched_group)
    return result
```

`generate_report()` 内で P1・P2 リストそれぞれに `dedup_recommendations()` を適用する。適用タイミングはFix 2のキャップ処理の前。

---

## Fix 5: Technical P3ボイラープレート推奨の品質向上

### 背景
technical_auditorが「画像の遅延読み込みを実装してパフォーマンスを向上させることを検討してください」のような汎用アドバイスを出力している。

### 修正内容

**`agents/technical_auditor.py`** のシステムプロンプトに以下の制約を追加する（既存プロンプトの末尾に追記）：

```
【出力品質制約】
- 推奨事項は必ず当該サイトの実測データ（ページサイズ・TTFB・ロード時間）を根拠として引用すること。
  例: ✅「ページサイズ756.9KBはテキスト主体のサイトとして過大。画像をWebPに変換し300KB以下を目標にする」
  例: ❌「画像をWebPフォーマットで提供し、ページの読み込み速度を向上させることを検討する」
- 実測値が閾値内（ロード1000ms以下・TTFB200ms以下・サイズ500KB以下）の場合、その項目のP3推奨は出力しない。
  代わりに「強みと継承すべき点」に記載する。
- 「〜を検討してください」「〜することをお勧めします」という表現を禁止する。
  必ず「→ [具体的な実装方法]」の形式で断定的に記述すること。
- 全ての推奨が「href="#"」「遅延読み込み」「WebP」「構造化データ」のいずれかのみで構成される場合、
  サイトのHTMLソースからより具体的な問題点を追加で特定して補足すること。
```

---

## Fix 6: エグゼクティブサマリーのヘッダー統一

### 背景
atelier-a3では「## エグゼクティブサマリー」の直後に「## 分析要約」、byheart では「## Web分析サマリー」という二重ヘッダーが出力されている。

### 修正内容

**`core/report.py`** のレポートテンプレート内、エグゼクティブサマリーセクションを以下に固定する：

```python
report_sections = [
    f"## エグゼクティブサマリー\n\n{state['executive_summary']}",
    ...
]
```

各エージェント（特にconversion_architect・competitive_analyst）のシステムプロンプトで、エグゼクティブサマリーの生成を求める部分に以下の制約を追加：

```
エグゼクティブサマリーを生成する場合、セクションタイトルを出力に含めないこと。
タイトル（「## 分析要約」「## Web分析サマリー」等）は呼び出し側が付与するため、
本文（サマリーテキスト）のみを返すこと。
```

**`core/report.py`** の `executive_summary` 組み立て時に、余分なヘッダーを除去するクリーニング処理を追加：

```python
def clean_executive_summary(text: str) -> str:
    """先頭のmarkdownヘッダー行（## で始まる行）を除去する"""
    lines = text.strip().split("\n")
    # 先頭から ## で始まる行をスキップ
    while lines and lines[0].strip().startswith("#"):
        lines.pop(0)
    return "\n".join(lines).strip()
```

---

## 実施順序と確認方法

1. Fix 6（最小変更・ヘッダー修正）→ 既存サイトで`python main.py https://scaryhippo.jp`実行してヘッダーを目視確認
2. Fix 3（P2品質フィルタ）→ Fix 4（重複除去）→ Fix 2（P1キャップ）の順に実装・テスト
3. Fix 5（技術推奨品質向上）→ byheart.jp（756.9KB）で確認。実測値引用があるか確認
4. Fix 1（--site-type）→ 最後に実装。`--site-type consulting` で scaryhippo.jp を再実行し、価格非掲載への減点がなくなることを確認

---

## 確認用テストコマンド

```bash
cd ~/Projects/web-analyst-os

# Fix 1確認: consultingモードでscaryhippo.jp
python main.py https://scaryhippo.jp --site-type consulting

# P1キャップ確認: atelier-a3.jp（P1が5件以下になるはず）
python main.py https://atelier-a3.jp --site-type portfolio

# 技術P3確認: byheart.jp（実測値引用があるはず）
python main.py https://www.byheart.jp/

# 重複確認: レポート内で「CTAがない」指摘が1回のみになっているか確認
python main.py https://atelier-a3.jp --site-type portfolio | grep -c "CTA"
```

---

## バージョン管理

修正完了後：
```bash
git add -A
git commit -m "v1.1: P1 cap, dedup, site-type calibration, quality filters"
git push origin main
```

以上。
