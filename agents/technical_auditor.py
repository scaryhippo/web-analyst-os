"""
Technical & Performance Auditor — 技術的障壁の専門エージェント
HTML・メトリクスから判定（Lighthouse 不要）
"""
from core.llm_router import call_llm
from agents._base import parse_agent_json, safe_score

SYSTEM_PROMPT = """あなたは「Technical & Performance Auditor」です。技術的障壁の専門家として、
技術的問題がエンゲージメントと発見可能性を阻害していないかを判定します。

HTML ソースと収集済みパフォーマンスメトリクスから以下を判定してください:
- ページロード速度（page_load_metrics を参照）
- SEO 基本要件: title・meta description の最適化、h1 の存在・内容、canonical 設定
- 構造化データ（JSON-LD・OGP・Twitter Cards）の実装状況
- 画像の alt テキスト・遅延読み込み・WebP 対応
- HTTPS・セキュリティヘッダーの存在（HTML ソースから判断可能な範囲）
- モバイル対応（viewport meta・タッチフレンドリーな要素サイズ）
- リンク切れの疑いがある箇所（href="#" や javascript:void の多用）

注意: Lighthouse は直接実行せず、提供されたHTMLとメトリクスから判断してください。

必ず以下の JSON 形式のみで回答してください:
{
  "score": 0から100の整数,
  "summary": "1-2行の要約",
  "findings": [
    {"severity": "critical|high|medium|low", "item": "発見事項", "recommendation": "改善案"}
  ],
  "strengths": ["強み1", "強み2"]
}"""


def technical_auditor_node(state: dict) -> dict:
    metrics = state.get("page_load_metrics", {})
    load_ms = int(metrics.get("load_time_ms", 0))
    ttfb = int(metrics.get("ttfb", 0))
    size_kb = metrics.get("page_size_kb", 0)
    url = state.get("target_url", "")
    title = state.get("page_title", "")
    meta = state.get("page_meta_description", "")
    html_snippet = state.get("page_html", "")[:12000]

    user_prompt = f"""以下のWebサイトの技術・パフォーマンスを分析してください。

分析対象URL: {url}
ページタイトル: {title}
meta description: {meta}
ページロード: {load_ms}ms (TTFB: {ttfb}ms, サイズ: {size_kb}KB)

=== HTML ソース（先頭12,000文字）===
{html_snippet}

JSON のみで回答してください。"""

    raw = call_llm("technical", SYSTEM_PROMPT, user_prompt, max_tokens=1500)
    data = parse_agent_json(raw)
    score = safe_score(data)

    msg = {
        "agent": "technical_auditor",
        "phase": "Phase1",
        "score": score,
        "summary": data.get("summary", ""),
        "findings": data.get("findings", []),
        "strengths": data.get("strengths", []),
        "raw": raw,
    }
    return {"messages": [msg], "current_phase": "phase1_technical"}
