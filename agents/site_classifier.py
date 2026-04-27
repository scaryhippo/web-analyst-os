"""
Web Analyst OS — Phase 0.5: サイトタイプ自動分類エージェント
Phase 0（ブラウザ収集）の直後に実行し、state["site_type"] を自動設定する。
--site-type が明示指定されている場合はスキップされる。
"""
import json
from core.llm_router import call_llm
from agents._base import parse_agent_json

CLASSIFIER_SYSTEM_PROMPT = """あなたはWebサイトのビジネスタイプを分類する専門家です。
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
- GovTechのように B2G で人的コンサルが主体ならconsultingとする"""


def classify_site_type(state: dict) -> dict:
    """
    Phase 0.5: ページテキストとメタ情報からサイトタイプを自動判定する。
    --site-type が明示指定（site_type_confidence == "explicit"）の場合は呼ばれない。
    """
    page_text = state.get("page_text", "")[:3000]
    url = state.get("target_url", "")
    title = state.get("page_title", "")
    meta_desc = state.get("page_meta_description", "")
    nav_labels = [sp.get("nav_label", "") for sp in state.get("subpages", []) if sp.get("nav_label")]

    user_message = f"""URL: {url}
ページタイトル: {title}
meta description: {meta_desc}
ナビゲーションラベル: {', '.join(nav_labels) if nav_labels else '（なし）'}

ページ本文（先頭3,000文字）:
{page_text}"""

    try:
        raw = call_llm("specialist", CLASSIFIER_SYSTEM_PROMPT, user_message, max_tokens=300)
        # JSON を抽出してパース
        import re
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        result = json.loads(m.group(0)) if m else {}
        site_type = result.get("site_type", "transactional")
        # バリデーション
        if site_type not in ("transactional", "consulting", "portfolio", "brand"):
            site_type = "transactional"
        return {
            "site_type":            site_type,
            "site_type_confidence": result.get("confidence", "low"),
            "site_type_signals":    result.get("primary_signals", []),
            "site_type_reasoning":  result.get("reasoning", ""),
        }
    except Exception as e:
        return {
            "site_type":            "transactional",
            "site_type_confidence": "low",
            "site_type_signals":    [],
            "site_type_reasoning":  f"自動判定失敗（{e}）→ デフォルト transactional を使用",
        }


def site_classifier_node(state: dict) -> dict:
    """LangGraph ノード: Phase 0.5 サイトタイプ自動分類"""
    # 明示指定済みの場合はスキップ
    if state.get("site_type_confidence") == "explicit":
        print(f"  [Phase 0.5] サイトタイプ明示指定: {state.get('site_type')}")
        return {"current_phase": "phase0.5_skip"}

    result = classify_site_type(state)
    confidence_ja = {"high": "高", "medium": "中", "low": "低"}.get(result["site_type_confidence"], result["site_type_confidence"])
    signals_str = "、".join(result["site_type_signals"]) if result["site_type_signals"] else "—"
    print(f"  [Phase 0.5] サイトタイプ自動判定: {result['site_type']} （確信度：{confidence_ja}）")
    print(f"             根拠: {signals_str}")
    return {**result, "current_phase": "phase0.5_complete"}
