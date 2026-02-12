import logging
import re

from playwright.async_api import async_playwright

from app.scrapers.base import BaseScraper, ListingInfo, ScrapeResult

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"


def parse_price(text: str) -> float | None:
    match = re.search(r"\$?([\d,]+\.?\d*)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


class ManapoolScraper(BaseScraper):
    async def scrape(self, url: str) -> ScrapeResult:
        try:
            logger.info(f"Manapool: Fetching {url}")

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox"],
                )
                context = await browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1920, "height": 1080},
                )
                page = await context.new_page()

                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Wait for dynamic content to render
                await page.wait_for_timeout(5000)

                price = None
                available = False
                listings = []

                # Try to find "For Sale" listing rows with prices
                # Manapool renders listings dynamically; look for common price patterns
                price_selectors = [
                    "[class*='price']",
                    "[class*='Price']",
                    "[class*='listing'] [class*='price']",
                    "[class*='cost']",
                    "button:has-text('Add to Cart')",
                ]

                for selector in price_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        for el in elements:
                            text = await el.text_content()
                            if text:
                                parsed = parse_price(text.strip())
                                if parsed and parsed > 0:
                                    if price is None or parsed < price:
                                        price = parsed
                                    available = True
                                    listings.append(
                                        ListingInfo(
                                            title="Manapool Listing",
                                            price=parsed,
                                            link=url,
                                        )
                                    )
                    except Exception:
                        continue

                # Fallback: scan all text for dollar amounts near "Add to Cart"
                if not price:
                    try:
                        body_text = await page.text_content("body") or ""
                        # Look for prices in the page
                        all_prices = re.findall(r"\$(\d+\.?\d*)", body_text)
                        valid_prices = [float(p) for p in all_prices if float(p) > 0.5]
                        if valid_prices:
                            price = min(valid_prices)
                            available = True
                    except Exception:
                        pass

                # Check availability text
                try:
                    body_text = await page.text_content("body") or ""
                    lower = body_text.lower()
                    if "sold out" in lower or "out of stock" in lower or "no listings" in lower:
                        available = False
                    elif "add to cart" in lower:
                        available = True
                except Exception:
                    pass

                # Debug: log a snippet of the page
                try:
                    snippet = await page.text_content("body") or ""
                    logger.info(f"Manapool: page text length={len(snippet)}, first 500 chars: {snippet[:500]}")
                except Exception:
                    pass

                await browser.close()

            logger.info(
                f"Manapool: price={price}, available={available}, "
                f"listings={len(listings)}"
            )
            return ScrapeResult(
                price=price, available=available, listings=listings
            )

        except Exception as e:
            logger.error(f"Manapool scraper error: {e}")
            return ScrapeResult(error=str(e))
