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

# Cached eBay cookies from challenge solving
_cookie_cache: dict = {"cookies": {}, "expires_at": 0}

# Domains allowed through Playwright route filter
_ALLOWED_DOMAINS = {"ebay.com", "ebaystatic.com"}



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

    async def _solve_challenge_and_scrape(self, url: str) -> tuple[dict[str, str], str | None]:
        """Two-phase Playwright approach: solve challenge then fetch results.

        Phase 1 (JS enabled):  Load the lightweight challenge page, let JS
            solve it, block the post-challenge redirect to avoid OOM.
        Phase 2 (JS disabled): Open a new context with extracted cookies,
            fetch the server-rendered search results safely.
        """
        global _cookie_cache
        from playwright.async_api import async_playwright

        logger.info("eBay: Launching Playwright (two-phase challenge solve)...")
        html = None

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                    "--disable-extensions", "--no-first-run",
                    "--js-flags=--max-old-space-size=256",
                ],
            )

            # ── Phase 1: Solve challenge (JS enabled) ──
            ctx1 = await browser.new_context(
                user_agent=DEFAULT_USER_AGENT,
                viewport={"width": 800, "height": 600},
            )
            page1 = await ctx1.new_page()
            first_nav_done = {"value": False}

            async def route_challenge(route):
                resource = route.request.resource_type
                req_url = route.request.url
                if resource in ("image", "font", "media", "stylesheet"):
                    await route.abort()
                    return
                # Block post-challenge redirect to prevent heavy search page OOM
                if resource == "document" and first_nav_done["value"]:
                    logger.info("eBay challenge: Blocking post-challenge redirect")
                    await route.abort()
                    return
                if not any(d in req_url for d in _ALLOWED_DOMAINS):
                    await route.abort()
                    return
                await route.continue_()

            await page1.route("**/*", route_challenge)

            try:
                await page1.goto(url, wait_until="domcontentloaded", timeout=30000)
                first_nav_done["value"] = True
                # Give challenge JS time to run, send fingerprint, set cookies
                await page1.wait_for_timeout(10000)
            except Exception as e:
                logger.warning(f"eBay challenge phase 1: {e}")

            cookies_list = await ctx1.cookies()
            await ctx1.close()
            logger.info(f"eBay challenge: Phase 1 extracted {len(cookies_list)} cookies")

            # ── Phase 2: Fetch results (JS disabled, with cookies) ──
            if cookies_list:
                ctx2 = await browser.new_context(
                    user_agent=DEFAULT_USER_AGENT,
                    viewport={"width": 800, "height": 600},
                    java_script_enabled=False,
                )
                await ctx2.add_cookies(cookies_list)
                page2 = await ctx2.new_page()

                try:
                    resp = await page2.goto(url, wait_until="domcontentloaded", timeout=30000)
                    html = await page2.content()
                    logger.info(f"eBay challenge: Phase 2 got HTML len={len(html)}")
                except Exception as e:
                    logger.warning(f"eBay challenge phase 2: {e}")

                await ctx2.close()

            await browser.close()

        cookie_dict = {c["name"]: c["value"] for c in cookies_list}
        logger.info(f"eBay challenge: Got {len(cookie_dict)} cookies total")

        # Cache cookies for future curl_cffi attempts
        if cookie_dict:
            _cookie_cache["cookies"] = cookie_dict
            _cookie_cache["expires_at"] = time.time() + 300  # 5 min cache

        return cookie_dict, html

    async def _fetch_html(self, url: str, cookies: dict | None = None) -> str:
        """Fetch eBay HTML via curl_cffi with optional cookies."""
        async with AsyncSession(impersonate="chrome120") as session:
            resp = await session.get(
                url,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                cookies=cookies,
                timeout=30,
            )
            logger.info(f"eBay scrape: status={resp.status_code}, len={len(resp.text)}")
            return resp.text

    @staticmethod
    def _is_blocked(html: str) -> bool:
        """Check if the response is eBay's bot detection page."""
        soup = BeautifulSoup(html, "lxml")
        title = soup.title.string if soup.title else ""
        return "pardon" in title.lower() or "interruption" in title.lower()

    async def _scrape_via_html(self, search_url: str, search_term: str) -> ScrapeResult:
        """Fallback: scrape eBay HTML via curl_cffi, solving challenges if needed."""
        global _cookie_cache

        # Use cached cookies if available
        cookies = None
        if _cookie_cache["cookies"] and time.time() < _cookie_cache["expires_at"]:
            cookies = _cookie_cache["cookies"]
            logger.info(f"eBay scrape: Using {len(cookies)} cached cookies")

        html = await self._fetch_html(search_url, cookies)

        # If blocked, use Playwright to solve challenge AND get HTML directly
        if self._is_blocked(html):
            logger.warning("eBay scrape: Blocked — attempting Playwright challenge solve")
            try:
                cookies, pw_html = await self._solve_challenge_and_scrape(search_url)
                if pw_html and not self._is_blocked(pw_html):
                    html = pw_html
                    logger.info("eBay scrape: Using HTML from Playwright directly")
                elif cookies:
                    # Playwright got cookies but couldn't get HTML — retry with curl_cffi
                    html = await self._fetch_html(search_url, cookies)
                    if self._is_blocked(html):
                        logger.error("eBay scrape: Still blocked after challenge solve")
                        return ScrapeResult(error="eBay challenge solve failed. Try again or configure EBAY_CLIENT_ID/EBAY_CLIENT_SECRET.")
                else:
                    return ScrapeResult(error="eBay challenge solve failed — no cookies obtained.")
            except Exception as e:
                logger.error(f"eBay challenge solve error: {e}")
                return ScrapeResult(error=f"eBay challenge solve failed: {e}")

        EbayScraper.last_page_html = html
        EbayScraper.last_page_text = ""

        soup = BeautifulSoup(html, "lxml")
        page_title = soup.title.string if soup.title else ""

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
