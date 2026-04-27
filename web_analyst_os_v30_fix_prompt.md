# Web Analyst OS v3.0 — 評価次元ベースアーキテクチャへの完全移行
作成日: 2026-04-27  
対象ディレクトリ: `~/Projects/web-analyst-os`

## 設計思想

現行のサイトタイプ分類（consulting / transactional / portfolio / brand）は
「タイプラベル → 評価ウェイト」という2段階構造のプロキシ設計だった。
これは新しいビジネス形態が出るたびにコード変更を要する本質的な欠陥を持つ。

v3.0では**このプロキシを廃止**し、分類器が評価ウェイト（=評価次元プロファイル）を
直接出力する設計に移行する。

```
[旧] サイトタイプラベル → analyst_config.yaml の固定プロファイル → エージェント
[新] 評価次元プロファイル（動的生成）→ エージェント（直接注入）
```

サイトタイプは「人間が読むためのラベル」として生成されるが、
採点・優先度判定・総合スコア計算には一切関与しない。

---

## 実装スコープ（7ファイル）

| 対象ファイル | 変更内容 |
|---|---|
| `analyst_config.yaml` | site_type_presets を評価次元プロファイルで再定義 |
| `agents/site_classifier.py` | ラベルではなく評価次元プロファイルを出力 |
| `core/state.py` | evaluation_profile フィールドを追加 |
| `core/graph.py` | プリセットロード or 分類器実行のロジック変更 |
| `main.py` | --site-type が評価次元プリセットをロードするよう変更 |
| `agents/*.py`（全5エージェント） | evaluation_profile を受け取り採点・優先度に反映 |
| `core/report.py` | site_type_label 表示・重み付き総合スコア計算 |

---

## Fix 1：評価次元の定義（設計基盤）

以下の10次元をシステム全体の共通評価軸とする。
すべての値は `0.1 〜 2.0` の範囲で表現し、`1.0` が「標準的な重要度」を意味する。

| 次元キー | 意味 | 低い例 | 高い例 |
|---|---|---|---|
| `price_disclosure_weight` | 価格・料金の透明性の重要度 | 指名買い型コンサル | 地域店舗・EC |
| `cta_immediacy_weight` | 即時コンバージョンの重要度 | 長期検討型B2B | EC・予約型 |
| `lead_qualification_weight` | リードの事前選別・スクリーニングの重要度 | 誰でも来訪OK | 選別型ブティック |
| `social_proof_weight` | 口コミ・実績・導入事例の重要度 | 個人ブログ | 高額サービス・SaaS |
| `credential_display_weight` | 資格・経歴・認証情報の重要度 | ECサイト | 専門家サービス・行政向け |
| `portfolio_display_weight` | 作品・ギャラリー・実績表示の重要度 | SaaS | 写真家・デザイナー |
| `navigation_depth_weight` | 深いナビゲーション構造の必要度 | 1プロダクトLP | 複合サービスサイト |
| `mobile_optimization_weight` | モバイル最適化の重要度 | 行政調達担当向け | 一般消費者向けEC |
| `competitive_diff_weight` | 競合との差別化訴求の重要度 | 独占的ニッチ | 競合多数の市場 |
| `trust_signal_weight` | セキュリティ・信頼性シグナルの重要度 | 情報サイト | 個人情報取得・決済系 |

---

## Fix 2：`analyst_config.yaml` — ナmedプリセットの再定義

既存の `site_type_profiles` セクションを以下で置き換える。
`--site-type` フラグで指定できる名前付きプリセットとして機能する。

```yaml
# analyst_config.yaml

evaluation_dimensions:
  - price_disclosure_weight
  - cta_immediacy_weight
  - lead_qualification_weight
  - social_proof_weight
  - credential_display_weight
  - portfolio_display_weight
  - navigation_depth_weight
  - mobile_optimization_weight
  - competitive_diff_weight
  - trust_signal_weight

site_type_presets:

  transactional:
    label: "流入型・即時コンバージョン型"
    profile:
      price_disclosure_weight:    1.8
      cta_immediacy_weight:       1.9
      lead_qualification_weight:  0.3
      social_proof_weight:        1.3
      credential_display_weight:  0.5
      portfolio_display_weight:   0.4
      navigation_depth_weight:    1.0
      mobile_optimization_weight: 1.6
      competitive_diff_weight:    1.0
      trust_signal_weight:        1.2

  consulting:
    label: "高単価・選別型コンサルティング"
    profile:
      price_disclosure_weight:    0.3
      cta_immediacy_weight:       0.4
      lead_qualification_weight:  1.9
      social_proof_weight:        1.9
      credential_display_weight:  1.9
      portfolio_display_weight:   0.4
      navigation_depth_weight:    0.8
      mobile_optimization_weight: 0.8
      competitive_diff_weight:    1.6
      trust_signal_weight:        1.8

  portfolio:
    label: "作品集・実績提示型"
    profile:
      price_disclosure_weight:    0.2
      cta_immediacy_weight:       0.6
      lead_qualification_weight:  0.5
      social_proof_weight:        1.1
      credential_display_weight:  0.7
      portfolio_display_weight:   2.0
      navigation_depth_weight:    0.7
      mobile_optimization_weight: 1.3
      competitive_diff_weight:    1.3
      trust_signal_weight:        0.7

  brand:
    label: "コーポレートブランド型"
    profile:
      price_disclosure_weight:    0.1
      cta_immediacy_weight:       0.5
      lead_qualification_weight:  0.3
      social_proof_weight:        1.4
      credential_display_weight:  0.9
      portfolio_display_weight:   0.3
      navigation_depth_weight:    1.3
      mobile_optimization_weight: 1.4
      competitive_diff_weight:    1.4
      trust_signal_weight:        1.2
```

---

## Fix 3：`agents/site_classifier.py` — プロファイル直接出力に変更

既存の `CLASSIFIER_SYSTEM_PROMPT` を以下で置き換える。

```python
CLASSIFIER_SYSTEM_PROMPT = """
あなたはWebサイトの評価プロファイルを生成する専門家です。
収集したサイトデータから、以下10次元の重要度スコアを出力してください。

## 10評価次元の定義

1. price_disclosure_weight（価格透明性の重要度）
   - 高い: 来訪者が価格を見て即決する類のサービス（地域店舗・EC・SaaS月額等）
   - 低い: 価格が案件単位/要相談が業界標準のサービス（戦略コンサル・法律・行政調達）

2. cta_immediacy_weight（即時コンバージョンの重要度）
   - 高い: 「今すぐ予約」「カートに入れる」が主目的
   - 低い: 長期検討・稟議・複数ステークホルダーを経て意思決定

3. lead_qualification_weight（リード選別の重要度）
   - 高い: ミスマッチな問い合わせを事前に排除したい高単価・限定受注型
   - 低い: 間口を広く取って量で勝負するビジネス

4. social_proof_weight（社会的証明の重要度）
   - 高い: 初回購買リスクが高く第三者評価が意思決定に必須
   - 低い: 指名・紹介・限定コミュニティ内でのみ流通するサービス

5. credential_display_weight（資格・経歴の重要度）
   - 高い: 専門家の質が直接アウトカムに影響する（医療・法律・戦略コンサル）
   - 低い: プロダクトの品質が人の資格より重要なEC・SaaS

6. portfolio_display_weight（作品・実績表示の重要度）
   - 高い: 仕上がりを見て依頼判断するクリエイティブ系
   - 低い: 作品概念のないサービス・プロダクト型

7. navigation_depth_weight（深いナビゲーションの必要度）
   - 高い: 複数サービス・複数ターゲットが存在する複合サイト
   - 低い: シングルプロダクト・シングルサービスのLP型

8. mobile_optimization_weight（モバイル最適化の重要度）
   - 高い: 一般消費者・外出先での購買判断が多い
   - 低い: PCで稟議書を開きながら比較検討する行政・大企業担当者向け

9. competitive_diff_weight（競合差別化の重要度）
   - 高い: 類似サービスが多く選定理由の明示が必須
   - 低い: カテゴリを独占する独自ニッチ・指名性の高いサービス

10. trust_signal_weight（セキュリティ・信頼シグナルの重要度）
    - 高い: 個人情報・機密情報・決済情報を取り扱う
    - 低い: 情報提供のみで個人情報不要

## 出力形式

以下のJSONを厳密に出力すること。JSON以外のテキストを含めないこと。
値はすべて 0.1 〜 2.0 の範囲で、1.0 を「標準的な重要度」として設定する。

{
  "site_type_label": "このサイトのビジネスタイプを日本語で自由に表現（例：GovTech SaaS型、地域密着型フォトスタジオ、戦略コンサルブティック）",
  "confidence": "high | medium | low",
  "reasoning": "判定の根拠を2文以内で。サイトの主要ビジネス特性と次元スコアの根拠を述べること。",
  "evaluation_profile": {
    "price_disclosure_weight":    数値,
    "cta_immediacy_weight":       数値,
    "lead_qualification_weight":  数値,
    "social_proof_weight":        数値,
    "credential_display_weight":  数値,
    "portfolio_display_weight":   数値,
    "navigation_depth_weight":    数値,
    "mobile_optimization_weight": 数値,
    "competitive_diff_weight":    数値,
    "trust_signal_weight":        数値
  }
}
"""


async def classify_site_type(state: dict, llm) -> dict:
    """
    Phase 0.5: 評価次元プロファイルを直接生成する。
    --site-type が明示されている場合は呼ばれない。
    """
    import json

    page_text  = state.get("page_text_content", "")[:3000]
    url        = state.get("url", "")
    title      = state.get("page_title", "")
    meta_desc  = state.get("meta_description", "")
    nav_labels = [sp.get("nav_label", "") for sp in state.get("subpages", [])]

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
            "site_type_label":      result.get("site_type_label", "汎用型"),
            "site_type_confidence": result.get("confidence", "low"),
            "site_type_reasoning":  result.get("reasoning", ""),
            "evaluation_profile":   result.get("evaluation_profile", _default_profile()),
        }
    except (json.JSONDecodeError, AttributeError):
        return {
            "site_type_label":      "汎用型（判定失敗）",
            "site_type_confidence": "low",
            "site_type_reasoning":  "自動判定に失敗。デフォルトプロファイルを使用。",
            "evaluation_profile":   _default_profile(),
        }


def _default_profile() -> dict:
    """全次元を1.0（標準）に設定したフォールバックプロファイル"""
    return {
        "price_disclosure_weight":    1.0,
        "cta_immediacy_weight":       1.0,
        "lead_qualification_weight":  1.0,
        "social_proof_weight":        1.0,
        "credential_display_weight":  1.0,
        "portfolio_display_weight":   1.0,
        "navigation_depth_weight":    1.0,
        "mobile_optimization_weight": 1.0,
        "competitive_diff_weight":    1.0,
        "trust_signal_weight":        1.0,
    }
```

---

## Fix 4：`core/state.py` — フィールド変更

`site_type` フィールドを廃止し、以下に置き換える：

```python
# 削除
# site_type: str

# 追加
site_type_label:      str   # 人間向け表示ラベル（採点には不使用）
site_type_confidence: str   # "high" | "medium" | "low" | "explicit"
site_type_reasoning:  str   # 判定理由
evaluation_profile:   dict  # 10次元の評価ウェイト辞書
context:              str   # --context オプションの値
```

---

## Fix 5：`main.py` — --site-type がプリセットをロードするよう変更

```python
import yaml

def load_config() -> dict:
    with open("analyst_config.yaml") as f:
        return yaml.safe_load(f)

def build_initial_state(args) -> dict:
    config = load_config()
    
    if args.site_type:
        # 名前付きプリセットからプロファイルをロード
        presets = config.get("site_type_presets", {})
        if args.site_type not in presets:
            raise ValueError(
                f"Unknown site type: {args.site_type}. "
                f"Available: {list(presets.keys())}"
            )
        preset = presets[args.site_type]
        return {
            "url":                  args.url,
            "site_type_label":      preset["label"],
            "site_type_confidence": "explicit",
            "site_type_reasoning":  f"--site-type {args.site_type} で明示指定",
            "evaluation_profile":   preset["profile"],
            "context":              getattr(args, "context", ""),
            # その他の既存フィールド...
        }
    else:
        # Phase 0.5 自動判定（evaluation_profile は後で設定される）
        return {
            "url":                  args.url,
            "site_type_label":      "",
            "site_type_confidence": "",
            "site_type_reasoning":  "",
            "evaluation_profile":   {},
            "context":              getattr(args, "context", ""),
            # その他の既存フィールド...
        }
```

---

## Fix 6：全エージェント（`agents/*.py`）— プロファイル注入

全5エージェントに共通の注入関数を追加する。
`core/agent_utils.py`（新規または既存のユーティリティファイル）に配置することを推奨。

```python
# core/agent_utils.py

def build_profile_instruction(profile: dict, agent_type: str) -> str:
    """
    評価次元プロファイルをエージェント向けの指示文に変換する。
    agent_type: "conversion" | "ux" | "brand" | "technical" | "competitive"
    """
    if not profile:
        return ""

    # エージェントごとに関連次元をマッピング
    AGENT_RELEVANT_DIMENSIONS = {
        "conversion": [
            "price_disclosure_weight",
            "cta_immediacy_weight",
            "lead_qualification_weight",
            "trust_signal_weight",
        ],
        "ux": [
            "navigation_depth_weight",
            "mobile_optimization_weight",
            "portfolio_display_weight",
            "cta_immediacy_weight",
        ],
        "brand": [
            "social_proof_weight",
            "credential_display_weight",
            "portfolio_display_weight",
            "competitive_diff_weight",
        ],
        "technical": [
            "mobile_optimization_weight",
            "trust_signal_weight",
            "navigation_depth_weight",
        ],
        "competitive": [
            "competitive_diff_weight",
            "social_proof_weight",
            "credential_display_weight",
            "market_positioning_weight",  # fallback to competitive_diff if absent
        ],
    }

    relevant = AGENT_RELEVANT_DIMENSIONS.get(agent_type, list(profile.keys()))
    
    lines = ["【このサイト固有の評価プロファイル】",
             "以下の次元ウェイトに基づいてスコアリングと優先度判定を行うこと。",
             "1.0 が標準。2.0 は最重要、0.1 はほぼ不問を意味する。",
             ""]
    
    DIMENSION_LABELS = {
        "price_disclosure_weight":    "価格透明性の重要度",
        "cta_immediacy_weight":       "即時コンバージョンの重要度",
        "lead_qualification_weight":  "リード選別の重要度",
        "social_proof_weight":        "社会的証明の重要度",
        "credential_display_weight":  "資格・経歴表示の重要度",
        "portfolio_display_weight":   "作品・実績表示の重要度",
        "navigation_depth_weight":    "ナビゲーション深度の必要度",
        "mobile_optimization_weight": "モバイル最適化の重要度",
        "competitive_diff_weight":    "競合差別化の重要度",
        "trust_signal_weight":        "セキュリティ・信頼シグナルの重要度",
    }

    for dim in relevant:
        val = profile.get(dim)
        if val is None:
            continue
        label = DIMENSION_LABELS.get(dim, dim)
        
        if val >= 1.5:
            guidance = "→ 欠如はP1候補。スコアへの影響大。"
        elif val >= 1.0:
            guidance = "→ 欠如はP2候補。標準的な重要度。"
        elif val >= 0.5:
            guidance = "→ 欠如はP3止まり。軽微な言及に留める。"
        else:
            guidance = "→ このサイトでは不問。指摘しない。"
        
        lines.append(f"- {label}: {val:.1f}  {guidance}")

    lines += [
        "",
        "【優先度判定のルール】",
        "- weight < 0.5 の次元に関する欠如は指摘しない（このサイトでは不要な要素）",
        "- weight 0.5〜1.0 の次元に関する欠如はP3のみ（軽微な改善として言及）",
        "- weight 1.0〜1.5 の次元に関する欠如はP2候補（次スプリントで対処）",
        "- weight > 1.5 の次元に関する欠如はP1候補（即時対処が必要）",
        "- 上記ルールは採点の絶対基準ではなく、他の要因と総合して判断すること",
    ]

    return "\n".join(lines)
```

### 各エージェントへの適用

各エージェントのシステムプロンプト生成部分に以下を追加する：

```python
# 例: agents/conversion_architect.py
from core.agent_utils import build_profile_instruction

def get_system_prompt(state: dict) -> str:
    profile_instruction = build_profile_instruction(
        state.get("evaluation_profile", {}),
        agent_type="conversion"
    )
    
    # 既存のシステムプロンプトの末尾（出力形式指定の直前）に挿入
    base_prompt = CONVERSION_SYSTEM_PROMPT
    if profile_instruction:
        base_prompt = base_prompt + "\n\n" + profile_instruction
    
    return base_prompt
```

同様に：
- `agents/ux_auditor.py` → `agent_type="ux"`
- `agents/brand_copy_analyst.py` → `agent_type="brand"`
- `agents/technical_auditor.py` → `agent_type="technical"`
- `agents/competitive_analyst.py` → `agent_type="competitive"`

---

## Fix 7：`core/report.py` — 重み付き総合スコアとヘッダー変更

### 7-1：総合スコアの重み付き計算

5エージェントの個別スコアを評価プロファイルで重み付けして集計する。
既存の単純平均を以下の関数に置き換える：

```python
def calculate_weighted_total(scores: dict, profile: dict) -> int:
    """
    評価次元プロファイルに基づく重み付き総合スコアを計算する。
    
    Args:
        scores: {
            "conversion": int, "ux": int, "brand": int,
            "technical": int, "competitive": int
        }
        profile: 10次元の評価ウェイト辞書
    Returns:
        重み付き総合スコア（0-100の整数）
    """
    if not profile:
        # プロファイルなし = 単純平均（フォールバック）
        return round(sum(scores.values()) / len(scores))

    # エージェントごとのドメインウェイトをプロファイルから算出
    def avg(*keys):
        vals = [profile.get(k, 1.0) for k in keys]
        return sum(vals) / len(vals)

    agent_weights = {
        "conversion": avg("cta_immediacy_weight",
                          "price_disclosure_weight",
                          "lead_qualification_weight"),
        "ux":         avg("navigation_depth_weight",
                          "mobile_optimization_weight"),
        "brand":      avg("social_proof_weight",
                          "credential_display_weight",
                          "portfolio_display_weight"),
        "technical":  1.0,  # 技術スコアは常に等重み（客観的指標のため）
        "competitive": avg("competitive_diff_weight",
                           "social_proof_weight"),
    }

    weighted_sum = sum(
        scores.get(agent, 0) * weight
        for agent, weight in agent_weights.items()
    )
    weight_total = sum(agent_weights.values())

    return round(weighted_sum / weight_total)
```

### 7-2：レポートヘッダーの変更

```python
# site_type_label と confidence からヘッダーを組み立てる
label     = state.get("site_type_label", "不明")
confidence = state.get("site_type_confidence", "")

if confidence == "explicit":
    site_type_line = f"サイトタイプ: {label}（明示指定）"
elif confidence == "high":
    site_type_line = f"サイトタイプ: {label}（自動判定・確信度：高）"
elif confidence == "medium":
    site_type_line = (
        f"サイトタイプ: {label}（自動判定・確信度：中 "
        f"— 異なる場合は --site-type で上書き可能）"
    )
else:
    site_type_line = (
        f"サイトタイプ: {label}（自動判定・確信度：低 "
        f"— --site-type での上書きを強く推奨）"
    )
```

---

## 確認用テストコマンド

```bash
cd ~/Projects/web-analyst-os

# ① 既存4サイトで自動判定を確認
# site_type_label が自由形式で出力されること
# evaluation_profile が10次元の辞書として state に格納されること（ログで確認）

python main.py https://www.scaryhippo.jp > /tmp/sh_v30.md
head -5 /tmp/sh_v30.md
# 期待: "サイトタイプ: 高単価・選別型コンサルティングブティック（自動判定・確信度：高）"等

python main.py https://qoollc.co.jp/ > /tmp/qoo_v30.md
head -5 /tmp/qoo_v30.md
# 期待: consulting ではなく "GovTech SaaS型" "行政向けプロダクト型" 等のラベルが出ること

python main.py https://sunphototakahashi.com > /tmp/sun_v30.md
head -5 /tmp/sun_v30.md
# 期待: "地域密着型フォトスタジオ" 等のトランザクション的ラベル

python main.py https://atelier-a3.jp > /tmp/a3_v30.md
head -5 /tmp/a3_v30.md
# 期待: "コンセプチュアルアート写真家" 等のポートフォリオ的ラベル

# ② --site-type プリセット指定が引き続き機能すること
python main.py https://www.scaryhippo.jp --site-type consulting > /tmp/sh_preset.md
head -5 /tmp/sh_preset.md
# 期待: "高単価・選別型コンサルティング（明示指定）"

# ③ 総合スコアの重み付きが機能していること（qooで確認）
# qooの price_disclosure_weight が低い → コンバージョン軸の重みが下がる
# → 総合スコアが単純平均より conversion スコアの影響を受けにくくなっているはず
grep "総合スコア" /tmp/qoo_v30.md

# ④ エージェントがプロファイルに基づいて優先度を変えていること
# qooで price_disclosure に関する指摘が P1 ではなく P3 以下に降格しているか確認
grep -n "価格\|料金.*透明\|price" /tmp/qoo_v30.md | head -5

# ⑤ 回帰テスト
python main.py https://www.scaryhippo.jp \
  --competitor-url https://qoollc.co.jp/ > /tmp/sh_comp_v30.md
grep "## 競合比較" /tmp/sh_comp_v30.md
# 競合比較セクションが正常出力されることを確認
```

---

## 確認の判定基準

| 確認項目 | 合格基準 |
|---|---|
| qoo の自動判定ラベル | "consulting" ではなく SaaS/プロダクト型を示すラベルが出る |
| 自由ラベルの多様性 | 4サイトで4種類の異なるラベルが生成される |
| プリセット指定 | --site-type consulting が analyst_config.yaml から正しく読み込まれる |
| 重み付きスコア | consulting サイトで cta_immediacy 低ウェイトが総合スコアに反映される |
| 優先度の自動調整 | qooで「価格非開示」指摘がP1から降格（price_disclosure_weight < 0.5のため） |
| 既存機能の回帰 | 競合比較・Skeptical・免責注記が正常出力 |

---

## バージョン管理

```bash
git add -A
git commit -m "v3.0: dimension-based evaluation profile, free-form site-type label, weighted total score"
git push origin main
```
