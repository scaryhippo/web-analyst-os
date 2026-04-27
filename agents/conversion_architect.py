"""
Conversion Architect — コンバージョン設計の専門エージェント
"""
from core.llm_router import call_llm
from agents._base import build_structured_data_context, parse_agent_json, safe_score, build_page_context, get_site_type_context

SYSTEM_PROMPT = """あなたは「Conversion Architect」です。コンバージョン設計の専門家として、
Webサイトのすべての要素が訪問者を目標行動に向けて動かしているかを判定します。

以下の観点で分析してください:
- ファーストビューで「何をする会社か」「なぜ選ぶか」「次に何をすべきか」の3点が5秒以内に伝わるか
- CTA のコピー・配置・優先順位が適切か（1ページに主 CTA は1つか）
- コンバージョンファネルの各ステップに摩擦がないか
- トラスト・シグナル（実績・導入事例・認定・メディア掲載）の配置と説得力
- フォームの長さ・ステップ数・エラー処理

必ず以下の JSON 形式のみで回答してください（説明文は不要）:
{
  "score": 0から100の整数,
  "summary": "1-2行の要約",
  "findings": [
    {"severity": "critical|high|medium|low", "item": "発見事項", "recommendation": "改善案"}
  ],
  "strengths": ["強み1", "強み2"]
}"""


def conversion_architect_node(state: dict) -> dict:
    page_context = build_page_context(state)
    user_prompt = f"""以下のWebサイトのコンバージョン設計を分析してください。

{page_context}

JSON のみで回答してください。"""

    _sd_ctx = build_structured_data_context(state)
    system = SYSTEM_PROMPT + "\n\n" + get_site_type_context(state) + (("\n\n" + _sd_ctx) if _sd_ctx else "")
    raw = call_llm("specialist", system, user_prompt, max_tokens=2500)
    data = parse_agent_json(raw)
    score = safe_score(data)

    msg = {
        "agent": "conversion_architect",
        "phase": "Phase1",
        "score": score,
        "summary": data.get("summary", ""),
        "findings": data.get("findings", []),
        "strengths": data.get("strengths", []),
        "raw": raw,
    }
    return {"messages": [msg], "current_phase": "phase1_conversion"}
