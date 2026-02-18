import logging
import re
import time
from base64 import b64encode
from urllib.parse import quote_plus, parse_qs, urlparse

import httpx
from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, DEFAULT_USER_AGENT, ListingInfo, ScrapeResult, parse_price

logger = logging.getLogger(__name__)

# eBay Browse API endpoints
_EBAY_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
_EBAY_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
_EBAY_SCOPE = "https://api.ebay.com/oauth/api_scope"

# Cached OAuth token
_token_cache: dict = {"token": None, "expires_at": 0}



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


async def _get_ebay_token(client_id: str, client_secret: str) -> str | None:
    """Get an OAuth2 token for the eBay Browse API, with caching."""
    global _token_cache
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    credentials = b64encode(f"{client_id}:{client_secret}".encode()).decode()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _EBAY_TOKEN_URL,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "client_credentials",
                "scope": _EBAY_SCOPE,
            },
        )
        if resp.status_code != 200:
            logger.error(f"eBay OAuth failed: {resp.status_code} {resp.text[:200]}")
            return None
        data = resp.json()
        _token_cache["token"] = data["access_token"]
        _token_cache["expires_at"] = time.time() + data.get("expires_in", 7200)
        logger.info("eBay: OAuth token acquired")
        return _token_cache["token"]


def _extract_price_filter(url: str) -> tuple[float | None, float | None]:
    """Extract min/max price filters from eBay URL params."""
    if not url.startswith("http"):
        return None, None
    qs = parse_qs(urlparse(url).query)
    min_price = None
    max_price = None
    if "_udlo" in qs:
        try:
            min_price = float(qs["_udlo"][0])
        except ValueError:
            pass
    if "_udhi" in qs:
        try:
            max_price = float(qs["_udhi"][0])
        except ValueError:
            pass
    return min_price, max_price


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

    async def _scrape_via_api(self, search_term: str, url: str) -> ScrapeResult | None:
        """Try eBay Browse API. Returns None if API not configured or fails."""
        from app.config import settings

        if not settings.ebay_client_id or not settings.ebay_client_secret:
            return None

        token = await _get_ebay_token(settings.ebay_client_id, settings.ebay_client_secret)
        if not token:
            return None

        # Build API filters
        filters = ["buyingOptions:{FIXED_PRICE}", "deliveryCountry:US"]
        min_price, max_price = _extract_price_filter(url)
        if min_price is not None:
            filters.append(f"price:[{min_price}..],priceCurrency:USD")
        if max_price is not None:
            filters.append(f"price:[..{max_price}],priceCurrency:USD")

        params = {
            "q": search_term,
            "filter": ",".join(filters),
            "limit": "50",
            "sort": "price",
        }

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                _EBAY_SEARCH_URL,
                params=params,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
                    "Content-Type": "application/json",
                },
            )

        if resp.status_code != 200:
            logger.warning(f"eBay API search failed: {resp.status_code} {resp.text[:300]}")
            return None

        data = resp.json()
        items = data.get("itemSummaries", [])
        logger.info(f"eBay API: Got {len(items)} results for '{search_term}'")

        listings = []
        seen_ids = set()
        for item in items:
            try:
                title = item.get("title", "")
                if not title:
                    continue

                # Validate title matches search
                if search_term and not _title_matches_search(title, search_term):
                    logger.debug(f"eBay API: Skipping non-matching: '{title[:80]}'")
                    continue

                price_data = item.get("price", {})
                price_val = float(price_data.get("value", 0))
                if price_val <= 0:
                    continue

                item_url = item.get("itemWebUrl", "")
                item_id = item.get("itemId", "")
                # Extract numeric part from API itemId (format: v1|123456|0)
                id_match = re.search(r"(\d{8,})", item_id)
                listing_id = id_match.group(1) if id_match else item_id

                if listing_id in seen_ids:
                    continue
                seen_ids.add(listing_id)

                condition = item.get("condition", "")
                if isinstance(condition, dict):
                    condition = condition.get("conditionId", "")

                listings.append(ListingInfo(
                    title=title,
                    price=price_val,
                    link=item_url,
                    listing_id=listing_id,
                    condition=str(condition),
                ))
            except Exception as e:
                logger.debug(f"eBay API: Error parsing item: {e}")
                continue

        lowest_price = min((l.price for l in listings), default=None)
        available = len(listings) > 0

        logger.info(
            f"eBay API: {len(listings)} matching listings "
            f"(search='{search_term}'), lowest={lowest_price}"
        )
        return ScrapeResult(
            price=lowest_price,
            available=available,
            listings=listings,
        )

    async def _scrape_via_html(self, search_url: str, search_term: str) -> ScrapeResult:
        """Fallback: scrape eBay HTML via curl_cffi."""
        async with AsyncSession(impersonate="chrome120") as session:
            resp = await session.get(
                search_url,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=30,
            )
            logger.info(f"eBay scrape: status={resp.status_code}")
            html = resp.text

        logger.info(f"eBay scrape: HTML length={len(html)}")
        EbayScraper.last_page_html = html
        EbayScraper.last_page_text = ""

        soup = BeautifulSoup(html, "lxml")

        # Check for bot detection page
        page_title = soup.title.string if soup.title else ""
        if "pardon" in page_title.lower() or "interruption" in page_title.lower():
            logger.warning("eBay scrape: Blocked by bot detection (Pardon Our Interruption)")
            return ScrapeResult(error="eBay blocked this IP. Configure EBAY_CLIENT_ID and EBAY_CLIENT_SECRET for reliable access.")

        listings = []
        seen_ids = set()

        # Strategy 1: new s-card selector
        items = soup.select("li.s-card")
        logger.info(f"eBay scrape: li.s-card found {len(items)}")

        # Strategy 2: legacy .s-item selector
        if not items:
            items = soup.select(".s-item")
            logger.info(f"eBay scrape: .s-item found {len(items)}")

        # Strategy 3: ul.srp-results > li
        if not items:
            results_ul = soup.select_one("ul.srp-results")
            if results_ul:
                items = results_ul.find_all("li", recursive=False)
                logger.info(f"eBay scrape: ul.srp-results > li found {len(items)}")

        for item in items:
            try:
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

                title = ""
                for title_sel in [".s-card__title", ".s-item__title", "h3", "span[role='heading']"]:
                    title_el = item.select_one(title_sel)
                    if title_el:
                        title = title_el.get_text(strip=True)
                        break
                if not title:
                    for a_tag in item.find_all("a", href=True):
                        if f"/itm/{listing_id}" in a_tag["href"]:
                            title = a_tag.get_text(strip=True)
                            if title:
                                break
                if not title or title.lower().startswith("shop on ebay"):
                    continue

                if search_term and not _title_matches_search(title, search_term):
                    continue

                price = None
                shipping_keywords = {"shipping", "delivery", "postage", "original",
                                    "was", "strikethrough", "secondary", "additional"}

                for price_sel in [".s-card__price", ".s-item__price", "[class*='price']"]:
                    for price_el in item.select(price_sel):
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

                item_html_str = str(item)
                if "SPONSORED" in item_html_str or "ad-badge" in item_html_str:
                    continue

                if listing_id in seen_ids:
                    continue
                seen_ids.add(listing_id)

                listings.append(ListingInfo(
                    title=title, price=price, link=link, listing_id=listing_id,
                ))
            except Exception as e:
                logger.debug(f"eBay scrape: Error parsing item: {e}")
                continue

        if not listings:
            logger.warning(f"eBay scrape: No listings found. Page title: {page_title}")

        lowest_price = min((l.price for l in listings), default=None)
        available = len(listings) > 0

        logger.info(
            f"eBay scrape: {len(listings)} matching listings "
            f"(search='{search_term}'), lowest={lowest_price}"
        )
        return ScrapeResult(
            price=lowest_price,
            available=available,
            listings=listings,
        )

    async def scrape(self, url: str) -> ScrapeResult:
        try:
            # Extract search term from URL or use as-is
            if url.startswith("http"):
                search_term = _extract_search_terms(url)
            else:
                search_term = url

            logger.info(f"eBay: Starting check (search_term='{search_term}')")

            # Try API first
            api_result = await self._scrape_via_api(search_term, url)
            if api_result is not None:
                return api_result

            # Fall back to HTML scraping
            logger.info("eBay: API not configured or failed, falling back to HTML scraping")
            if not url.startswith("http"):
                search_url = self._build_url(url)
            else:
                search_url = url
                if "LH_BIN=1" not in search_url:
                    search_url += "&LH_BIN=1"
                if "LH_PrefLoc=1" not in search_url:
                    search_url += "&LH_PrefLoc=1"

            return await self._scrape_via_html(search_url, search_term)

        except Exception as e:
            logger.error(f"eBay scraper error: {e}")
            return ScrapeResult(error=str(e))
