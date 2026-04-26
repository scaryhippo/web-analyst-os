"""
Web Analyst OS — LangGraph グラフ定義
Phase 0: ブラウザ収集 → Phase 1: 5専門エージェント並列 →
Phase 2: Red Team → Phase 3: スコア計算 → Phase 4: レポート生成
"""
import concurrent.futures
from langgraph.graph import StateGraph, END

from core.state import AnalystState
from core.browser import BrowserCollector
from core.scorer import calculate_scores
from core.report import generate_report
from core.llm_router import load_config

from agents.conversion_architect import conversion_architect_node
from agents.ux_auditor import ux_auditor_node
from agents.brand_copy_analyst import brand_copy_analyst_node
from agents.technical_auditor import technical_auditor_node
from agents.competitive_analyst import competitive_analyst_node
from agents.skeptical_firsttimer import red_team_attack_node, specialist_rebuttal_node


# ─────────────────────────────────────────────
# Phase 0: ブラウザ収集
# ─────────────────────────────────────────────

def browser_collection_node(state: AnalystState) -> dict:
    config = load_config()
    collector = BrowserCollector(config)
    url = state["target_url"]
    task_id = state["task_id"]

    do_crawl = state.get("crawl_subpages", False)
    crawl_max = state.get("crawl_max", 3)

    try:
        data = collector.collect_sync(url, task_id, crawl_subpages=do_crawl, crawl_max=crawl_max)
    except Exception as e:
        return {
            "error": f"ブラウザ収集失敗: {e}",
            "current_phase": "error",
            "page_title": "",
            "page_meta_description": "",
            "page_text": "",
            "page_html": "",
            "screenshot_path": "",
            "mobile_screenshot_path": "",
            "page_load_metrics": {},
            "subpages": [],
            "competitor_data": None,
        }

    # 競合 URL がある場合は追加収集
    competitor_data = None
    competitor_url = state.get("competitor_url")
    if competitor_url:
        try:
            competitor_data = collector.collect_sync(competitor_url, task_id + "_competitor")
        except Exception:
            competitor_data = None

    return {
        "page_title": data["page_title"],
        "page_meta_description": data["page_meta_description"],
        "page_text": data["page_text"],
        "page_html": data["page_html"],
        "screenshot_path": data["screenshot_path"],
        "mobile_screenshot_path": data["mobile_screenshot_path"],
        "page_load_metrics": data["page_load_metrics"],
        "subpages": data.get("subpages", []),
        "competitor_data": competitor_data,
        "current_phase": "phase0_complete",
        "error": None,
    }


# ─────────────────────────────────────────────
# Phase 1: 専門エージェント並列実行
# ─────────────────────────────────────────────

_SPECIALIST_NODES = [
    conversion_architect_node,
    ux_auditor_node,
    brand_copy_analyst_node,
    technical_auditor_node,
    competitive_analyst_node,
]

_FOCUS_MAP = {
    "conversion": [conversion_architect_node],
    "ux":         [ux_auditor_node],
    "brand":      [brand_copy_analyst_node],
    "technical":  [technical_auditor_node],
    "all":        _SPECIALIST_NODES,
}


def specialist_analysis_node(state: AnalystState) -> dict:
    """5専門エージェントを ThreadPoolExecutor で並列実行する"""
    focus = state.get("focus", "all")
    nodes = _FOCUS_MAP.get(focus, _SPECIALIST_NODES)

    all_messages = []
    state_dict = dict(state)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(node, state_dict): node for node in nodes}
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                all_messages.extend(result.get("messages", []))
            except Exception as e:
                node_fn = futures[future]
                name = getattr(node_fn, "__name__", str(node_fn))
                print(f"  [警告] {name} が失敗しました: {str(e)[:120]}")

    return {
        "messages": all_messages,
        "current_phase": "phase1_complete",
    }


# ─────────────────────────────────────────────
# Phase 3: スコア計算・優先度分類
# ─────────────────────────────────────────────

def synthesis_node(state: AnalystState) -> dict:
    config = load_config()
    messages = state.get("messages", [])

    site_type = state.get("site_type", "transactional")
    score_result = calculate_scores(messages, config, site_type)
    overall = score_result.pop("overall", 50)
    scores = score_result  # { conversion, ux, brand_copy, technical, competitive }

    # 優先度分類
    p1_thresh = config["priority"]["p1_score_threshold"]
    p2_thresh = config["priority"]["p2_score_threshold"]

    p1_items, p2_items, p3_items, strengths = [], [], [], []

    for msg in messages:
        agent = msg.get("agent", "")
        for finding in msg.get("findings", []):
            item_text = f"[{agent}] {finding.get('item', '')} → {finding.get('recommendation', '')}"
            severity = finding.get("severity", "low")
            if severity in ("critical", "high"):
                p1_items.append(item_text)
            elif severity == "medium":
                p2_items.append(item_text)
            else:
                p3_items.append(item_text)
        for s in msg.get("strengths", []):
            strengths.append(f"[{agent}] {s}")

    # スコアが低い次元も P1/P2/P3 に追加
    label_map = {
        "conversion": "コンバージョン設計",
        "ux":         "UX・使いやすさ",
        "brand_copy": "ブランド・コピー",
        "technical":  "技術・パフォーマンス",
        "competitive":"競合ポジショニング",
    }
    for key, label in label_map.items():
        sc = scores.get(key, 50)
        if sc < p1_thresh:
            dim_item = f"[スコア {sc}/100] {label} — 早急な改善が必要"
            if dim_item not in p1_items:
                p1_items.insert(0, dim_item)
        elif sc < p2_thresh:
            dim_item = f"[スコア {sc}/100] {label} — 次スプリントで対応推奨"
            if dim_item not in p2_items:
                p2_items.insert(0, dim_item)

    # エグゼクティブサマリー生成（LLM 失敗時はスコアから自動生成）
    from core.llm_router import call_llm
    summaries = [f"・{msg.get('summary','')}" for msg in messages if msg.get("summary")]
    summary_text = "\n".join(summaries[:5])
    exec_summary_raw = ""
    try:
        exec_summary_raw = call_llm(
            "synthesis",
            "Web分析の専門家として、以下の分析結果を3行以内に要約してください。数値を含めて簡潔に。",
            f"総合スコア: {overall}/100\n\n各専門家のサマリー:\n{summary_text}",
            max_tokens=500,
        )
    except Exception:
        # LLM が利用できない場合はスコアから自動生成
        top_names = {"conversion": "コンバージョン設計", "ux": "UX", "brand_copy": "ブランド", "technical": "技術", "competitive": "競合ポジショニング"}
        if scores:
            sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            strong = sorted_scores[0] if sorted_scores else None
            weak = sorted(scores.items(), key=lambda x: x[1])[0] if scores else None
            parts = [f"総合スコア {overall}/100。"]
            if strong:
                parts.append(f"最高スコア: {top_names.get(strong[0], strong[0])}（{strong[1]}点）。")
            if weak:
                parts.append(f"優先改善領域: {top_names.get(weak[0], weak[0])}（{weak[1]}点）。")
            exec_summary_raw = "".join(parts)
        else:
            exec_summary_raw = f"総合スコア {overall}/100。"

    return {
        "scores": scores,
        "overall_score": overall,
        "p1_items": p1_items,
        "p2_items": p2_items,
        "p3_items": p3_items,
        "strengths": list(dict.fromkeys(strengths)),  # 重複除去
        "executive_summary": exec_summary_raw.strip(),
        "current_phase": "phase3_complete",
    }


# ─────────────────────────────────────────────
# Phase 4: レポート生成
# ─────────────────────────────────────────────

def report_generation_node(state: AnalystState) -> dict:
    report = generate_report(state)
    return {
        "final_report": report,
        "current_phase": "completed",
    }


# ─────────────────────────────────────────────
# 条件分岐: ブラウザ収集失敗時
# ─────────────────────────────────────────────

def should_continue(state: AnalystState) -> str:
    if state.get("error"):
        return "error_end"
    return "continue"


def should_run_red_team(state: AnalystState) -> str:
    if state.get("run_red_team", True):
        return "red_team"
    return "skip_red_team"


# ─────────────────────────────────────────────
# グラフ組み立て
# ─────────────────────────────────────────────

def create_analyst_graph():
    graph = StateGraph(AnalystState)

    graph.add_node("browser_collection", browser_collection_node)
    graph.add_node("specialist_analysis", specialist_analysis_node)
    graph.add_node("red_team_attack", red_team_attack_node)
    graph.add_node("specialist_rebuttal", specialist_rebuttal_node)
    graph.add_node("synthesis", synthesis_node)
    graph.add_node("report_generation", report_generation_node)

    graph.set_entry_point("browser_collection")

    graph.add_conditional_edges(
        "browser_collection",
        should_continue,
        {
            "continue": "specialist_analysis",
            "error_end": END,
        },
    )
    graph.add_edge("specialist_analysis", "synthesis")

    graph.add_conditional_edges(
        "synthesis",
        should_run_red_team,
        {
            "red_team": "red_team_attack",
            "skip_red_team": "report_generation",
        },
    )

    graph.add_edge("red_team_attack", "specialist_rebuttal")
    graph.add_edge("specialist_rebuttal", "report_generation")
    graph.add_edge("report_generation", END)

    return graph.compile()
