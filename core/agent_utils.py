"""
Web Analyst OS v3.0 — エージェント共通ユーティリティ
評価次元プロファイルをエージェント向けの指示文に変換する。
"""

DIMENSION_LABELS = {
    "price_disclosure_weight":    "価格透明性の重要度",
    "cta_immediacy_weight":       "即時コンバージョンの重要度",
    "lead_qualification_weight":  "リード選別の重要度",
    "social_proof_weight":        "社会的証明の重要度",
    "credential_display_weight":  "資格・経歴表示の重要度",
    "portfolio_display_weight":   "作品・実績表示の重要度",
    "navigation_depth_weight":    "ナビゲーション深度の必要度",
    "mobile_optimization_weight": "モバイル最適化の重要度",
    "competitive_diff_weight":    "競合差別化の重要度",
    "trust_signal_weight":        "セキュリティ・信頼シグナルの重要度",
}

AGENT_RELEVANT_DIMENSIONS = {
    "conversion": [
        "price_disclosure_weight",
        "cta_immediacy_weight",
        "lead_qualification_weight",
        "trust_signal_weight",
    ],
    "ux": [
        "navigation_depth_weight",
        "mobile_optimization_weight",
        "portfolio_display_weight",
        "cta_immediacy_weight",
    ],
    "brand": [
        "social_proof_weight",
        "credential_display_weight",
        "portfolio_display_weight",
        "competitive_diff_weight",
    ],
    "technical": [
        "mobile_optimization_weight",
        "trust_signal_weight",
        "navigation_depth_weight",
    ],
    "competitive": [
        "competitive_diff_weight",
        "social_proof_weight",
        "credential_display_weight",
    ],
}


def build_profile_instruction(profile: dict, agent_type: str) -> str:
    """
    評価次元プロファイルをエージェント向けの優先度指示文に変換する。
    プロファイルが空の場合は空文字を返す。
    """
    if not profile:
        return ""

    relevant = AGENT_RELEVANT_DIMENSIONS.get(agent_type, list(profile.keys()))

    lines = [
        "【このサイト固有の評価プロファイル】",
        "以下の次元ウェイトに基づいてスコアリングと優先度判定を行うこと。",
        "1.0 が標準。2.0 は最重要、0.1 はほぼ不問を意味する。",
        "",
    ]

    for dim in relevant:
        val = profile.get(dim)
        if val is None:
            continue
        label = DIMENSION_LABELS.get(dim, dim)
        val_f = float(val)
        if val_f >= 1.5:
            guidance = "→ 欠如はP1候補。スコアへの影響大。"
        elif val_f >= 1.0:
            guidance = "→ 欠如はP2候補。標準的な重要度。"
        elif val_f >= 0.5:
            guidance = "→ 欠如はP3止まり。軽微な言及に留める。"
        else:
            guidance = "→ このサイトでは不問。指摘しない。"
        lines.append(f"- {label}: {val_f:.1f}  {guidance}")

    lines += [
        "",
        "【優先度判定のルール】",
        "- weight < 0.5 の次元に関する欠如は指摘しない（このサイトでは不要）",
        "- weight 0.5〜1.0 の次元: P3のみ（軽微な改善として言及）",
        "- weight 1.0〜1.5 の次元: P2候補（次スプリントで対処）",
        "- weight > 1.5 の次元: P1候補（即時対処が必要）",
        "- 上記ルールは採点の絶対基準ではなく、他の要因と総合して判断すること",
    ]

    return "\n".join(lines)
