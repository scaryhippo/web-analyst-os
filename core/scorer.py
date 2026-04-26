"""
Web Analyst OS — スコアカード計算
"""


def calculate_scores(messages: list, config: dict) -> dict:
    weights = config["score_weights"]
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
    ) / total_weight

    return {**scores, "overall": round(overall)}
