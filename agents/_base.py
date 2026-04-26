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


SITE_TYPE_CONTEXT = {
    "transactional": (
        "【評価文脈】このサイトはBtoB/BtoCの流入・問合せ獲得を主目的とする。"
        "価格透明性・CTAの明確さ・社会的証明を重視して評価せよ。"
    ),
    "consulting": (
        "【評価文脈】このサイトは高単価・選別型のコンサルティングサービスを扱う。"
        "価格非掲載は業界慣行であり減点しない。"
        "代わりに、経歴の具体性・実績の信頼性・差別化ポジショニングを重点的に評価せよ。"
    ),
    "brand": (
        "【評価文脈】このサイトはブランディング・認知形成を主目的とする。"
        "直接的なコンバージョン導線の欠如は必ずしも欠点ではない。"
        "ブランドボイスの一貫性・世界観の伝達力を重視して評価せよ。"
    ),
    "portfolio": (
        "【評価文脈】このサイトは作品・実績の提示を主目的とする。"
        "視覚的な強さ・作品の見やすさ・クリエイターとしての差別化を重視し、"
        "コンバージョン最適化は副次的に評価せよ。"
    ),
}


def get_site_type_context(state: dict) -> str:
    """サイトタイプに応じた評価文脈文字列を返す"""
    site_type = state.get("site_type", "transactional")
    return SITE_TYPE_CONTEXT.get(site_type, SITE_TYPE_CONTEXT["transactional"])


def build_subpages_context(state: dict) -> str:
    """サブページデータをエージェントに渡すコンテキスト文字列を組み立てる"""
    subpages = state.get("subpages", [])
    if not subpages:
        return ""
    lines = ["\n=== サブページ収集データ ==="]
    for sp in subpages:
        label = sp.get("nav_label") or sp.get("url", "")
        size_kb = round(sp.get("page_size_bytes", 0) / 1024, 1)
        lines.append(f"\n--- {label} ({sp.get('url', '')} / {size_kb}KB) ---")
        lines.append(sp.get("text_content", "")[:2000])
    lines.append(
        "\n【サブページ分析指示】"
        "上記のサブページデータを参照し、分析に反映させること。"
        "「コンテンツ確認不可」「ページ内容が不明」等の判定はサブページ確認後に行うこと。"
    )
    return "\n".join(lines)


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
