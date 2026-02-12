import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def parse_price(text: str) -> float | None:
    """Extract a numeric price from text like '$1,234.56' or '1234.56'."""
    match = re.search(r"\$?([\d,]+\.?\d*)", text)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


@dataclass
class ListingInfo:
    title: str
    price: float
    link: str
    listing_id: str = ""
    seller: str = ""
    condition: str = ""


@dataclass
class ScrapeResult:
    price: Optional[float] = None
    available: bool = False
    listings: list[ListingInfo] = field(default_factory=list)
    error: Optional[str] = None


class BaseScraper(ABC):
    @abstractmethod
    async def scrape(self, url: str) -> ScrapeResult:
        pass
