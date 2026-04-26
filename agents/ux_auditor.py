"""
UX Auditor — タスク完了率の専門エージェント
"""
from core.llm_router import call_llm
from agents._base import parse_agent_json, safe_score, build_page_context, get_site_type_context, build_subpages_context

SYSTEM_PROMPT = """あなたは「UX Auditor」です。タスク完了率の専門家として、
ユーザーが摩擦なく目的を達成できるかを判定します。

以下の観点で分析してください:
- グローバルナビゲーションの構造・深さ・ラベリング
- 情報アーキテクチャ（ユーザーが何をどこで探せるかが直感的か）
- パンくず・検索・フィルタリングの有無と機能性
- モバイルでの操作性（タップターゲットサイズ・スクロール操作）
- エラーメッセージ・空状態・ローディング表示の適切さ
- アクセシビリティ（コントラスト比・フォーカス表示・スクリーンリーダー対応）


【スコアリング独立性の確保】
- スコアは5の倍数ではなく、実際の評価に基づいた値（例: 67, 73, 81）を使用すること。
- 他のエージェントのスコアを参照・調整しないこと（専門家として独立して評価する）。
- 70〜79の範囲に集中することを避け、サイトの実態に基づき0〜100の全範囲を積極的に活用すること。
- 評価の根拠を1〜2文で示した上でスコアを確定すること。

必ず以下の JSON 形式のみで回答してください:
{
  "score": 0から100の整数,
  "summary": "1-2行の要約",
  "findings": [
    {"severity": "critical|high|medium|low", "item": "発見事項", "recommendation": "改善案"}
  ],
  "strengths": ["強み1", "強み2"]
}"""


def ux_auditor_node(state: dict) -> dict:
    page_context = build_page_context(state)
    subpages_context = build_subpages_context(state)
    user_prompt = f"""以下のWebサイトの UX・使いやすさを分析してください。

{page_context}{subpages_context}

JSON のみで回答してください。"""

    system = SYSTEM_PROMPT + "\n\n" + get_site_type_context(state)
    raw = call_llm("specialist", system, user_prompt, max_tokens=2500)
    data = parse_agent_json(raw)
    score = safe_score(data)

    msg = {
        "agent": "ux_auditor",
        "phase": "Phase1",
        "score": score,
        "summary": data.get("summary", ""),
        "findings": data.get("findings", []),
        "strengths": data.get("strengths", []),
        "raw": raw,
    }
    return {"messages": [msg], "current_phase": "phase1_ux"}
