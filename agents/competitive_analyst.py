"""
Competitive Positioning Analyst — 差別化の専門エージェント
"""
from core.llm_router import call_llm
from agents._base import parse_agent_json, safe_score, build_page_context

SYSTEM_PROMPT = """あなたは「Competitive Positioning Analyst」です。差別化の専門家として、
競合との文脈の中でこのサイトが何を記憶させるかを判定します。

以下の観点で分析してください:
- ポジショニングの明確さ（カテゴリリーダー/ニッチ特化/価格訴求のどれを選んでいるか）
- 競合と同じ言葉・ビジュアル・構造を使っていないか
- 独自のフレーミング・造語・ビジュアルアイデンティティの有無
- 競合 URL が指定されている場合: 差別化ポイントと見劣りする点を比較
- 競合が指定されていない場合: 同カテゴリの一般的ベストプラクティスとの差分

必ず以下の JSON 形式のみで回答してください:
{
  "score": 0から100の整数,
  "summary": "1-2行の要約",
  "findings": [
    {"severity": "critical|high|medium|low", "item": "発見事項", "recommendation": "改善案"}
  ],
  "strengths": ["強み1", "強み2"]
}"""


def competitive_analyst_node(state: dict) -> dict:
    page_context = build_page_context(state)

    competitor_section = ""
    competitor_data = state.get("competitor_data")
    if competitor_data:
        c_title = competitor_data.get("page_title", "")
        c_text = competitor_data.get("page_text", "")[:3000]
        competitor_section = f"""
=== 競合サイトのデータ ===
競合URL: {state.get('competitor_url', '')}
タイトル: {c_title}
本文（抜粋）:
{c_text}
"""

    user_prompt = f"""以下のWebサイトの競合ポジショニングを分析してください。

{page_context}
{competitor_section}

JSON のみで回答してください。"""

    raw = call_llm("specialist", SYSTEM_PROMPT, user_prompt, max_tokens=1500)
    data = parse_agent_json(raw)
    score = safe_score(data)

    msg = {
        "agent": "competitive_analyst",
        "phase": "Phase1",
        "score": score,
        "summary": data.get("summary", ""),
        "findings": data.get("findings", []),
        "strengths": data.get("strengths", []),
        "raw": raw,
    }
    return {"messages": [msg], "current_phase": "phase1_competitive"}
