import json
import logging
import re

from playwright.async_api import async_playwright

from app.scrapers.base import BaseScraper, ListingInfo, ScrapeResult

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def parse_price(text: str) -> float | None:
    match = re.search(r"\$?([\d,]+\.?\d*)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def _find_price_in_dict(d: dict) -> float | None:
    """Search a dict for listing price, avoiding shipping/fee fields."""
    # Explicit keys to match
    good_keys = {"price", "total_price", "unit_price", "listing_price",
                 "sale_price", "card_price", "cost"}
    # Keys to skip even though they contain "price"/"cost"
    bad_keywords = {"shipping", "delivery", "fee", "tax", "discount",
                    "original", "compare", "msrp", "retail", "from_price",
                    "market"}

    for k, v in d.items():
        k_lower = k.lower()
        # Skip shipping/fee/tax fields
        if any(bk in k_lower for bk in bad_keywords):
            continue
        if k_lower in good_keys or (
            "price" in k_lower and not any(bk in k_lower for bk in bad_keywords)
        ):
            if isinstance(v, (int, float)) and v > 0:
                return float(v)
            elif isinstance(v, str):
                p = parse_price(v)
                if p and p > 0:
                    return p
        if isinstance(v, dict):
            result = _find_price_in_dict(v)
            if result:
                return result
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
                            or "products" in resp_url.lower()
                            or "sb-api" in resp_url.lower()
                        ):
                            ct = response.headers.get("content-type", "")
                            if "json" in ct:
                                body = await response.json()
                                if isinstance(body, list) and body:
                                    logger.info(f"Manapool API: {resp_url[:120]} -> list[{len(body)}], first_item_keys={list(body[0].keys()) if isinstance(body[0], dict) else 'N/A'}")
                                elif isinstance(body, dict):
                                    logger.info(f"Manapool API: {resp_url[:120]} -> keys={list(body.keys())}")
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
                # Manapool uses Supabase (sb-api.manapool.com) which stores prices in CENTS
                # Only process 'products_mtg_single' responses — these have individual seller listings.
                # Skip 'cardsmtg' and 'cardsmtg_browse' which contain aggregate/metadata (from_price etc.)
                for resp in api_responses:
                    resp_url_lower = resp["url"].lower()
                    # Only parse individual listing endpoints
                    if "products" not in resp_url_lower and "listing" not in resp_url_lower and "for-sale" not in resp_url_lower and "inventory" not in resp_url_lower:
                        continue
                    is_supabase = "sb-api" in resp["url"]
                    data = resp["data"]
                    items = []
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict):
                        for key in ["results", "listings", "data", "items", "for_sale", "inventory"]:
                            if key in data and isinstance(data[key], list):
                                items = data[key]
                                break

                    if items and isinstance(items[0], dict):
                        sample = {k: v for k, v in list(items[0].items())[:6]}
                        logger.info(f"Manapool API: first item keys={list(items[0].keys())}, sample={sample}")

                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        # Recursively search for price in nested dict (Supabase joins)
                        item_price = _find_price_in_dict(item)
                        if item_price and item_price > 0:
                            # Supabase stores prices in cents — convert to dollars
                            if is_supabase:
                                item_price = item_price / 100.0
                            # Extract seller/condition info from any level
                            seller = (item.get("seller_name") or item.get("seller")
                                      or item.get("shop_name") or "")
                            condition = ""
                            cond_id = item.get("condition_id", "")
                            if cond_id:
                                cond_map = {"1": "NM", "2": "LP", "3": "MP", "4": "HP", "5": "DMG"}
                                condition = cond_map.get(str(cond_id), str(cond_id))
                            title = f"{seller} - {condition}".strip(" -") if seller else f"Manapool Listing ({condition})" if condition else "Manapool Listing"
                            listings.append(
                                ListingInfo(
                                    title=title,
                                    price=round(item_price, 2),
                                    link=url,
                                )
                            )

                # Strategy 2: Scrape visible DOM for dollar amounts
                if not listings:
                    logger.info("Manapool: No listings from API, scraping DOM")
                    try:
                        body_text = await page.text_content("body") or ""
                        # Find all dollar amounts on the page
                        dollar_matches = re.findall(r"\$(\d+\.\d{2})", body_text)
                        logger.info(f"Manapool: Found {len(dollar_matches)} dollar amounts: {dollar_matches[:20]}")

                        # Use all dollar amounts as potential listings (threshold $0.01)
                        for dm in dollar_matches:
                            p = float(dm)
                            if p >= 0.01:
                                listings.append(
                                    ListingInfo(
                                        title="Manapool Listing",
                                        price=p,
                                        link=url,
                                    )
                                )
                    except Exception as e:
                        logger.warning(f"Manapool: DOM scrape error: {e}")

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
