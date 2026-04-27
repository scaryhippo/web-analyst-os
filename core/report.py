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


def extract_competitive_summary(text: str) -> str:
    """competitive_analyst の出力から <competitive_summary> タグの内容を抽出する"""
    match = re.search(r'<competitive_summary>(.*?)</competitive_summary>', text, re.DOTALL)
    return match.group(1).strip() if match else ""


def generate_score_comparison_table(self_scores: dict, competitor_scores: dict, competitor_title: str = "競合サイト") -> str:
    """自社と競合のスコアを横並びで比較する Markdown テーブルを生成する"""
    AXES = [
        ("conversion", "コンバージョン設計"),
        ("ux",         "UX・使いやすさ"),
        ("brand_copy", "ブランド・コピー"),
        ("technical",  "技術・パフォーマンス"),
        ("competitive","競合ポジショニング"),
    ]
    lines = [
        "### スコア比較\n",
        f"| 評価軸 | 自社 | {competitor_title} | 差分 |",
        "|---|---|---|---|",
    ]
    total_s, total_c = 0, 0
    for key, label in AXES:
        s = self_scores.get(key, 0)
        c = competitor_scores.get(key, 0)
        diff = s - c
        diff_str = f"**+{diff}**" if diff > 0 else (f"**{diff}**" if diff < 0 else "±0")
        lines.append(f"| {label} | {s}/100 | {c}/100 | {diff_str} |")
        total_s += s
        total_c += c
    n = len(AXES)
    avg_s, avg_c = total_s // n, total_c // n
    diff_avg = avg_s - avg_c
    diff_str = f"**+{diff_avg}**" if diff_avg > 0 else (f"**{diff_avg}**" if diff_avg < 0 else "±0")
    lines.append(f"| **総合** | **{avg_s}/100** | **{avg_c}/100** | {diff_str} |")
    return "\n".join(lines)


def clean_skeptical_output(text: str) -> str:
    """
    Skeptical First-Timer の出力から自己修正（再判定）の痕跡を除去する。
    二段階判定が出た場合は最終判定のみに統一する。
    """
    judgments = re.findall(r'判定:\s*(RESOLVED|PARTIALLY_RESOLVED|UNRESOLVED)', text)
    if len(judgments) >= 2:
        final_judgment = judgments[-1]
        # 「---」以降の再判定ブロックを削除
        text = re.sub(r'\n+---\n+\*\*再判定.*', '', text, flags=re.DOTALL)
        # 最初の判定を最終判定に書き換え
        text = re.sub(
            r'判定:\s*(RESOLVED|PARTIALLY_RESOLVED|UNRESOLVED)',
            f'判定: {final_judgment}',
            text,
            count=1,
        )
    # 「**再判定: XXX**」という表記そのものを除去
    text = re.sub(r'\*\*再判定:\s*(RESOLVED|PARTIALLY_RESOLVED|UNRESOLVED)\*\*\n*', '', text)
    return text.strip()


def clean_arrow_formatting(text: str) -> str:
    """'→ →' '→→' などの二重矢印を単一の '→' に正規化する"""
    return re.sub(r'→\s*→', '→', text)


def clean_items(items: list) -> list:
    return [clean_arrow_formatting(item) for item in items]


# ─── Fix 3 / Fix B: P2・P3 品質フィルタ + 称賛観察の分離 ──────────────────────

_POSITIVE_PATTERNS = [
    r'は非常に優れ', r'は優れ(た|てい)', r'は良好', r'は適切に設定',
    r'は正しく実装', r'は十分', r'は高水準', r'は優秀', r'問題はない',
    r'に問題が?な[いく]', r'は許容範囲', r'は優位', r'非常に高速',
    r'は最適化されて', r'は軽量', r'は問題なし',
]


def is_positive_observation(item: str) -> bool:
    """矢印の後が現状肯定文（称賛観察）かを判定する"""
    if '→' not in item:
        return False
    after_arrow = item.split('→', 1)[1]
    for pattern in _POSITIVE_PATTERNS:
        if re.search(pattern, after_arrow):
            return True
    return False


def filter_section_quality(items: list) -> tuple:
    """
    スコアのみ項目を除去し、称賛観察を強みセクション用に分離する。
    Returns: (改善推奨アイテムリスト, 強みとして追加すべきアイテムリスト)
    """
    filtered = []
    praise_items = []
    for item in items:
        if is_positive_observation(item):
            praise_items.append(item)
        elif "→" in item:
            filtered.append(item)
        elif re.match(r"- \[(?!スコア)[^\]]+\]", item) and len(item) > 60:
            filtered.append(item)
    return filtered, praise_items


# 後方互換エイリアス（戻り値が変わったため注意）
def filter_p2_quality(items: list) -> list:
    filtered, _ = filter_section_quality(items)
    return filtered


# ─── Fix A: 重複除去（トピックグループベース、P1/P2/P3 統合処理） ─────────────

DEDUP_TOPIC_GROUPS = [
    # 画像・ページサイズ最適化
    ["WebP", "遅延読み込み", "Lazy", "lazy", "ページサイズ", "KB", "画像最適化", "300KB"],
    # 社会的証明・トラストシグナル
    ["社会的証明", "トラスト", "実績数", "クライアント名", "導入施設", "受賞歴", "ロゴ"],
    # CTA・コンバージョン導線
    ["CTA", "主CTA", "コンバージョン導線", "問い合わせ.*導線", "READ THE MANIFESTO"],
    # 経歴・プロフィール検証
    ["経歴", "LinkedI", "在籍期間", "MBB.*ファーム", "CIO.*在任", "プロフィール"],
    # なりすましメール・警告バナー
    ["なりすまし", "警告バナー", "警告.*配置", "フィッシング"],
    # WORKSページ・ポートフォリオ不在
    ["WORKSページ", "ポートフォリオ.*確認", "作品.*不在", "作品.*見え", "ビジュアル.*不在"],
    # ナビゲーション・メニュー
    ["グローバルナビ", "ナビゲーション.*ラベル", "ナビ.*英語", "ナビ.*日本語"],
    # 価格・料金
    ["価格", "料金", "価格帯", "費用", "有償"],
    # フォーム・送信体験
    ["フォーム.*バリデーション", "送信.*フィードバック", "返信.*日数", "エラーメッセージ"],
    # 構造化データ・SEO
    ["構造化データ", "JSON-LD", "OGP", "Twitter Card", "meta description"],
    # パンくず・現在地
    ["パンくず", "breadcrumb", "現在地"],
    # タップターゲット・モバイル操作性
    ["タップターゲット", "44×44", "48×48", "モバイル.*タップ"],
    # フォーカス・アクセシビリティ
    ["focus-visible", "フォーカス表示", "キーボードナビ", "スクリーンリーダー", "WCAG"],
    # ターゲット分離
    ["BtoB.*BtoC", "施設担当者.*求職者", "ターゲット.*分離", "ターゲット.*分岐"],
    # H1・ヒーローコピーの明確性
    ["H1.*コピー", "ヒーロー.*5秒", "ファーストビュー.*伝わらない", "5秒以内.*伝わら"],
    # 英日混在トーン（Fix C 追加）
    ["英日混在", "英語・日本語", "言語統一", "トーン統一", "英語混在", "バイリンガル", "英語主体", "日本語主体"],
    # ナビゲーション不在（Fix C 追加）
    ["グローバルナビが", "ナビゲーションが.*ない", "固定ヘッダー", "スティッキー.*ナビ", "ナビがない"],
    # フォーム設計（Fix C 追加）
    ["インラインバリデーション", "送信後.*サンクス", "サンクスページ", "フォーム摩擦", "入力ガイダンス"],
    # セキュリティ認証（Fix C 追加）
    ["ISO27001", "ISMS", "第三者認証", "セキュリティ認証", "第三者監査"],
    # 定休日例外（Fix C 追加）
    ["定休日", "日曜.*祝日", "日祝", "要予約で承"],
]


def _match_topic_group(item_lower: str) -> int | None:
    """アイテムがどのトピックグループに属するかを返す（属さない場合は None）"""
    for group_idx, keywords in enumerate(DEDUP_TOPIC_GROUPS):
        for kw in keywords:
            try:
                if re.search(kw.lower(), item_lower):
                    return group_idx
            except re.error:
                if kw.lower() in item_lower:
                    return group_idx
    return None


def build_prioritized_items(p1_raw: list, p2_raw: list, p3_raw: list) -> tuple:
    """
    P1/P2/P3 を統合した状態でトピックレベル重複除去し、再分離する。
    P1 に出現したトピックは P2/P3 から除去される。
    """
    tagged = (
        [("P1", item) for item in p1_raw] +
        [("P2", item) for item in p2_raw] +
        [("P3", item) for item in p3_raw]
    )
    seen_groups: set = set()
    result_tagged = []

    for priority, item in tagged:
        group_idx = _match_topic_group(item.lower())
        if group_idx is None or group_idx not in seen_groups:
            result_tagged.append((priority, item))
            if group_idx is not None:
                seen_groups.add(group_idx)

    p1_out = [item for p, item in result_tagged if p == "P1"]
    p2_out = [item for p, item in result_tagged if p == "P2"]
    p3_out = [item for p, item in result_tagged if p == "P3"]
    return p1_out, p2_out, p3_out


# ─── Fix 2/B: P1/P2 上限キャップ ───────────────────────────────────────────

P1_MAX = 5
P2_MAX = 10


def cap_p1_items(p1_items: list, p2_items: list) -> tuple:
    """P1 を P1_MAX 件に絞り、超過分を P2 先頭に移動する"""
    if len(p1_items) <= P1_MAX:
        return p1_items, p2_items
    specific = [i for i in p1_items if not i.strip().lstrip("- ").startswith("[スコア")]
    score_only = [i for i in p1_items if i.strip().lstrip("- ").startswith("[スコア")]
    p1_final = specific[:P1_MAX]
    overflow = specific[P1_MAX:] + score_only
    return p1_final, overflow + p2_items


def cap_p2_items(p2_items: list, p3_items: list) -> tuple:
    """P2 を P2_MAX 件に絞り、超過分を P3 先頭に移動する"""
    if len(p2_items) <= P2_MAX:
        return p2_items, p3_items
    return p2_items[:P2_MAX], p2_items[P2_MAX:] + p3_items


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
    subpages = state.get("subpages", [])

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
    ]
    if subpages:
        sub_labels = " | ".join(
            sp.get("nav_label") or sp.get("url", "").split("/")[-2] or sp.get("url", "")
            for sp in subpages
        )
        lines.append(f"収集サブページ: {sub_labels}")
    lines += [
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

    # Fix C: 二重矢印クリーニング
    p1_items = clean_items(p1_items)
    p2_items = clean_items(p2_items)
    p3_items = clean_items(p3_items)

    # Fix A: P1/P2/P3 統合重複除去
    p1_items, p2_items, p3_items = build_prioritized_items(p1_items, p2_items, p3_items)

    # Fix 2: P1 キャップ → Fix B: P2 キャップ
    p1_items, p2_items = cap_p1_items(p1_items, p2_items)
    p2_items, p3_items = cap_p2_items(p2_items, p3_items)

    # Fix B: P2・P3 品質フィルタ + 称賛アイテムを強みへ分離
    p2_items, p2_praise = filter_section_quality(p2_items)
    p3_items, p3_praise = filter_section_quality(p3_items)
    strengths = strengths + [p.lstrip("- ") for p in p2_praise + p3_praise]

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
            rebuttal = clean_skeptical_output(rebuttal_map.get(vector, "（応答なし）"))
            lines += [
                f"### {label}",
                "",
                f"**攻撃**: {attack_text}",
                "",
                f"**評価**: {rebuttal}",
                "",
            ]

    # 競合比較（Fix A: 充実版）
    if competitor_url and competitor_data:
        comp_title = state.get("competitor_title") or competitor_data.get("page_title", "競合サイト")
        comp_scores = state.get("competitor_scores", {})
        comp_analysis_raw = state.get("competitive_analysis", "")

        lines += ["## 競合比較", "",
                  f"競合 URL: {competitor_url}",
                  f"競合サイトタイトル: {comp_title}",
                  ""]

        # スコア比較テーブル
        if comp_scores and scores:
            lines.append(generate_score_comparison_table(scores, comp_scores, comp_title))
            lines.append("")

        # 競合比較サマリー
        competitive_summary = extract_competitive_summary(comp_analysis_raw)
        if competitive_summary:
            lines += ["### 競合比較分析", "", competitive_summary, ""]
        else:
            lines += ["（詳細な差分は Competitive Positioning Analyst のスコアに反映されています）", ""]

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

    # Fix D: 外部プラットフォーム免責注記
    lines += [
        "## 分析上の注記",
        "",
        "本レポートは対象WebページのHTMLテキストコンテンツおよびJSON-LD構造化データに基づく分析です。",
        "以下の情報は本システムの収集範囲外となります：",
        "",
        "- Google マップ / 食べログ / Yelp 等の外部プラットフォームのレビュー・評価",
        "- SNS（Instagram / X / Facebook 等）の投稿・フォロワー数",
        "- iframe 内に表示される外部コンテンツ",
        "- ログイン・会員登録が必要なページのコンテンツ",
        "",
        "これらの情報は別途手動で確認し、分析を補完することを推奨します。",
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
