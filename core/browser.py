"""
Web Analyst OS — Playwright ブラウザ統合 (Phase 0)
URL のページデータ・メトリクス・スクリーンショットを収集する。
"""
import asyncio
import time
from pathlib import Path


class BrowserCollector:
    """
    Playwright を使って URL を解析し、エージェントが必要とするデータを収集する。
    """

    def __init__(self, config: dict):
        self.config = config["browser"]
        self.screenshot_dir = Path(config["output"]["screenshot_dir"]).expanduser()
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def collect(self, url: str, task_id: str) -> dict:
        """
        指定 URL のデータを収集して返す。
        返り値: page_title, meta_description, page_text, page_html,
                screenshot_path, mobile_screenshot_path, load_metrics
        """
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.config["headless"])

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
        }

    def collect_sync(self, url: str, task_id: str) -> dict:
        """同期インターフェース: asyncio.run() で collect() を呼び出す"""
        return asyncio.run(self.collect(url, task_id))
