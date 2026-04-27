"""
Web Analyst OS v3.0 — Phase 0.5: サイト評価次元プロファイル生成エージェント
固定ラベルではなく 10次元の評価ウェイトを直接出力する。
"""
import json
import re
from core.llm_router import call_llm

CLASSIFIER_SYSTEM_PROMPT = """あなたはWebサイトの評価プロファイルを生成する専門家です。
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
値はすべて 0.1〜2.0 の範囲で、1.0 を「標準的な重要度」として設定する。

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
}"""


def _default_profile() -> dict:
    """全次元を 1.0（標準）に設定したフォールバックプロファイル"""
    return {k: 1.0 for k in [
        "price_disclosure_weight", "cta_immediacy_weight", "lead_qualification_weight",
        "social_proof_weight", "credential_display_weight", "portfolio_display_weight",
        "navigation_depth_weight", "mobile_optimization_weight",
        "competitive_diff_weight", "trust_signal_weight",
    ]}


def classify_site_type(state: dict) -> dict:
    """
    Phase 0.5: 評価次元プロファイルを直接生成する。
    --site-type が明示指定（site_type_confidence == "explicit"）の場合は呼ばれない。
    """
    page_text  = state.get("page_text", "")[:3000]
    url        = state.get("target_url", "")
    title      = state.get("page_title", "")
    meta_desc  = state.get("page_meta_description", "")
    nav_labels = [sp.get("nav_label", "") for sp in state.get("subpages", []) if sp.get("nav_label")]

    user_message = f"""URL: {url}
ページタイトル: {title}
meta description: {meta_desc}
ナビゲーションラベル: {', '.join(nav_labels) if nav_labels else '（なし）'}

ページ本文（先頭3,000文字）:
{page_text}"""

    try:
        raw = call_llm("specialist", CLASSIFIER_SYSTEM_PROMPT, user_message, max_tokens=500)
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        result = json.loads(m.group(0)) if m else {}

        profile = result.get("evaluation_profile", {})
        # 値を 0.1〜2.0 にクリップ
        profile = {k: max(0.1, min(2.0, float(v))) for k, v in profile.items()}
        if len(profile) < 5:
            profile = _default_profile()

        return {
            "site_type_label":      result.get("site_type_label", "汎用型"),
            "site_type_confidence": result.get("confidence", "low"),
            "site_type_reasoning":  result.get("reasoning", ""),
            "evaluation_profile":   profile,
        }
    except Exception as e:
        return {
            "site_type_label":      "汎用型（判定失敗）",
            "site_type_confidence": "low",
            "site_type_reasoning":  f"自動判定失敗（{e}）→ デフォルトプロファイル使用",
            "evaluation_profile":   _default_profile(),
        }


def site_classifier_node(state: dict) -> dict:
    """LangGraph ノード: Phase 0.5 評価プロファイル自動生成"""
    if state.get("site_type_confidence") == "explicit":
        label = state.get("site_type_label", state.get("site_type", ""))
        print(f"  [Phase 0.5] 評価プロファイル明示指定: {label}")
        return {"current_phase": "phase0.5_skip"}

    result = classify_site_type(state)
    confidence_ja = {"high": "高", "medium": "中", "low": "低"}.get(
        result["site_type_confidence"], result["site_type_confidence"]
    )
    profile = result["evaluation_profile"]
    # 主要な高次元を表示
    top = sorted(profile.items(), key=lambda x: x[1], reverse=True)[:3]
    top_str = ", ".join(f"{k.replace('_weight','')}={v:.1f}" for k, v in top)
    print(f"  [Phase 0.5] サイトタイプ: {result['site_type_label']} （確信度：{confidence_ja}）")
    print(f"             高ウェイト次元: {top_str}")
    return {**result, "current_phase": "phase0.5_complete"}
