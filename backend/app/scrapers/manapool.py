import json
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

            api_responses: list[dict] = []

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

                # Intercept API responses to capture listing data
                async def handle_response(response):
                    try:
                        resp_url = response.url
                        if response.status == 200 and (
                            "listing" in resp_url.lower()
                            or "for-sale" in resp_url.lower()
                            or "inventory" in resp_url.lower()
                            or "/api/" in resp_url.lower()
                        ):
                            ct = response.headers.get("content-type", "")
                            if "json" in ct:
                                body = await response.json()
                                logger.info(f"Manapool API: {resp_url[:120]} -> keys={list(body.keys()) if isinstance(body, dict) else type(body).__name__}")
                                api_responses.append({"url": resp_url, "data": body})
                    except Exception:
                        pass

                page.on("response", handle_response)

                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Wait for dynamic content and API calls to complete
                await page.wait_for_timeout(6000)

                listings = []
                price = None
                available = False

                # Strategy 1: Parse intercepted API responses for listings
                for resp in api_responses:
                    data = resp["data"]
                    items = []
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict):
                        # Look for common API patterns
                        for key in ["results", "listings", "data", "items", "for_sale", "inventory"]:
                            if key in data and isinstance(data[key], list):
                                items = data[key]
                                break
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        item_price = None
                        for pk in ["price", "total_price", "unit_price", "amount", "cost"]:
                            if pk in item:
                                try:
                                    val = item[pk]
                                    if isinstance(val, (int, float)):
                                        item_price = float(val)
                                    elif isinstance(val, str):
                                        item_price = parse_price(val)
                                    if item_price and item_price > 0:
                                        break
                                except Exception:
                                    pass
                        if item_price and item_price > 0:
                            seller = item.get("seller_name", item.get("seller", item.get("shop_name", "Seller")))
                            condition = item.get("condition", item.get("card_condition", ""))
                            title = f"{seller} - {condition}".strip(" -") if seller else "Manapool Listing"
                            listings.append(
                                ListingInfo(
                                    title=title,
                                    price=item_price,
                                    link=url,
                                )
                            )

                # Strategy 2: Scrape visible DOM for listing rows if API interception missed
                if not listings:
                    logger.info("Manapool: No listings from API, scraping DOM")
                    # Dump the full body text for debugging
                    try:
                        body_text = await page.text_content("body") or ""
                        # Find all dollar amounts
                        dollar_matches = re.findall(r"\$(\d+\.\d{2})", body_text)
                        logger.info(f"Manapool: Found {len(dollar_matches)} dollar amounts in page: {dollar_matches[:20]}")

                        # Try to find listing containers - look for elements that have both
                        # a price and an "Add to Cart" or similar action
                        # Try various selectors for listing rows
                        row_selectors = [
                            "[class*='listing']",
                            "[class*='Listing']",
                            "[class*='for-sale'] > div",
                            "[class*='ForSale'] > div",
                            "[class*='seller']",
                            "[class*='Seller']",
                            "table tbody tr",
                            "[class*='row']",
                            "[class*='inventory']",
                            "[class*='card-item']",
                        ]

                        for selector in row_selectors:
                            try:
                                rows = await page.query_selector_all(selector)
                                if rows:
                                    logger.info(f"Manapool: selector '{selector}' found {len(rows)} elements")
                                for row in rows:
                                    text = await row.text_content() or ""
                                    row_price = parse_price(text)
                                    if row_price and row_price > 0.5:
                                        listings.append(
                                            ListingInfo(
                                                title="Manapool Listing",
                                                price=row_price,
                                                link=url,
                                            )
                                        )
                            except Exception:
                                continue
                            if listings:
                                break

                    except Exception as e:
                        logger.warning(f"Manapool: DOM scrape error: {e}")

                # Strategy 3: Fallback to all dollar amounts on page
                if not listings:
                    try:
                        body_text = await page.text_content("body") or ""
                        all_prices = re.findall(r"\$(\d+\.\d{2})", body_text)
                        valid_prices = [float(p) for p in all_prices if float(p) > 0.5]
                        for vp in valid_prices:
                            listings.append(
                                ListingInfo(title="Manapool Listing", price=vp, link=url)
                            )
                    except Exception:
                        pass

                # Deduplicate listings by price
                seen_prices = set()
                unique_listings = []
                for l in listings:
                    if l.price not in seen_prices:
                        seen_prices.add(l.price)
                        unique_listings.append(l)
                listings = unique_listings

                if listings:
                    price = min(l.price for l in listings)
                    available = True

                await browser.close()

            logger.info(
                f"Manapool: price={price}, available={available}, "
                f"listings={len(listings)}, "
                f"api_responses={len(api_responses)}"
            )
            return ScrapeResult(
                price=price, available=available, listings=listings
            )

        except Exception as e:
            logger.error(f"Manapool scraper error: {e}")
            return ScrapeResult(error=str(e))
