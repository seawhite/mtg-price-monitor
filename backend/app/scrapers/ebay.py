import logging
import re
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, ListingInfo, ScrapeResult

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


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
            response = requests.get(search_url, headers=HEADERS, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")
            listings = []
            seen_ids = set()

            items = soup.select(".s-item")
            for item in items:
                try:
                    # Skip the first "Shop on eBay" placeholder
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

                    # Skip price ranges like "$10.00 to $20.00"
                    if " to " in price_text:
                        continue

                    price = parse_price(price_text)
                    if not price or price <= 0:
                        continue

                    # Link
                    link_el = item.select_one(".s-item__link")
                    link = link_el["href"] if link_el else ""

                    # Extract listing ID from link
                    listing_id = ""
                    id_match = re.search(r"/itm/(\d+)", link)
                    if id_match:
                        listing_id = id_match.group(1)

                    # Skip sponsored items
                    sponsored = item.select_one(".s-item__ad-badge, [class*='SPONSORED']")
                    if sponsored:
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
