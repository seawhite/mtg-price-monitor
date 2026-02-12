import logging
import re

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


class ManapoolScraper(BaseScraper):
    async def scrape(self, url: str) -> ScrapeResult:
        try:
            logger.info(f"Manapool: Fetching {url}")
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "lxml")

            price = None
            available = False

            # Look for price elements on the card page
            price_selectors = [
                ".card-price",
                ".price",
                "[class*='price']",
                ".product-price",
                ".card-detail-price",
            ]

            for selector in price_selectors:
                elements = soup.select(selector)
                for el in elements:
                    text = el.get_text(strip=True)
                    parsed = parse_price(text)
                    if parsed and parsed > 0:
                        price = parsed
                        available = True
                        break
                if price:
                    break

            # Check for availability indicators
            page_text = soup.get_text().lower()
            if "sold out" in page_text or "out of stock" in page_text:
                available = False
            elif "add to cart" in page_text or "buy now" in page_text:
                available = True

            # Look for individual vendor/seller listings
            listings = []
            listing_selectors = [
                ".vendor-listing",
                ".seller-listing",
                ".listing-row",
                "tr[class*='listing']",
                ".card-listing",
            ]

            for selector in listing_selectors:
                rows = soup.select(selector)
                for row in rows:
                    row_text = row.get_text(strip=True)
                    row_price = parse_price(row_text)
                    if row_price and row_price > 0:
                        # Try to find a link in the row
                        link_el = row.select_one("a[href]")
                        link = link_el["href"] if link_el else url

                        listings.append(
                            ListingInfo(
                                title="Manapool Listing",
                                price=row_price,
                                link=link,
                            )
                        )
                if listings:
                    break

            if not price and listings:
                price = min(l.price for l in listings)
                available = True

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
