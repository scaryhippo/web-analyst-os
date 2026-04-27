"""
Competitive Positioning Analyst — 差別化の専門エージェント
"""
from core.llm_router import call_llm
from core.agent_utils import build_profile_instruction
from agents._base import build_context_prefix, build_structured_data_context, parse_agent_json, safe_score, build_page_context, get_site_type_context, build_subpages_context

SYSTEM_PROMPT = """あなたは「Competitive Positioning Analyst」です。差別化の専門家として、
競合との文脈の中でこのサイトが何を記憶させるかを判定します。

以下の観点で分析してください:
- ポジショニングの明確さ（カテゴリリーダー/ニッチ特化/価格訴求のどれを選んでいるか）
- 競合と同じ言葉・ビジュアル・構造を使っていないか
- 独自のフレーミング・造語・ビジュアルアイデンティティの有無
- 競合 URL が指定されている場合: 差別化ポイントと見劣りする点を比較
- 競合が指定されていない場合: 同カテゴリの一般的ベストプラクティスとの差分


【スコアリング独立性の確保】
- スコアは5の倍数ではなく、実際の評価に基づいた値（例: 67, 73, 81）を使用すること。
- 他のエージェントのスコアを参照・調整しないこと（専門家として独立して評価する）。
- 70〜79の範囲に集中することを避け、サイトの実態に基づき0〜100の全範囲を積極的に活用すること。
- 評価の根拠を1〜2文で示した上でスコアを確定すること。


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

必ず以下の JSON 形式で回答してください:
{
  "score": 0から100の整数,
  "summary": "1-2行の要約",
  "findings": [
    {"severity": "critical|high|medium|low", "item": "発見事項", "recommendation": "改善案"}
  ],
  "strengths": ["強み1", "強み2"]
}"""

COMPETITOR_EXTRA_PROMPT = """
【競合比較モード時の追加出力】
上記JSONの後に、以下の<competitive_summary>タグで囲まれた競合比較サマリーを必ず追加出力すること。

また、JSONに "competitor_scores" フィールドを追加し、競合サイトの各軸の推定スコアを出力すること:
{
  "score": ...,
  "competitor_scores": {
    "conversion": 0-100,
    "ux": 0-100,
    "brand_copy": 0-100,
    "technical": 0-100,
    "competitive": 0-100
  },
  ...
}

<competitive_summary>
自社優位軸:
- [評価軸名]: [1文で根拠を示す。例：「技術・パフォーマンス: ロード432ms vs 競合693msで1.6倍高速」]
（最大3点、具体的なデータ・コピー・機能の差を根拠とする）

競合優位軸:
- [評価軸名]: [1文で根拠を示す。例：「社会的証明: 競合はプロダクトSaaSで導入企業名を公開」]
（最大3点、同様に根拠必須）

戦略的示唆:
[2〜3文で「自社が取るべき差別化アクション」を具体的に述べる。
 競合が強い軸で真っ向勝負せず、自社優位軸をどう活かすかの方向性を示す。]
</competitive_summary>

注意:
- 推測ではなく収集したサイトデータに基づいて記述すること
- 「総じて」「概して」等の抽象表現は使わないこと
"""


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

    has_competitor = bool(state.get("competitor_url") and state.get("competitor_data"))

    subpages_context = build_subpages_context(state)
    user_prompt = f"""以下のWebサイトの競合ポジショニングを分析してください。

{page_context}
{competitor_section}{subpages_context}

JSON{"と<competitive_summary>タグ" if has_competitor else "のみ"}で回答してください。"""

    _ctx_prefix = build_context_prefix(state)
    _profile_instr = build_profile_instruction(state.get("evaluation_profile", {}), "competitive")
    _sd_ctx = build_structured_data_context(state)
    extra = COMPETITOR_EXTRA_PROMPT if has_competitor else ""
    system = _ctx_prefix + SYSTEM_PROMPT + extra + "\n\n" + get_site_type_context(state) + (("\n\n" + _sd_ctx) if _sd_ctx else "") + (("\n\n" + _profile_instr) if _profile_instr else "")
    max_tok = 3500 if has_competitor else 2500
    raw = call_llm("specialist", system, user_prompt, max_tokens=max_tok)
    data = parse_agent_json(raw)
    score = safe_score(data)

    competitor_scores = data.get("competitor_scores", {})

    msg = {
        "agent": "competitive_analyst",
        "phase": "Phase1",
        "score": score,
        "summary": data.get("summary", ""),
        "findings": data.get("findings", []),
        "strengths": data.get("strengths", []),
        "raw": raw,
    }
    result = {"messages": [msg], "current_phase": "phase1_competitive", "competitive_analysis": raw}
    if competitor_scores:
        result["competitor_scores"] = competitor_scores
    return result
