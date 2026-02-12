import logging
import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
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
    # Store last page info for debugging
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
                        "--disable-dev-shm-usage",
                    ],
                )
                context = await browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1920, "height": 1080},
                    locale="en-US",
                )
                page = await context.new_page()

                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                """)

                response = await page.goto(search_url, wait_until="networkidle", timeout=30000)
                logger.info(f"eBay: Response status={response.status if response else 'None'}")
                await page.wait_for_timeout(3000)

                # Get the full rendered HTML
                html = await page.content()
                EbayScraper.last_page_html = html
                EbayScraper.last_page_text = await page.text_content("body") or ""
                logger.info(f"eBay: HTML length={len(html)}")

                await browser.close()

            # Parse the HTML with BeautifulSoup instead of Playwright DOM queries
            soup = BeautifulSoup(html, "lxml")

            listings = []
            seen_ids = set()

            items = soup.select(".s-item")
            logger.info(f"eBay: BeautifulSoup found {len(items)} .s-item elements")

            for item in items:
                try:
                    # Skip the "Shop on eBay" placeholder
                    title_el = item.select_one(".s-item__title")
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    if title.lower().startswith("shop on ebay"):
                        continue

                    # Price
                    price_el = item.select_one(".s-item__price")
                    if not price_el:
                        continue
                    price_text = price_el.get_text(strip=True)

                    # Skip price ranges
                    if " to " in price_text:
                        continue

                    price = parse_price(price_text)
                    if not price or price <= 0:
                        continue

                    # Link
                    link_el = item.select_one(".s-item__link")
                    link = link_el["href"] if link_el and link_el.has_attr("href") else ""

                    # Extract listing ID
                    listing_id = ""
                    id_match = re.search(r"/itm/(\d+)", link)
                    if id_match:
                        listing_id = id_match.group(1)

                    # Skip sponsored
                    sponsored = item.select_one(".s-item__ad-badge, [class*='SPONSORED']")
                    if sponsored:
                        continue

                    # Skip non-US items
                    loc_el = item.select_one(".s-item__location, .s-item__itemLocation")
                    if loc_el:
                        loc_text = loc_el.get_text(strip=True).lower()
                        if loc_text and "united states" not in loc_text and "us" not in loc_text.split():
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

            # If no .s-item found, log what selectors DO exist for debugging
            if not listings:
                # Check what major containers exist
                for sel in ["#srp-river-results", ".srp-results", ".b-list__items_nofooter",
                            "[class*='srp']", "[class*='item']", "ul.srp-results"]:
                    found = soup.select(sel)
                    if found:
                        logger.info(f"eBay: Found {len(found)} elements for '{sel}'")
                # Log first few class names from top-level divs
                top_divs = soup.select("body > div")
                logger.info(f"eBay: {len(top_divs)} top-level divs. Classes: {[d.get('class', []) for d in top_divs[:5]]}")

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
