"""
Brand & Copy Analyst — バリュープロポジションの専門エージェント
"""
from core.llm_router import call_llm
from agents._base import parse_agent_json, safe_score, build_page_context

SYSTEM_PROMPT = """あなたは「Brand & Copy Analyst」です。バリュープロポジションの専門家として、
明確で差別化されたメッセージが伝わるかを判定します。

以下の観点で分析してください:
- H1・ヒーローコピーが「誰のための・何の・どんな価値か」を明示しているか
- トーン・オブ・ボイスの一貫性（カジュアル/フォーマル、親しみ/権威）
- 社会的証明（数値実績・顧客ロゴ・推薦文・導入事例）の質と配置
- ページ全体のナラティブ構造（問題提起→解決策→証拠→行動）
- 競合と見分けがつかない汎用コピー（「最高品質」「業界トップ」等）の使用
- CTAコピーの具体性（「詳細を見る」より「14日間無料で試す」）

必ず以下の JSON 形式のみで回答してください:
{
  "score": 0から100の整数,
  "summary": "1-2行の要約",
  "findings": [
    {"severity": "critical|high|medium|low", "item": "発見事項", "recommendation": "改善案"}
  ],
  "strengths": ["強み1", "強み2"]
}"""


def brand_copy_analyst_node(state: dict) -> dict:
    page_context = build_page_context(state)
    user_prompt = f"""以下のWebサイトのブランド・コピーを分析してください。

{page_context}

JSON のみで回答してください。"""

    raw = call_llm("specialist", SYSTEM_PROMPT, user_prompt, max_tokens=1500)
    data = parse_agent_json(raw)
    score = safe_score(data)

    msg = {
        "agent": "brand_copy_analyst",
        "phase": "Phase1",
        "score": score,
        "summary": data.get("summary", ""),
        "findings": data.get("findings", []),
        "strengths": data.get("strengths", []),
        "raw": raw,
    }
    return {"messages": [msg], "current_phase": "phase1_brand"}
