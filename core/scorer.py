"""
Web Analyst OS — スコアカード計算
site_type_profiles から重みを動的に読み込む。
"""


def calculate_scores(messages: list, config: dict, site_type: str = "transactional") -> dict:
    # site_type_profiles から重みを取得、なければデフォルトの score_weights を使用
    profiles = config.get("site_type_profiles", {})
    profile = profiles.get(site_type, {})
    weights = profile.get("score_weights", config.get("score_weights", {}))

    agent_score_map = {
        "conversion_architect": "conversion",
        "ux_auditor":           "ux",
        "brand_copy_analyst":   "brand_copy",
        "technical_auditor":    "technical",
        "competitive_analyst":  "competitive",
    }
    scores = {}
    for msg in messages:
        agent = msg.get("agent")
        if agent in agent_score_map:
            key = agent_score_map[agent]
            scores[key] = msg.get("score", 50)

    # 加重平均（取得できなかった次元は 50 でフォールバック）
    total_weight = sum(weights.values())
    overall = sum(
        scores.get(k, 50) * weights.get(k, 0)
        for k in weights
    ) / total_weight if total_weight > 0 else 50

    return {**scores, "overall": round(overall)}
