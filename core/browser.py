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

    async def extract_main_content(self, page) -> str:
        """
        Google翻訳ウィジェット・nav/header/footer等のノイズを除去した上で
        本文テキストを取得する。DOM操作はクローン上で行い元ページに影響しない。
        """
        text = await page.evaluate("""
            () => {
                const NOISE_SELECTORS = [
                    '#google_translate_element', '.goog-te-combo',
                    '.goog-te-banner-frame', '.skiptranslate', '.goog-te-gadget',
                    'select', '[class*="language"]', '[id*="language"]',
                    '[class*="translate"]', '[id*="translate"]',
                    'nav', 'header', 'footer',
                    'script', 'style', 'noscript', 'iframe',
                    '#wpadminbar', '.wp-admin-bar',
                ];
                const clone = document.body.cloneNode(true);
                NOISE_SELECTORS.forEach(sel => {
                    clone.querySelectorAll(sel).forEach(el => el.remove());
                });
                const mainSelectors = [
                    'main', 'article', '#content', '.content',
                    '#main', '.main', '[role="main"]'
                ];
                for (const sel of mainSelectors) {
                    const el = clone.querySelector(sel);
                    if (el && el.innerText.trim().length > 200) {
                        return el.innerText.trim();
                    }
                }
                return clone.innerText.trim();
            }
        """)
        return text or ""

    async def extract_structured_data(self, page) -> dict:
        """
        JSON-LD構造化データを取得し、営業時間・料金・評価などを抽出する。
        Schema.org準拠のサイトでは本文テキストより信頼性の高い情報源となる。
        """
        raw_jsonld = await page.evaluate("""
            () => {
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                return Array.from(scripts).map(s => {
                    try { return JSON.parse(s.textContent); }
                    catch(e) { return null; }
                }).filter(Boolean);
            }
        """)
        extracted: dict = {}
        for item in raw_jsonld:
            if not isinstance(item, dict):
                continue
            if item.get("@type") in [
                "LocalBusiness", "Store", "Restaurant", "PhotoStudio",
                "Organization", "ProfessionalService",
            ]:
                extracted["business_name"] = item.get("name", "")
                extracted["address"] = item.get("address", {})
                extracted["telephone"] = item.get("telephone", "")
                extracted["price_range"] = item.get("priceRange", "")
                extracted["founding_date"] = item.get("foundingDate", "")
                hours = item.get("openingHours", item.get("openingHoursSpecification", []))
                if hours:
                    extracted["opening_hours"] = hours
                rating = item.get("aggregateRating", {})
                if rating:
                    extracted["aggregate_rating"] = {
                        "value": rating.get("ratingValue", ""),
                        "count": rating.get("reviewCount", rating.get("ratingCount", "")),
                        "best": rating.get("bestRating", 5),
                    }
            offers = item.get("offers", item.get("hasOfferCatalog", {}))
            if offers:
                extracted["offers"] = offers
        return extracted

    async def _crawl_subpages(self, browser, page, base_url: str, max_pages: int = 3) -> list:
        """
        ナビゲーションリンクを抽出し、最大 max_pages 件のサブページを収集する。
        アンカーリンク・重複パス・汎用ラベル・コンテンツ不足ページを除外する。
        """
        import re as _re

        base_domain = urlparse(base_url).netloc
        base_path = urlparse(base_url).path.rstrip("/")

        EXCLUDE_PATTERNS = [
            r"^#",
            r"javascript:",
            r"\.(jpg|png|pdf|svg|gif|zip|mp4|webp)$",
            r"/(wp-admin|admin|login|logout|cart|checkout)",
            r"[?&](page|p)=\d+",
            r"#",
        ]
        CONTENT_INDICATORS = [
            "service", "works", "gallery", "portfolio", "about", "contact",
            "fee", "price", "menu", "product", "news", "blog", "profile",
            "サービス", "料金", "実績", "会社", "ギャラリー", "作品",
        ]
        GENERIC_LABELS = {"menu", "home", "top", "×", "close", "open", "toggle", "back", ""}

        nav_links = await page.evaluate("""
            () => {
                const links = [];
                const seen = new Set();
                const selectors = ['nav a[href]', 'header a[href]', '.menu a[href]', '#menu a[href]'];
                for (const sel of selectors) {
                    document.querySelectorAll(sel).forEach(a => {
                        const href = a.getAttribute('href');
                        const text = a.innerText.trim();
                        if (href && text && !seen.has(href)) {
                            seen.add(href);
                            links.push({href: a.href, text: text, pathname: a.pathname});
                        }
                    });
                }
                return links;
            }
        """)

        def is_valid(link: dict) -> bool:
            href = link.get("href", "")
            text = link.get("text", "")
            pathname = link.get("pathname", "").rstrip("/")
            for pat in EXCLUDE_PATTERNS:
                if _re.search(pat, href, _re.IGNORECASE):
                    return False
            if urlparse(href).netloc != base_domain:
                return False
            if pathname == base_path or pathname in ("", "/"):
                return False
            if len(text) <= 1:
                return False
            if text.lower() in GENERIC_LABELS:
                return False
            return True

        def content_score(link: dict) -> int:
            combined = (link.get("href", "") + link.get("text", "")).lower()
            return sum(1 for kw in CONTENT_INDICATORS if kw in combined)

        valid_links = [l for l in nav_links if is_valid(l)]
        valid_links.sort(key=content_score, reverse=True)

        # パス重複除去
        seen_paths: set = set()
        unique_links = []
        for link in valid_links:
            path = urlparse(link["href"]).path.rstrip("/")
            if path not in seen_paths:
                seen_paths.add(path)
                unique_links.append(link)

        subpage_data = []
        for link in unique_links[:max_pages]:
            try:
                sub_page = await browser.new_page()
                await sub_page.goto(link["href"], wait_until="domcontentloaded", timeout=15000)
                await sub_page.wait_for_timeout(1500)
                sub_text = await self.extract_main_content(sub_page)
                sub_html = await sub_page.content()
                # コンテンツが極端に少ないページ（200文字未満）は除外
                if len(sub_text.strip()) < 200:
                    await sub_page.close()
                    continue
                subpage_data.append({
                    "url": link["href"],
                    "nav_label": link["text"],
                    "text_content": sub_text[:8000],  # Fix C: 3000→8000
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

            # テキスト・HTML 取得（ノイズ除去済みコンテンツ）
            page_text = await self.extract_main_content(page)
            page_html = await page.content()

            # JSON-LD 構造化データ取得
            structured_data = await self.extract_structured_data(page)

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
            "page_text": page_text[:10000],
            "page_html": page_html[:12000],
            "screenshot_path": str(screenshot_path),
            "mobile_screenshot_path": str(mobile_screenshot_path),
            "page_load_metrics": metrics,
            "structured_data": structured_data,
            "subpages": subpages,
        }

    def collect_sync(self, url: str, task_id: str, crawl_subpages: bool = False, crawl_max: int = 3) -> dict:
        """同期インターフェース: asyncio.run() で collect() を呼び出す"""
        return asyncio.run(self.collect(url, task_id, crawl_subpages, crawl_max))
