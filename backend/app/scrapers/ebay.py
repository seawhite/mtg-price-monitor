import json
import logging
import re
from urllib.parse import quote_plus

from playwright.async_api import async_playwright

from app.scrapers.base import BaseScraper, ListingInfo, ScrapeResult

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def parse_price(text: str) -> float | None:
    match = re.search(r"\$?([\d,]+\.?\d*)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


class EbayScraper(BaseScraper):
    # Store last page HTML for debugging
    last_page_html: str = ""
    last_page_text: str = ""

    def _build_url(self, search_term: str) -> str:
        """Build eBay search URL with Buy It Now + US only filters."""
        encoded = quote_plus(search_term)
        return (
            f"https://www.ebay.com/sch/i.html"
            f"?_nkw={encoded}"
            f"&_sacat=0"
            f"&LH_BIN=1"
            f"&LH_PrefLoc=1"
            f"&_from=R40"
        )

    async def scrape(self, url: str) -> ScrapeResult:
        try:
            # If url looks like a search term (no http), build the full URL
            if not url.startswith("http"):
                search_url = self._build_url(url)
            else:
                # Ensure Buy It Now and US filters are present
                search_url = url
                if "LH_BIN=1" not in search_url:
                    search_url += "&LH_BIN=1"
                if "LH_PrefLoc=1" not in search_url:
                    search_url += "&LH_PrefLoc=1"

            logger.info(f"eBay: Fetching {search_url}")

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-infobars",
                        "--disable-dev-shm-usage",
                    ],
                )
                context = await browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                    java_script_enabled=True,
                )
                page = await context.new_page()

                # Stealth: hide webdriver, plugins, etc.
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                    window.chrome = {runtime: {}};
                """)

                response = await page.goto(search_url, wait_until="networkidle", timeout=30000)
                logger.info(f"eBay: Initial response status={response.status if response else 'None'}")

                # Wait for search results to render
                try:
                    await page.wait_for_selector(".srp-results", timeout=10000)
                    logger.info("eBay: Found .srp-results container")
                except Exception:
                    logger.warning("eBay: No .srp-results container found")
                    try:
                        await page.wait_for_selector(".s-item", timeout=5000)
                    except Exception:
                        logger.warning("eBay: No .s-item elements found either")

                await page.wait_for_timeout(2000)

                # Capture page info for debugging
                page_title = await page.title()
                current_url = page.url
                logger.info(f"eBay: Page title='{page_title}', url='{current_url}'")

                # Capture HTML and text for debug endpoint
                try:
                    EbayScraper.last_page_html = await page.content()
                    EbayScraper.last_page_text = await page.text_content("body") or ""
                    logger.info(f"eBay: Page HTML length={len(EbayScraper.last_page_html)}, text length={len(EbayScraper.last_page_text)}")
                except Exception:
                    pass

                listings = []
                seen_ids = set()

                # Try multiple item selectors (eBay changes their HTML frequently)
                item_selectors = [".s-item", ".srp-results .s-item__wrapper", "[data-viewport]"]
                items = []
                for sel in item_selectors:
                    items = await page.query_selector_all(sel)
                    if items:
                        logger.info(f"eBay: Found {len(items)} items with selector '{sel}'")
                        break

                # If no items found, try parsing prices from page text
                if not items:
                    logger.warning(f"eBay: No items found with any selector. Page text (first 500): {EbayScraper.last_page_text[:500]}")
                    # Fallback: extract all dollar amounts from page
                    all_prices = re.findall(r"\$(\d+\.\d{2})", EbayScraper.last_page_text)
                    logger.info(f"eBay: Found {len(all_prices)} dollar amounts in page text: {all_prices[:10]}")

                for item in items:
                    try:
                        # Skip the first "Shop on eBay" placeholder
                        title_el = await item.query_selector(".s-item__title")
                        if not title_el:
                            continue
                        title = (await title_el.text_content() or "").strip()
                        if title.lower().startswith("shop on ebay"):
                            continue

                        # Price
                        price_el = await item.query_selector(".s-item__price")
                        if not price_el:
                            continue
                        price_text = (await price_el.text_content() or "").strip()

                        # Skip price ranges like "$10.00 to $20.00"
                        if " to " in price_text:
                            continue

                        price = parse_price(price_text)
                        if not price or price <= 0:
                            continue

                        # Link
                        link_el = await item.query_selector(".s-item__link")
                        link = await link_el.get_attribute("href") if link_el else ""
                        link = link or ""

                        # Extract listing ID from link
                        listing_id = ""
                        id_match = re.search(r"/itm/(\d+)", link)
                        if id_match:
                            listing_id = id_match.group(1)

                        # Skip sponsored items
                        sponsored = await item.query_selector(".s-item__ad-badge, [class*='SPONSORED']")
                        if sponsored:
                            continue

                        # Skip non-US items
                        loc_el = await item.query_selector(".s-item__location, .s-item__itemLocation")
                        if loc_el:
                            loc_text = (await loc_el.text_content() or "").strip().lower()
                            if loc_text and "united states" not in loc_text and "us" not in loc_text.split():
                                logger.debug(f"eBay: Skipping non-US item: {loc_text}")
                                continue

                        # Deduplicate
                        if listing_id and listing_id in seen_ids:
                            continue
                        if listing_id:
                            seen_ids.add(listing_id)

                        listings.append(
                            ListingInfo(
                                title=title,
                                price=price,
                                link=link,
                                listing_id=listing_id,
                            )
                        )
                    except Exception as e:
                        logger.debug(f"eBay: Error parsing item: {e}")
                        continue

                await browser.close()

            lowest_price = min((l.price for l in listings), default=None)
            available = len(listings) > 0

            logger.info(
                f"eBay: Found {len(listings)} listings, "
                f"lowest={lowest_price}"
            )
            return ScrapeResult(
                price=lowest_price,
                available=available,
                listings=listings,
            )

        except Exception as e:
            logger.error(f"eBay scraper error: {e}")
            return ScrapeResult(error=str(e))
