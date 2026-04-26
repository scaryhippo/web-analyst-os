"""
Web Analyst OS — ターミナル UI
Rich を使ってフェーズ進捗・エージェント発言・スコアカードを表示する。
"""
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule
from rich import box

console = Console()

AGENT_LABELS = {
    "conversion_architect": "Conversion Architect",
    "ux_auditor":           "UX Auditor",
    "brand_copy_analyst":   "Brand & Copy Analyst",
    "technical_auditor":    "Technical Auditor",
    "competitive_analyst":  "Competitive Positioning Analyst",
    "red_team":             "Skeptical First-Timer",
}

AGENT_COLORS = {
    "conversion_architect": "cyan",
    "ux_auditor":           "green",
    "brand_copy_analyst":   "magenta",
    "technical_auditor":    "yellow",
    "competitive_analyst":  "blue",
    "red_team":             "bright_red",
}


def print_banner(url: str, version: str = "1.0.0"):
    console.print()
    console.print(Panel(
        Text(f"Web Analyst OS v{version}", justify="center", style="bold white"),
        subtitle="AI マルチエージェント Web 分析システム",
        border_style="bright_blue",
        padding=(1, 4),
    ))
    console.print(f"  対象 URL: [bold cyan]{url}[/bold cyan]")
    console.print("  " + "━" * 44)
    console.print()


def print_phase_header(phase: str):
    console.print()
    console.print(Rule(f"[bold bright_blue]{phase}[/bold bright_blue]", style="bright_blue"))


def print_agent_preview(agent: str, preview: str, score: int = None):
    color = AGENT_COLORS.get(agent, "white")
    label = AGENT_LABELS.get(agent, agent)
    score_str = f"  スコア: {score}/100" if score is not None else ""
    console.print(
        f"  [bold {color}][{label}][/bold {color}]{score_str}\n"
        f"  [dim]{preview}[/dim]"
    )


def print_red_team_attack(vector: str, attack: str):
    labels = {
        "clarity_attacker": "Clarity Attacker",
        "trust_destroyer":  "Trust Destroyer",
        "action_blocker":   "Action Blocker",
    }
    label = labels.get(vector, vector)
    preview = attack[:120] + ("..." if len(attack) > 120 else "")
    console.print(f"  [bold bright_red][{label}][/bold bright_red] [dim]{preview}[/dim]")


def print_collection_result(metrics: dict, desktop_path: str, mobile_path: str):
    load_ms = int(metrics.get("load_time_ms", 0))
    size_kb = metrics.get("page_size_kb", 0)
    console.print(f"  [green]✓[/green] デスクトップ スクリーンショット保存: [dim]{desktop_path}[/dim]")
    console.print(f"  [green]✓[/green] モバイル スクリーンショット保存: [dim]{mobile_path}[/dim]")
    console.print(f"  [green]✓[/green] ページロード: {load_ms}ms | ページサイズ: {size_kb}KB")


def print_error(message: str):
    console.print(f"[red bold]エラー:[/red bold] {message}")


def print_report_saved(filepath: str, elapsed: float):
    console.print()
    console.print(f"  [bold green]✅ 分析完了[/bold green] ({elapsed:.0f}秒)")
    console.print(f"  レポート: [cyan]{filepath}[/cyan]")
    console.print()
