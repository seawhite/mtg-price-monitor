import logging
import re
from urllib.parse import quote_plus, parse_qs, urlparse

from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, DEFAULT_USER_AGENT, ListingInfo, ScrapeResult, parse_price

logger = logging.getLogger(__name__)



def _normalize(text: str) -> str:
    """Strip punctuation and lowercase for comparison."""
    return re.sub(r"[^\w\s]", "", text).lower()


def _extract_search_terms(url: str) -> str:
    """Extract the search keywords from an eBay URL or raw search term."""
    if url.startswith("http"):
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        nkw = qs.get("_nkw", [""])[0]
        return nkw
    return url


def _title_matches_search(title: str, search_term: str) -> bool:
    """Check that a listing title contains all significant search keywords."""
    norm_title = _normalize(title)
    norm_search = _normalize(search_term)
    keywords = [w for w in norm_search.split() if len(w) >= 2]
    if not keywords:
        return True
    matched = sum(1 for kw in keywords if kw in norm_title)
    # Require all keywords to be present
    return matched == len(keywords)


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

            # Extract search keywords for title validation
            search_term = _extract_search_terms(search_url) if url.startswith("http") else url
            logger.info(f"eBay: Fetching {search_url} (search_term='{search_term}')")

            async with AsyncSession(impersonate="chrome120") as session:
                resp = await session.get(
                    search_url,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                    timeout=30,
                )
                logger.info(f"eBay: Response status={resp.status_code}")
                html = resp.text

            logger.info(f"eBay: HTML length={len(html)}")
            EbayScraper.last_page_html = html
            EbayScraper.last_page_text = ""

            # Parse the HTML with BeautifulSoup
            soup = BeautifulSoup(html, "lxml")

            listings = []
            seen_ids = set()

            # Strategy 1: Try new s-card selector
            items = soup.select("li.s-card")
            logger.info(f"eBay: li.s-card found {len(items)} elements")

            # Strategy 2: Try legacy .s-item selector
            if not items:
                items = soup.select(".s-item")
                logger.info(f"eBay: .s-item found {len(items)} elements")

            # Strategy 3: find <li> children of ul.srp-results
            if not items:
                results_ul = soup.select_one("ul.srp-results")
                if results_ul:
                    items = results_ul.find_all("li", recursive=False)
                    logger.info(f"eBay: ul.srp-results > li found {len(items)} elements")

            for item in items:
                try:
                    # Find the item link to /itm/ (most reliable anchor)
                    link = ""
                    listing_id = ""
                    for a_tag in item.find_all("a", href=True):
                        href = a_tag["href"]
                        id_match = re.search(r"/itm/(\d+)", href)
                        if id_match:
                            link = href
                            listing_id = id_match.group(1)
                            break

                    if not listing_id:
                        continue

                    # Extract title: try known selectors, then fall back to link text
                    title = ""
                    for title_sel in [".s-card__title", ".s-item__title", "h3", "span[role='heading']"]:
                        title_el = item.select_one(title_sel)
                        if title_el:
                            title = title_el.get_text(strip=True)
                            break
                    if not title:
                        # Use the text of the link that points to /itm/
                        for a_tag in item.find_all("a", href=True):
                            if f"/itm/{listing_id}" in a_tag["href"]:
                                title = a_tag.get_text(strip=True)
                                if title:
                                    break
                    if not title or title.lower().startswith("shop on ebay"):
                        continue

                    # Validate title matches search keywords
                    if search_term and not _title_matches_search(title, search_term):
                        logger.debug(f"eBay: Skipping non-matching listing: '{title[:80]}'")
                        continue

                    # Extract price — avoid shipping/secondary prices
                    price = None
                    # Exclude elements whose class contains these keywords
                    shipping_keywords = {"shipping", "delivery", "postage", "original",
                                        "was", "strikethrough", "secondary", "additional"}

                    for price_sel in [".s-card__price", ".s-item__price", "[class*='price']"]:
                        for price_el in item.select(price_sel):
                            # Skip shipping/secondary price elements
                            el_classes = " ".join(price_el.get("class", [])).lower()
                            parent_classes = " ".join(price_el.parent.get("class", [])).lower() if price_el.parent else ""
                            all_classes = el_classes + " " + parent_classes
                            if any(kw in all_classes for kw in shipping_keywords):
                                continue
                            price_text = price_el.get_text(strip=True)
                            if " to " in price_text:
                                continue
                            price = parse_price(price_text)
                            if price and price > 0:
                                break
                        if price:
                            break

                    # Fallback: find $X.XX in item text, but skip shipping lines
                    if not price:
                        for line in item.stripped_strings:
                            line_lower = line.lower()
                            if any(kw in line_lower for kw in ["shipping", "delivery", "postage"]):
                                continue
                            m = re.search(r"\$(\d+[\.,]\d{2})", line)
                            if m:
                                price = float(m.group(1).replace(",", ""))
                                break

                    if not price or price <= 0:
                        continue

                    # Skip sponsored
                    item_classes = " ".join(item.get("class", []))
                    item_html_str = str(item)
                    if "SPONSORED" in item_html_str or "ad-badge" in item_html_str:
                        continue

                    # Deduplicate
                    if listing_id in seen_ids:
                        continue
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

            # If still nothing, log diagnostic info
            if not listings:
                results_ul = soup.select_one("ul.srp-results")
                if results_ul:
                    children = results_ul.find_all("li", recursive=False)
                    first_html = str(children[0])[:500] if children else 'NONE'
                    logger.warning(f"eBay: {len(children)} <li> in ul.srp-results but 0 parsed. First child HTML: {first_html}")
                else:
                    # Log a snippet of the page for debugging
                    logger.warning(f"eBay: No ul.srp-results found. Page title: {soup.title.string if soup.title else 'N/A'}")
                    logger.warning(f"eBay: HTML snippet (first 1000 chars): {html[:1000]}")

            lowest_price = min((l.price for l in listings), default=None)
            available = len(listings) > 0

            logger.info(
                f"eBay: Found {len(listings)} matching listings "
                f"(search='{search_term}'), lowest={lowest_price}"
            )
            return ScrapeResult(
                price=lowest_price,
                available=available,
                listings=listings,
            )

        except Exception as e:
            logger.error(f"eBay scraper error: {e}")
            return ScrapeResult(error=str(e))
