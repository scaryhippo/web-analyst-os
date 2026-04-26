"""
Web Analyst OS — レポート生成・整形
"""
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def _score_bar(score: int) -> str:
    """スコアを視覚的なバーで表現する"""
    filled = round(score / 10)
    return "█" * filled + "░" * (10 - filled)


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

    score_labels = [
        ("conversion",  "コンバージョン設計"),
        ("ux",          "UX・使いやすさ"),
        ("brand_copy",  "ブランド・コピー"),
        ("technical",   "技術・パフォーマンス"),
        ("competitive", "競合ポジショニング"),
    ]

    lines = [
        "# Web Analyst OS — 分析レポート",
        f"分析日時: {now}",
        f"対象 URL: {url}",
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
        executive_summary,
        "",
    ]

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
