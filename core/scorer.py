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

    result = {**scores, "overall": round(overall)}
    validate_score_diversity(scores)
    return result


def validate_score_diversity(scores: dict) -> bool:
    """全エージェントのスコアが5点以内に収まる場合に警告を出す"""
    values = [v for v in scores.values() if isinstance(v, (int, float))]
    if len(values) < 3:
        return True
    score_range = max(values) - min(values)
    if score_range <= 5:
        print(f"  [Scorer] ⚠ スコア分布が狭い（レンジ: {score_range}点）。エージェント独立性を確認してください。")
        return False
    return True
