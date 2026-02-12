import logging
import re

from playwright.async_api import async_playwright

from app.scrapers.base import BaseScraper, DEFAULT_USER_AGENT, ListingInfo, ScrapeResult, parse_price

logger = logging.getLogger(__name__)



class TCGPlayerScraper(BaseScraper):
    async def scrape(self, url: str) -> ScrapeResult:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox"],
                )
                context = await browser.new_context(
                    user_agent=DEFAULT_USER_AGENT,
                    viewport={"width": 1920, "height": 1080},
                )
                page = await context.new_page()

                logger.info(f"TCGPlayer: Navigating to {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

                # Wait for price elements to render
                await page.wait_for_timeout(5000)

                price = None
                available = False

                # Try multiple selectors for price
                price_selectors = [
                    ".price-point__data",
                    ".listed-median .price",
                    ".market-price .price",
                    "[class*='price'] .value",
                    ".spotlight__price",
                ]

                for selector in price_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        for el in elements:
                            text = await el.text_content()
                            if text:
                                parsed = parse_price(text.strip())
                                if parsed and parsed > 0:
                                    price = parsed
                                    available = True
                                    break
                    except Exception:
                        continue
                    if price:
                        break

                # Check for out-of-stock indicators
                if not price:
                    body_text = await page.text_content("body")
                    if body_text and "out of stock" in body_text.lower():
                        available = False

                # Try to get listing-level prices from the sellers table
                listings = []
                try:
                    listing_rows = await page.query_selector_all(
                        ".listing-item, .product-listing__row, [class*='listing']"
                    )
                    for row in listing_rows[:10]:
                        row_text = await row.text_content()
                        if row_text:
                            row_price = parse_price(row_text)
                            if row_price and row_price > 0:
                                listings.append(
                                    ListingInfo(
                                        title="TCGPlayer Listing",
                                        price=row_price,
                                        link=url,
                                    )
                                )
                except Exception:
                    pass

                # If no main price but listings found, use lowest
                if not price and listings:
                    price = min(l.price for l in listings)
                    available = True

                await browser.close()

                logger.info(
                    f"TCGPlayer: price={price}, available={available}, "
                    f"listings={len(listings)}"
                )
                return ScrapeResult(
                    price=price, available=available, listings=listings
                )

        except Exception as e:
            logger.error(f"TCGPlayer scraper error: {e}")
            return ScrapeResult(error=str(e))
