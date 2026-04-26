"""
Web Analyst OS — Playwright ブラウザ統合 (Phase 0)
URL のページデータ・メトリクス・スクリーンショットを収集する。
"""
import asyncio
import socket
import time
from pathlib import Path
from urllib.parse import urlparse


def _resolve_host_rule(url: str) -> list:
    """
    Playwright/Chromium が DNS を解決できない場合のフォールバック。
    システムの DNS でホストを解決し --host-resolver-rules 形式で返す。
    失敗した場合は空リストを返す。
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        results = socket.getaddrinfo(hostname, port, socket.AF_INET)
        if results:
            ip = results[0][4][0]
            return [f"MAP {hostname} {ip}"]
    except Exception:
        pass
    return []


class BrowserCollector:
    """
    Playwright を使って URL を解析し、エージェントが必要とするデータを収集する。
    """

    def __init__(self, config: dict):
        self.config = config["browser"]
        self.screenshot_dir = Path(config["output"]["screenshot_dir"]).expanduser()
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def _crawl_subpages(self, browser, page, base_url: str, max_pages: int = 3) -> list:
        """
        ナビゲーションリンクを抽出し、最大 max_pages 件のサブページを収集する。
        nav/header 内のリンクを優先し、外部ドメイン・画像・PDFを除外する。
        """
        base_domain = urlparse(base_url).netloc

        nav_links = await page.evaluate("""
            () => {
                const links = [];
                document.querySelectorAll('nav a[href], header a[href]').forEach(a => {
                    if (a.href && !a.href.startsWith('#'))
                        links.push({href: a.href, text: a.innerText.trim()});
                });
                if (links.length < 5) {
                    document.querySelectorAll('a[href]').forEach(a => {
                        if (a.href && !a.href.startsWith('#')) {
                            const exists = links.some(l => l.href === a.href);
                            if (!exists) links.push({href: a.href, text: a.innerText.trim()});
                        }
                    });
                }
                return links;
            }
        """)

        internal_links = [
            l for l in nav_links
            if urlparse(l["href"]).netloc == base_domain
            and not any(l["href"].endswith(ext) for ext in (".jpg", ".png", ".pdf", ".svg", ".webp"))
            and l["href"].rstrip("/") != base_url.rstrip("/")
        ]

        subpage_data = []
        for link in internal_links[:max_pages]:
            try:
                sub_page = await browser.new_page()
                await sub_page.goto(link["href"], wait_until="domcontentloaded", timeout=15000)
                await sub_page.wait_for_timeout(1500)
                sub_text = await sub_page.inner_text("body")
                sub_html = await sub_page.content()
                subpage_data.append({
                    "url": link["href"],
                    "nav_label": link["text"],
                    "text_content": sub_text[:3000],
                    "page_size_bytes": len(sub_html.encode("utf-8")),
                })
                await sub_page.close()
            except Exception as e:
                print(f"  [Browser] サブページスキップ: {link['href']} ({e})")

        return subpage_data

    async def collect(self, url: str, task_id: str, crawl_subpages: bool = False, crawl_max: int = 3) -> dict:
        """
        指定 URL のデータを収集して返す。
        crawl_subpages=True の場合はナビリンクから最大 crawl_max 件のサブページも収集する。
        """
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            # DNS 解決失敗時のフォールバック: システム DNS で事前解決して注入
            host_rules = _resolve_host_rule(url)
            launch_args = []
            if host_rules:
                launch_args.append(f"--host-resolver-rules={','.join(host_rules)}")

            browser = await p.chromium.launch(
                headless=self.config["headless"],
                args=launch_args if launch_args else None,
            )

            # デスクトップ収集
            context = await browser.new_context(
                viewport={
                    "width": self.config["viewport_width"],
                    "height": self.config["viewport_height"]
                }
            )
            page = await context.new_page()

            # パフォーマンス計測開始
            start_time = time.time()
            await page.goto(
                url,
                wait_until=self.config["wait_for_load"],
                timeout=self.config["timeout_ms"],
            )
            load_time_ms = (time.time() - start_time) * 1000

            # メタデータ取得
            title = await page.title()
            meta_el = await page.query_selector('meta[name="description"]')
            meta_desc = ""
            if meta_el:
                meta_desc = await meta_el.get_attribute("content") or ""

            # テキスト・HTML 取得
            page_text = await page.inner_text("body")
            page_html = await page.content()

            # Core Web Vitals 相当の簡易計測
            metrics = await page.evaluate("""() => {
                const nav = performance.getEntriesByType('navigation')[0];
                return {
                    ttfb: nav ? nav.responseStart - nav.requestStart : 0,
                    dom_content_loaded: nav ? nav.domContentLoadedEventEnd : 0,
                    page_load: nav ? nav.loadEventEnd : 0,
                };
            }""")
            metrics["load_time_ms"] = load_time_ms

            # ページサイズ
            page_size = len(page_html.encode("utf-8")) / 1024
            metrics["page_size_kb"] = round(page_size, 1)

            # デスクトップスクリーンショット
            screenshot_path = self.screenshot_dir / f"{task_id}_desktop.png"
            await page.screenshot(
                path=str(screenshot_path),
                full_page=self.config["screenshot_full_page"],
            )

            # サブページクローリング（同一ブラウザセッション内で実行）
            subpages = []
            if crawl_subpages:
                print(f"  [Browser] サブページを収集中（最大{crawl_max}件）...")
                subpages = await self._crawl_subpages(browser, page, url, crawl_max)
                for sp in subpages:
                    label = sp.get("nav_label") or sp["url"]
                    size_kb = round(sp["page_size_bytes"] / 1024, 1)
                    print(f"  [Browser] ✓ {label}: {sp['url']} ({size_kb}KB)")

            await context.close()

            # モバイルスクリーンショット
            mobile_context = await browser.new_context(
                viewport={
                    "width": self.config["mobile_viewport_width"],
                    "height": self.config["mobile_viewport_height"]
                },
                is_mobile=True,
            )
            mobile_page = await mobile_context.new_page()
            await mobile_page.goto(
                url,
                wait_until=self.config["wait_for_load"],
                timeout=self.config["timeout_ms"],
            )
            mobile_screenshot_path = self.screenshot_dir / f"{task_id}_mobile.png"
            await mobile_page.screenshot(
                path=str(mobile_screenshot_path),
                full_page=self.config["screenshot_full_page"],
            )
            await mobile_context.close()
            await browser.close()

        return {
            "page_title": title,
            "page_meta_description": meta_desc,
            "page_text": page_text[:8000],      # トークン節約のため上限設定
            "page_html": page_html[:12000],
            "screenshot_path": str(screenshot_path),
            "mobile_screenshot_path": str(mobile_screenshot_path),
            "page_load_metrics": metrics,
            "subpages": subpages,
        }

    def collect_sync(self, url: str, task_id: str, crawl_subpages: bool = False, crawl_max: int = 3) -> dict:
        """同期インターフェース: asyncio.run() で collect() を呼び出す"""
        return asyncio.run(self.collect(url, task_id, crawl_subpages, crawl_max))
