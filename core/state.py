"""
Web Analyst OS — LangGraph State 定義
全エージェントが共有するワークフロー状態。
"""
from typing import TypedDict, List, Dict, Optional, Any, Annotated
import operator


class AnalystState(TypedDict):
    # 入力
    target_url: str
    competitor_url: Optional[str]
    focus: str                        # "all" | "conversion" | "ux" | "brand" | "technical"
    task_id: str

    # Phase 0: ブラウザ収集データ
    page_title: str
    page_meta_description: str
    page_text: str                    # 本文テキスト（全ページ結合）
    page_html: str                    # 生 HTML（Technical Auditor 用）
    screenshot_path: str              # フルページスクリーンショットのパス
    mobile_screenshot_path: str
    page_load_metrics: Dict           # { lcp, fid, cls, ttfb, page_size_kb }
    competitor_data: Optional[Dict]   # competitor_url がある場合

    # Phase 1: 各専門家分析（差分追記）
    messages: Annotated[List[Dict], operator.add]

    # Phase 2: Red Team
    red_team_attacks: List[Dict]
    specialist_responses: List[Dict]

    # Phase 3: 統合
    scores: Dict[str, int]            # { conversion, ux, brand_copy, technical, competitive }
    overall_score: int
    p1_items: List[str]
    p2_items: List[str]
    p3_items: List[str]
    strengths: List[str]
    executive_summary: str
    final_report: str

    # サブページクローリング（--crawl-subpages 時のみ）
    subpages: List[Dict]

    # JSON-LD 構造化データ（営業時間・料金・評価等）
    structured_data: Dict

    # 競合比較（--competitor 指定時のみ）
    competitive_analysis: str   # competitive_analyst の生出力（<competitive_summary>抽出用）
    competitor_title: str       # 競合サイトのページタイトル
    competitor_scores: Dict     # 競合サイトの推定スコア（competitive_analyst が出力）

    # Phase 0.5: 評価次元プロファイル（v3.0 新設計）
    site_type_label: str        # 自由形式の人間向けラベル（採点には不使用）
    site_type_confidence: str   # "high" | "medium" | "low" | "explicit"
    site_type_signals: List     # 後方互換用（v3.0 では evaluation_profile が主）
    site_type_reasoning: str    # 判定理由
    evaluation_profile: Dict    # 10次元の評価ウェイト辞書（採点・優先度判定に使用）

    # --context オプション
    context: str                # 依頼者提供の分析コンテキスト（空の場合は ""）

    # メタ
    current_phase: str
    error: Optional[str]
    run_red_team: bool                # False の場合は Phase 2 をスキップ
    site_type: str                    # 後方互換用（v3.0 からは site_type_label を使用）
    crawl_subpages: bool
    crawl_max: int
