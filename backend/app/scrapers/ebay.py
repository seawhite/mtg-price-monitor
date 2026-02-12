import logging
import re
from urllib.parse import quote_plus

from playwright.async_api import async_playwright

from app.scrapers.base import BaseScraper, ListingInfo, ScrapeResult

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"


def parse_price(text: str) -> float | None:
    match = re.search(r"\$?([\d,]+\.?\d*)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


class EbayScraper(BaseScraper):
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
                    args=["--no-sandbox", "--disable-setuid-sandbox"],
                )
                context = await browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1920, "height": 1080},
                )
                page = await context.new_page()

                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                # Wait for search results to render
                await page.wait_for_timeout(3000)

                listings = []
                seen_ids = set()

                items = await page.query_selector_all(".s-item")
                logger.info(f"eBay: Found {len(items)} .s-item elements")

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
