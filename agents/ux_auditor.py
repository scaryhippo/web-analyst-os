"""
UX Auditor — タスク完了率の専門エージェント
"""
from core.llm_router import call_llm
from core.agent_utils import build_profile_instruction
from agents._base import build_context_prefix, build_structured_data_context, parse_agent_json, safe_score, build_page_context, get_site_type_context, build_subpages_context

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

    _profile_instr = build_profile_instruction(state.get("evaluation_profile", {}), "ux")
    _sd_ctx = build_structured_data_context(state)
    system = SYSTEM_PROMPT + "\n\n" + get_site_type_context(state) + (("\n\n" + _sd_ctx) if _sd_ctx else "") + (("\n\n" + _profile_instr) if _profile_instr else "")
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
