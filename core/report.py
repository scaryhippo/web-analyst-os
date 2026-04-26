"""
Web Analyst OS — レポート生成・整形
"""
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def _score_bar(score: int) -> str:
    """スコアを視覚的なバーで表現する"""
    filled = round(score / 10)
    return "█" * filled + "░" * (10 - filled)


def clean_executive_summary(text: str) -> str:
    """先頭の Markdown ヘッダー行（# で始まる行）を除去する"""
    lines = text.strip().split("\n")
    while lines and lines[0].strip().startswith("#"):
        lines.pop(0)
    return "\n".join(lines).strip()


# ─── Fix 3: P2 品質フィルタ ───────────────────────────────────────────────────

def filter_p2_quality(p2_items: list) -> list:
    """
    P2 からスコア羅列のみの項目を除去する。
    「→」または具体的な改善アクションを含む項目のみ残す。
    """
    filtered = []
    for item in p2_items:
        if "→" in item:
            filtered.append(item)
        elif re.match(r"- \[(?!スコア)[^\]]+\]", item) and len(item) > 60:
            filtered.append(item)
    return filtered


# ─── Fix 4: クロスエージェント重複除去 ──────────────────────────────────────

DEDUP_KEYWORDS = [
    ["CTA", "コンバージョン", "問い合わせ導線", "CTAが"],
    ["社会的証明", "トラスト", "信頼", "実績", "クライアント名"],
    ["価格", "料金", "価格帯", "費用"],
    ["ナビゲーション", "ナビ", "グローバルナビ"],
    ["モバイル", "タップ", "スマートフォン"],
    ["パンくず", "breadcrumb"],
    ["フォーカス", "キーボードナビ", "focus-visible"],
    ["meta description", "メタディスクリプション"],
    ["構造化データ", "JSON-LD", "OGP"],
]


def dedup_recommendations(items: list) -> list:
    """
    同一キーワードグループに属するアイテムが複数ある場合、
    最初（通常最も詳細）のみ残す。
    """
    seen_groups: set = set()
    result = []
    for item in items:
        item_lower = item.lower()
        matched_group = None
        for i, keywords in enumerate(DEDUP_KEYWORDS):
            if sum(1 for kw in keywords if kw.lower() in item_lower) >= 2:
                matched_group = i
                break
        if matched_group is None or matched_group not in seen_groups:
            result.append(item)
            if matched_group is not None:
                seen_groups.add(matched_group)
    return result


# ─── Fix 2: P1 上限キャップ（最大5件） ───────────────────────────────────────

P1_MAX = 5


def cap_p1_items(p1_items: list, p2_items: list) -> tuple:
    """
    P1 を P1_MAX 件に絞る。超過分はP2先頭に移動する。
    具体的な改善提案（[agent_name] 形式）を優先してP1に残し、
    スコア評価のみの行はP2に降格する。
    """
    if len(p1_items) <= P1_MAX:
        return p1_items, p2_items

    specific = [item for item in p1_items if not item.strip().startswith("- [スコア") and not item.strip().startswith("[スコア")]
    score_only = [item for item in p1_items if item.strip().startswith("- [スコア") or item.strip().startswith("[スコア")]

    p1_final = specific[:P1_MAX]
    overflow = specific[P1_MAX:] + score_only
    return p1_final, overflow + p2_items


def generate_report(state: dict) -> str:
    url = state.get("target_url", "")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    scores = state.get("scores", {})
    overall = state.get("overall_score", 0)
    executive_summary = state.get("executive_summary", "")
    p1_items = state.get("p1_items", [])
    p2_items = state.get("p2_items", [])
    p3_items = state.get("p3_items", [])
    strengths = state.get("strengths", [])
    messages = state.get("messages", [])
    red_team_attacks = state.get("red_team_attacks", [])
    specialist_responses = state.get("specialist_responses", [])
    competitor_url = state.get("competitor_url")
    competitor_data = state.get("competitor_data")
    metrics = state.get("page_load_metrics", {})
    site_type = state.get("site_type", "transactional")

    score_labels = [
        ("conversion",  "コンバージョン設計"),
        ("ux",          "UX・使いやすさ"),
        ("brand_copy",  "ブランド・コピー"),
        ("technical",   "技術・パフォーマンス"),
        ("competitive", "競合ポジショニング"),
    ]

    site_type_labels = {
        "transactional": "流入型BtoB/BtoC",
        "consulting":    "高単価・選別型コンサルティング",
        "brand":         "ブランディング・認知目的",
        "portfolio":     "作品集・実績提示",
    }

    lines = [
        "# Web Analyst OS — 分析レポート",
        f"分析日時: {now}",
        f"対象 URL: {url}",
        f"サイトタイプ: {site_type_labels.get(site_type, site_type)}",
        "━" * 40,
        "",
        "## スコアカード",
        "```",
        "┌─────────────────────────┬──────────┬────────────────┐",
        "│ 項目                    │  スコア  │ バー           │",
        "├─────────────────────────┼──────────┼────────────────┤",
    ]
    for key, label in score_labels:
        sc = scores.get(key, "—")
        sc_str = f"{sc:3d}/100" if isinstance(sc, int) else "  —/100"
        bar = _score_bar(sc) if isinstance(sc, int) else "—" * 10
        lines.append(f"│ {label:<23} │ {sc_str}  │ {bar} │")

    lines += [
        "├─────────────────────────┼──────────┼────────────────┤",
        f"│ {'総合スコア':<23} │ {overall:3d}/100  │ {_score_bar(overall)} │",
        "└─────────────────────────┴──────────┴────────────────┘",
        "```",
        "",
        "## エグゼクティブサマリー",
        "",
        clean_executive_summary(executive_summary),  # Fix 6: 二重ヘッダー除去
        "",
    ]

    # Fix 4: 重複除去 → Fix 2: P1 キャップ → Fix 3: P2 品質フィルタ
    p1_items = dedup_recommendations(p1_items)
    p2_items = dedup_recommendations(p2_items)
    p1_items, p2_items = cap_p1_items(p1_items, p2_items)
    p2_items = filter_p2_quality(p2_items)

    # P1
    lines += ["## 🔴 P1 — 今すぐ対処（インパクト大）", ""]
    if p1_items:
        for item in p1_items:
            lines.append(f"- {item}")
    else:
        lines.append("P1 課題なし — 大きな問題は見当たりません。")
    lines.append("")

    # P2
    lines += ["## 🟡 P2 — 次のスプリントで", ""]
    if p2_items:
        for item in p2_items:
            lines.append(f"- {item}")
    else:
        lines.append("P2 課題なし")
    lines.append("")

    # P3
    lines += ["## 🟢 P3 — 中長期で検討", ""]
    if p3_items:
        for item in p3_items:
            lines.append(f"- {item}")
    else:
        lines.append("P3 課題なし")
    lines.append("")

    # 強み
    lines += ["## 強みと継承すべき点", ""]
    if strengths:
        for s in strengths[:10]:
            lines.append(f"- {s}")
    else:
        lines.append("（分析中に明確な強みが特定されませんでした）")
    lines.append("")

    # Red Team
    if red_team_attacks:
        lines += ["## Skeptical First-Timer の視点から", ""]
        vector_labels = {
            "clarity_attacker": "Clarity Attacker（明確さへの攻撃）",
            "trust_destroyer":  "Trust Destroyer（信頼への攻撃）",
            "action_blocker":   "Action Blocker（行動障壁への攻撃）",
        }
        rebuttal_map = {r["vector"]: r["rebuttal"] for r in specialist_responses}

        for attack_item in red_team_attacks:
            vector = attack_item.get("vector", "")
            label = vector_labels.get(vector, vector)
            attack_text = attack_item.get("attack", "")
            rebuttal = rebuttal_map.get(vector, "（応答なし）")
            lines += [
                f"### {label}",
                "",
                f"**攻撃**: {attack_text}",
                "",
                f"**評価**: {rebuttal}",
                "",
            ]

    # 競合比較
    if competitor_url and competitor_data:
        c_title = competitor_data.get("page_title", "")
        lines += [
            "## 競合比較",
            "",
            f"競合 URL: {competitor_url}",
            f"競合サイトタイトル: {c_title}",
            "",
            "（詳細な差分は Competitive Positioning Analyst のスコアに反映されています）",
            "",
        ]

    # 技術メトリクス補足
    if metrics:
        load_ms = int(metrics.get("load_time_ms", 0))
        ttfb = int(metrics.get("ttfb", 0))
        size_kb = metrics.get("page_size_kb", 0)
        lines += [
            "## パフォーマンスメトリクス（実測値）",
            "",
            f"- ページロード時間: {load_ms}ms",
            f"- TTFB: {ttfb}ms",
            f"- ページサイズ: {size_kb}KB",
            "",
        ]

    return "\n".join(lines)


def save_report(report: str, url: str, report_dir: str) -> Path:
    """レポートを Markdown ファイルとして保存する"""
    report_path = Path(report_dir).expanduser()
    report_path.mkdir(parents=True, exist_ok=True)

    domain = urlparse(url).netloc.replace("www.", "")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{domain}.md"
    filepath = report_path / filename
    filepath.write_text(report, encoding="utf-8")
    return filepath
