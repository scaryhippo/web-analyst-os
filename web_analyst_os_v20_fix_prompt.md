# Web Analyst OS v2.0 — Phase 0.5・CLI改善・スコア安定化
作成日: 2026-04-27  
対象ディレクトリ: `~/Projects/web-analyst-os`

## 実装スコープ

以下4点を1セットとして実装する。いずれも「分析前の前処理フェーズ」に属する変更であり、
既存のPhase 1〜4（専門家エージェント群）には手を加えない。

| Fix | 内容 | 対象ファイル |
|---|---|---|
| A | Phase 0.5：サイトタイプ自動分類エージェント | `agents/site_classifier.py`（新規）、`core/graph.py`、`core/state.py` |
| B | --crawl-subpages デフォルトON化 / --no-subpages オプト追加 | `main.py` |
| C | --context フリーテキストオプション | `main.py`、全エージェント |
| D | スコア数値アンカーの追加 | 全エージェントのシステムプロンプト |

---

## Fix A：Phase 0.5 サイトタイプ自動分類エージェント

### 概要

Phase 0（ブラウザ収集）の直後、Phase 1（専門家エージェント並列実行）の直前に
新規エージェントを挿入する。このエージェントは収集済みのページテキスト・URL・
ナビ構造を読んでサイトタイプを自動判定し、`state["site_type"]` を設定する。

`--site-type` フラグが明示的に渡された場合はこのエージェントをスキップし、
フラグの値を直接使用する（明示 > 自動判定）。

---

### 対象ファイル1：`agents/site_classifier.py`（新規作成）

```python
CLASSIFIER_SYSTEM_PROMPT = """
あなたはWebサイトのビジネスタイプを分類する専門家です。
収集したサイトデータを分析し、以下の4タイプのうち最も適切なものを判定してください。

## サイトタイプ定義

**transactional（流入型・予約/購買型）**
特徴：料金表・予約フォーム・サービスメニュー・営業時間・所在地情報が存在する。
訪問者に即座の行動（予約・購入・来店）を求める設計。
例：写真スタジオ、飲食店、美容院、地域サービス、ECサイト
シグナル：price / fee / 料金 / 予約 / booking / 営業時間 / アクセス

**consulting（高単価・選別型）**
特徴：ケーススタディ・「要問い合わせ」型エンゲージメント・創業者の経歴・
資格情報が前面に出る。価格は非公開またはプロジェクト単位。
例：戦略コンサル、経営顧問、弁護士、独立系ブティック
シグナル：case study / 実績 / 経歴 / selected / boutique / セッション / 顧問

**portfolio（作品集・実績提示型）**
特徴：ギャラリー・作品一覧が主軸。料金情報は副次的または皆無。
視覚的訴求が中心で、直接的な購買よりも依頼検討を促す設計。
例：フォトグラファー、グラフィックデザイナー、建築家
シグナル：works / gallery / portfolio / 作品 / 制作実績

**brand（コーポレートブランド型）**
特徴：企業紹介・ニュース・採用・IR中心。直接的な購買・予約導線がない。
例：大企業のコーポレートサイト、スタートアップの会社紹介
シグナル：about / company / news / investor / recruit / IR / 会社概要

## 出力形式

以下のJSONを厳密に出力すること。JSON以外のテキストを含めないこと。

{
  "site_type": "transactional | consulting | portfolio | brand のいずれか1つ",
  "confidence": "high | medium | low のいずれか1つ",
  "primary_signals": ["判定根拠となったシグナルを3点以内で列挙"],
  "reasoning": "判定理由を2文以内で述べる。サイトの特徴と選んだタイプの対応を明記する。"
}

## 判定ルール

- 複数タイプの特徴を持つ場合は、訪問者に求める主要アクションが何かで判定する
  （例：料金ページ+予約フォームがあればtransactional、たとえギャラリーがあっても）
- 判定が困難な場合は confidence: low として transactional をデフォルトとする
- ECサイト（カート機能あり）は transactional とする
- GovTechのように B2G で人的コンサルが主体ならconsultingとする
"""

async def classify_site_type(state: dict, llm) -> dict:
    """
    Phase 0.5: ページテキストとメタ情報からサイトタイプを自動判定する。
    --site-type が明示されている場合は呼ばれない。
    """
    import json
    
    page_text = state.get("page_text_content", "")[:3000]
    url = state.get("url", "")
    title = state.get("page_title", "")
    meta_desc = state.get("meta_description", "")
    nav_labels = [
        sp.get("nav_label", "") for sp in state.get("subpages", [])
    ]
    
    user_message = f"""
URL: {url}
ページタイトル: {title}
meta description: {meta_desc}
ナビゲーションラベル: {', '.join(nav_labels)}

ページ本文（先頭3,000文字）:
{page_text}
"""
    
    response = await llm.ainvoke([
        {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
        {"role": "user",   "content": user_message},
    ])
    
    try:
        result = json.loads(response.content)
        return {
            "site_type":            result.get("site_type", "transactional"),
            "site_type_confidence": result.get("confidence", "low"),
            "site_type_signals":    result.get("primary_signals", []),
            "site_type_reasoning":  result.get("reasoning", ""),
        }
    except (json.JSONDecodeError, AttributeError):
        # パース失敗時はデフォルトにフォールバック
        return {
            "site_type":            "transactional",
            "site_type_confidence": "low",
            "site_type_signals":    [],
            "site_type_reasoning":  "自動判定に失敗したためデフォルト(transactional)を使用",
        }
```

---

### 対象ファイル2：`core/state.py`

`AnalystState` TypedDict に以下を追加する：

```python
site_type_confidence: str   # "high" | "medium" | "low" | "explicit"
site_type_signals:    list  # 自動判定の根拠シグナル（明示指定時は空リスト）
site_type_reasoning:  str   # 自動判定の理由（明示指定時は空文字）
context:              str   # --context オプションの値（空の場合は ""）
```

`main.py` の `build_initial_state()` にも初期値を追加する：

```python
"site_type_confidence": "explicit" if args.site_type else "",
"site_type_signals":    [],
"site_type_reasoning":  "",
"context":              args.context if hasattr(args, "context") else "",
```

---

### 対象ファイル3：`core/graph.py`

Phase 0（ブラウザ収集）の直後に Phase 0.5 を挿入する。

```python
from agents.site_classifier import classify_site_type

# Phase 0 完了後、Phase 1 実行前
if not state.get("site_type"):
    # --site-type 未指定の場合のみ自動判定
    classifier_result = await classify_site_type(state, llm)
    state.update(classifier_result)
    print(f"[Phase 0.5] サイトタイプ自動判定: {state['site_type']} "
          f"（確信度: {state['site_type_confidence']}）")
    print(f"           根拠: {', '.join(state['site_type_signals'])}")
else:
    # --site-type 明示指定
    state["site_type_confidence"] = "explicit"
    print(f"[Phase 0.5] サイトタイプ明示指定: {state['site_type']}")
```

---

### 対象ファイル4：`core/report.py`（レポートヘッダーへの判定情報追加）

レポート冒頭の「サイトタイプ」行を以下のように拡張する：

```python
# 自動判定の場合は確信度と根拠を付記
if state.get("site_type_confidence") == "explicit":
    site_type_line = f"サイトタイプ: {state['site_type']}（明示指定）"
elif state.get("site_type_confidence") == "high":
    site_type_line = f"サイトタイプ: {state['site_type']}（自動判定・確信度：高）"
elif state.get("site_type_confidence") == "medium":
    site_type_line = (
        f"サイトタイプ: {state['site_type']}（自動判定・確信度：中 "
        f"— 異なる場合は --site-type で上書き可能）"
    )
else:  # low
    site_type_line = (
        f"サイトタイプ: {state['site_type']}（自動判定・確信度：低 "
        f"— --site-type で上書きを推奨）"
    )
```

---

## Fix B：--crawl-subpages デフォルトON / --no-subpages 追加

### 対象ファイル：`main.py`

#### 変更前（現状）

```python
parser.add_argument(
    "--crawl-subpages",
    action="store_true",
    default=False,
    help="サブページを収集して分析精度を高める",
)
```

#### 変更後

```python
# --crawl-subpages を廃止し、--no-subpages をオプトアウト用に追加
parser.add_argument(
    "--no-subpages",
    action="store_true",
    default=False,
    help="サブページ収集を無効化する（デフォルトは収集あり）",
)
```

`build_initial_state()` または収集処理内での使用箇所も対応して変更する：

```python
# 変更前
crawl_subpages = args.crawl_subpages

# 変更後
crawl_subpages = not args.no_subpages
```

**注意**：既存のテストスクリプト・README等に `--crawl-subpages` の記述がある場合は
あわせて更新すること。

---

## Fix C：--context フリーテキストオプション

### 対象ファイル1：`main.py`

```python
parser.add_argument(
    "--context",
    type=str,
    default="",
    help="分析コンテキストを自由テキストで補足する（例：'家族向け写真スタジオ。30代子育て世帯が主客層。'）",
)
```

### 対象ファイル2：全エージェント（`agents/*.py`）

全エージェントのシステムプロンプト生成処理の先頭に、以下のコンテキスト注入を追加する。
関数名・実装パターンは各エージェントの構造に合わせて読み替えること。

```python
def build_system_prompt(state: dict, base_prompt: str) -> str:
    """
    コンテキスト情報をシステムプロンプトの先頭に注入する。
    --context が空の場合は何も追加しない。
    """
    context = state.get("context", "").strip()
    if not context:
        return base_prompt
    
    context_block = f"""【分析コンテキスト（依頼者提供情報）】
{context}

上記のコンテキストを踏まえて分析を行うこと。
競合設定・ターゲット顧客・地域性・ビジネスモデルに関する言及がある場合は、
スコアリングと改善提案の優先度に反映させること。

---

"""
    return context_block + base_prompt
```

`build_system_prompt()` を各エージェントのLLM呼び出し直前に適用する：

```python
# 例（各エージェントの呼び出し部分）
system_prompt = build_system_prompt(state, AGENT_SYSTEM_PROMPT)
response = await llm.ainvoke([
    {"role": "system", "content": system_prompt},
    {"role": "user",   "content": user_message},
])
```

---

## Fix D：スコア数値アンカーの追加

LLM揺れを抑制するため、各エージェントのシステムプロンプトに採点基準を追加する。
既存プロンプトの末尾（出力形式指定の直前）に挿入すること。

### technical_auditor（実測値に基づく基準が最も重要）

```
【技術スコア採点基準（実測値に基づく数値アンカー）】
以下の基準に従って技術スコアを算出すること。
複数条件が当てはまる場合は加算/減算で調整する。

ベーススコア（ページロード時間）:
- < 500ms                  → ベース 85点
- 500ms 〜 1,000ms         → ベース 65点
- 1,000ms 〜 2,000ms       → ベース 45点
- > 2,000ms                → ベース 25点

補正（各項目につき ±5点）:
- TTFB < 100ms             → +5点
- TTFB 100ms 〜 300ms      → ±0点
- TTFB > 300ms             → -5点
- HTTPS有効                → +5点
- モバイルviewport適切設定  → +5点
- meta description適切設定  → +3点
- 構造化データ実装あり      → +5点
- href="#" 多用（5件以上）  → -5点
- 画像altテキスト欠如       → -3点

上記の合計が技術スコアの基準値。100点上限・0点下限でクリップする。
この基準値から ±10点の範囲内でサイト全体の技術品質を加味して最終スコアを決定すること。
基準値から15点以上乖離する場合は、その理由をP1/P2/P3の指摘内に明記すること。
```

### conversion_architect / ux_auditor / brand_copy_analyst / competitive_analyst（共通アンカー）

各エージェントのプロンプト末尾に以下の共通基準を追加する：

```
【スコア採点の共通基準】
以下の基準を参考にスコアを決定すること。

80点以上: 競合と明確に差別化された強みを複数保有。
          このカテゴリにおける主要な改善項目が0〜1点のみ。
          訪問者の主要ゴール達成が阻害されていない。

60〜79点: 標準的な実装水準。改善余地はあるが致命的な欠如はない。
          P1指摘が1〜2点、P2指摘が複数点存在する状態。

40〜59点: 複数の重要要素が欠如またはミスマッチ。
          P1指摘が3点以上あり、コンバージョン/UX/ブランド/競合優位性に
          直接影響する問題が存在する。

40点未満: 商用サイトとして機能する最低要件を満たしていない。
          訪問者がサイトの目的・行動手順を把握できない致命的な状態。

【スコアの安定性について】
同一サイトを再分析した際に ±10点以内に収まることを意識すること。
根拠のない極端なスコア（90点以上 / 30点以下）を付ける場合は、
その具体的な根拠をP1または強みセクションに明記すること。
```

---

## 確認用テストコマンド

```bash
cd ~/Projects/web-analyst-os

# Fix A の確認：自動判定が機能していること
# （--site-type フラグなしで実行）
python main.py https://www.scaryhippo.jp > /tmp/scaryhippo_v20.md
# ヘッダーに「サイトタイプ: consulting（自動判定・確信度：高）」が出ること
head -10 /tmp/scaryhippo_v20.md

python main.py https://sunphototakahashi.com > /tmp/sunphoto_v20.md
# ヘッダーに「サイトタイプ: transactional（自動判定・確信度：高）」が出ること
head -10 /tmp/sunphoto_v20.md

python main.py https://atelier-a3.jp > /tmp/a3_v20.md
# ヘッダーに「サイトタイプ: portfolio（自動判定・確信度：高）」が出ること
head -10 /tmp/a3_v20.md

# Fix A の確認：明示指定が自動判定を上書きすること
python main.py https://www.scaryhippo.jp --site-type portfolio > /tmp/test_override.md
head -10 /tmp/test_override.md
# 「サイトタイプ: portfolio（明示指定）」が出ること

# Fix B の確認：デフォルトでサブページが収集されること
python main.py https://sunphototakahashi.com > /tmp/sunphoto_default_crawl.md
grep "収集サブページ" /tmp/sunphoto_default_crawl.md
# サービス内容|撮影料金|ギャラリー 等が出ること（フラグなしで）

# Fix B の確認：--no-subpages が機能すること
python main.py https://sunphototakahashi.com --no-subpages > /tmp/sunphoto_no_subpages.md
grep "収集サブページ" /tmp/sunphoto_no_subpages.md
# 出力なしまたは「なし」であること

# Fix C の確認：--context が分析に反映されること
python main.py https://sunphototakahashi.com \
  --context "三田市の家族写真専門スタジオ。主客層は30代子育て世帯。\
近隣に個人経営の競合が3店舗。日曜定休が最大の差別化阻害要因。" \
  > /tmp/sunphoto_with_context.md
# レポート内に「三田市」「子育て」「定休」への言及が増えていることを確認
grep -i "三田\|子育\|定休" /tmp/sunphoto_with_context.md

# Fix D の確認：スコア安定性のチェック（同一サイトを2回実行して比較）
python main.py https://qoollc.co.jp/ > /tmp/qoo_run1.md
python main.py https://qoollc.co.jp/ > /tmp/qoo_run2.md
grep "技術・パフォーマンス" /tmp/qoo_run1.md /tmp/qoo_run2.md
# 2回の技術スコアが ±10点以内であることを確認

# 全体回帰テスト
python main.py https://www.scaryhippo.jp \
  --competitor-url https://qoollc.co.jp/ \
  > /tmp/competitive_v20.md
# 競合比較セクションが正常に出力されることを確認
```

---

## 確認の判定基準

| 確認項目 | 合格基準 |
|---|---|
| scaryhippo 自動判定 | consulting（確信度：高）と判定される |
| sunphoto 自動判定 | transactional（確信度：高）と判定される |
| atelier-a3 自動判定 | portfolio（確信度：高）と判定される |
| 明示指定の優先 | --site-type 指定が自動判定を上書きする |
| デフォルトサブページ収集 | フラグなしでサブページが収集される |
| --no-subpages | サブページが収集されない |
| --context 反映 | コンテキストの内容が指摘に反映される |
| 技術スコア安定性 | qoo の技術スコアが2回実行で ±10点以内 |
| 競合比較回帰 | 競合比較セクションが正常出力される |

---

## バージョン管理

```bash
git add -A
git commit -m "v2.0: Phase 0.5 site-type auto-classifier, crawl-subpages default ON, --context option, score anchors"
git push origin main
```
