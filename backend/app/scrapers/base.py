from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


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
