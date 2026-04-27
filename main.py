#!/usr/bin/env python3
"""
Web Analyst OS v1.1.0 — CLI エントリーポイント

使用例:
  python main.py https://scaryhippo.jp
  python main.py https://scaryhippo.jp --site-type consulting
  python main.py https://scaryhippo.jp --competitor https://competitor.com
  python main.py https://scaryhippo.jp --focus conversion
  python main.py https://scaryhippo.jp --focus ux --no-red-team
  python main.py --help
"""
import argparse
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from core.llm_router import load_config
from core.report import save_report
from interface.cli import (
    console,
    print_banner,
    print_phase_header,
    print_agent_preview,
    print_red_team_attack,
    print_collection_result,
    print_error,
    print_report_saved,
)


def build_initial_state(
    url: str,
    competitor_url: str,
    focus: str,
    task_id: str,
    run_red_team: bool,
    site_type: str = "transactional",
    crawl_subpages: bool = False,
    crawl_max: int = 3,
) -> dict:
    return {
        "target_url": url,
        "competitor_url": competitor_url or None,
        "focus": focus,
        "task_id": task_id,
        "run_red_team": run_red_team,
        "site_type": site_type,
        "crawl_subpages": crawl_subpages,
        "crawl_max": crawl_max,
        "subpages": [],
        "structured_data": {},
        "competitive_analysis": "",
        "competitor_title": "",
        "competitor_scores": {},
        # Phase 0（初期化）
        "page_title": "",
        "page_meta_description": "",
        "page_text": "",
        "page_html": "",
        "screenshot_path": "",
        "mobile_screenshot_path": "",
        "page_load_metrics": {},
        "competitor_data": None,
        # Phase 1
        "messages": [],
        # Phase 2
        "red_team_attacks": [],
        "specialist_responses": [],
        # Phase 3
        "scores": {},
        "overall_score": 0,
        "p1_items": [],
        "p2_items": [],
        "p3_items": [],
        "strengths": [],
        "executive_summary": "",
        # Phase 4
        "final_report": "",
        # メタ
        "current_phase": "start",
        "error": None,
    }


def run_analysis(url: str, competitor_url: str = "", focus: str = "all", run_red_team: bool = True, site_type: str = "transactional", crawl_subpages: bool = False, crawl_max: int = 3):
    config = load_config()
    version = config.get("system_version", "1.0.0")

    print_banner(url, version)

    task_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    initial_state = build_initial_state(url, competitor_url, focus, task_id, run_red_team, site_type, crawl_subpages, crawl_max)

    # グラフ実行（LangGraph はストリーミングせず invoke で実行）
    print_phase_header("[Phase 0] ブラウザでページを収集中...")

    from core.graph import create_analyst_graph
    graph = create_analyst_graph()

    # LangGraph の .stream() でノードごとの結果を受け取る
    final_state = {}
    phase1_shown = False
    phase2_shown = False
    phase3_shown = False

    try:
        for chunk in graph.stream(initial_state, stream_mode="updates"):
            for node_name, updates in chunk.items():
                if not isinstance(updates, dict):
                    continue

                current_phase = updates.get("current_phase", "")
                error = updates.get("error")

                # Phase 0 完了
                if current_phase == "phase0_complete":
                    metrics = updates.get("page_load_metrics", {})
                    desktop = updates.get("screenshot_path", "")
                    mobile = updates.get("mobile_screenshot_path", "")
                    print_collection_result(metrics, desktop, mobile)

                # Phase 0 エラー
                if error:
                    print_error(
                        f"{error}\n\n"
                        "確認事項:\n"
                        "  ・URL が到達可能か確認してください\n"
                        "  ・タイムアウト設定: analyst_config.yaml → browser.timeout_ms\n"
                        "  ・ネットワーク環境を確認してください"
                    )
                    return

                # Phase 1 開始（最初のメッセージが来たとき）
                new_messages = updates.get("messages", [])
                if new_messages and not phase1_shown:
                    print_phase_header("[Phase 1] 専門エージェントが並列分析中...")
                    phase1_shown = True

                # Phase 1: エージェントプレビュー表示
                show_preview = config.get("output", {}).get("show_agent_preview", True)
                preview_chars = config.get("output", {}).get("agent_preview_chars", 120)
                if show_preview:
                    for msg in new_messages:
                        agent = msg.get("agent", "")
                        summary = msg.get("summary", "")
                        score = msg.get("score")
                        preview = summary[:preview_chars]
                        if preview:
                            print_agent_preview(agent, preview, score)

                # Phase 2: Red Team
                red_team_attacks = updates.get("red_team_attacks", [])
                if red_team_attacks and not phase2_shown:
                    print_phase_header("[Phase 2] Skeptical First-Timer が攻撃中...")
                    phase2_shown = True
                    for attack_item in red_team_attacks:
                        print_red_team_attack(
                            attack_item.get("vector", ""),
                            attack_item.get("attack", ""),
                        )

                # Phase 3: スコア計算
                if current_phase == "phase3_complete" and not phase3_shown:
                    print_phase_header("[Phase 3] スコア計算・優先度分類中...")
                    phase3_shown = True

                # Phase 4: レポート生成
                if current_phase == "completed":
                    print_phase_header("[Phase 4] レポート生成中...")

                final_state.update(updates)

    except KeyboardInterrupt:
        console.print("\n[yellow]中断されました[/yellow]")
        return
    except Exception as e:
        print_error(f"グラフ実行エラー: {e}")
        import traceback
        traceback.print_exc()
        return

    # レポート保存
    report = final_state.get("final_report", "")
    if not report:
        print_error("レポートが生成されませんでした")
        return

    report_dir = config.get("output", {}).get("report_dir", "~/Projects/web-analyst-os/reports")
    filepath = save_report(report, url, report_dir)
    elapsed = time.time() - start_time
    print_report_saved(str(filepath), elapsed)

    # ターミナルにもサマリー表示
    from rich.panel import Panel
    from rich import box as rbox
    overall = final_state.get("overall_score", 0)
    scores = final_state.get("scores", {})
    score_lines = [
        f"  総合スコア: {overall}/100",
        "",
        f"  コンバージョン設計 : {scores.get('conversion', '—')}/100",
        f"  UX・使いやすさ    : {scores.get('ux', '—')}/100",
        f"  ブランド・コピー  : {scores.get('brand_copy', '—')}/100",
        f"  技術・パフォーマンス: {scores.get('technical', '—')}/100",
        f"  競合ポジショニング: {scores.get('competitive', '—')}/100",
    ]
    console.print(Panel(
        "\n".join(score_lines),
        title="[bold green]スコアカード[/bold green]",
        border_style="green",
        box=rbox.ROUNDED,
        padding=(0, 2),
    ))


def main():
    parser = argparse.ArgumentParser(
        description="Web Analyst OS — AI マルチエージェント Web 分析",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""使用例:
  python main.py https://scaryhippo.jp
  python main.py https://scaryhippo.jp --site-type consulting
  python main.py https://atelier-a3.jp  --site-type portfolio
  python main.py https://scaryhippo.jp --competitor https://example.com
  python main.py https://scaryhippo.jp --focus conversion
  python main.py https://scaryhippo.jp --no-red-team
""",
    )
    parser.add_argument("url", help="分析対象の URL")
    parser.add_argument(
        "--competitor", metavar="URL",
        help="競合サイトの URL（指定時: 競合比較モード）",
        default="",
    )
    parser.add_argument(
        "--focus",
        choices=["all", "conversion", "ux", "brand", "technical"],
        default="all",
        help="分析フォーカス（デフォルト: all）",
    )
    parser.add_argument(
        "--no-red-team",
        action="store_true",
        help="Skeptical First-Timer（Phase 2）をスキップ",
    )
    parser.add_argument(
        "--site-type",
        choices=["transactional", "brand", "portfolio", "consulting"],
        default="transactional",
        dest="site_type",
        help=(
            "サイトのビジネスモデルタイプ（デフォルト: transactional）\n"
            "  transactional: 流入型BtoB/BtoC\n"
            "  consulting:    高単価・選別型（価格非掲載を減点しない）\n"
            "  brand:         ブランディング・認知目的\n"
            "  portfolio:     作品集・実績提示目的"
        ),
    )
    parser.add_argument(
        "--crawl-subpages",
        action="store_true",
        default=False,
        dest="crawl_subpages",
        help="ナビゲーションリンクから最大 --crawl-max 件のサブページを追加収集する",
    )
    parser.add_argument(
        "--crawl-max",
        type=int,
        default=3,
        dest="crawl_max",
        help="--crawl-subpages 使用時の最大収集サブページ数（デフォルト: 3）",
    )
    args = parser.parse_args()

    run_analysis(
        url=args.url,
        competitor_url=args.competitor,
        focus=args.focus,
        run_red_team=not args.no_red_team,
        site_type=args.site_type,
        crawl_subpages=args.crawl_subpages,
        crawl_max=args.crawl_max,
    )


if __name__ == "__main__":
    main()
