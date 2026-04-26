"""
エージェント共通ユーティリティ
"""
import json
import re
from typing import Optional


def parse_agent_json(response: str) -> dict:
    """
    LLM の応答テキストから JSON を抽出してパースする。
    コードブロック（```json ... ```）があれば中身を取り出す。
    パース失敗時はデフォルト値を返す。
    """
    # コードブロック内 JSON を抽出（貪欲マッチで入れ子対応）
    code_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", response, re.DOTALL)
    if code_match:
        json_str = code_match.group(1)
    else:
        # 先頭の { から末尾の } を抽出（貪欲マッチ）
        brace_match = re.search(r"\{.*\}", response, re.DOTALL)
        json_str = brace_match.group(0) if brace_match else "{}"

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return {}


def safe_score(data: dict, default: int = 50) -> int:
    """score フィールドを 0〜100 の整数で返す"""
    raw = data.get("score", default)
    try:
        return max(0, min(100, int(raw)))
    except (TypeError, ValueError):
        return default


def build_page_context(state: dict) -> str:
    """エージェントに渡すページコンテキスト文字列を組み立てる"""
    title = state.get("page_title", "")
    meta = state.get("page_meta_description", "")
    text = state.get("page_text", "")
    metrics = state.get("page_load_metrics", {})
    url = state.get("target_url", "")

    load_ms = int(metrics.get("load_time_ms", 0))
    ttfb = int(metrics.get("ttfb", 0))
    size_kb = metrics.get("page_size_kb", 0)

    return (
        f"分析対象URL: {url}\n"
        f"ページタイトル: {title}\n"
        f"meta description: {meta}\n"
        f"ページロード: {load_ms}ms (TTFB: {ttfb}ms, サイズ: {size_kb}KB)\n\n"
        f"=== ページ本文テキスト ===\n{text}\n"
    )
