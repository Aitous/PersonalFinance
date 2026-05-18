from backend.scrapers.chase import ChaseScraper
from backend.scrapers.discover import DiscoverScraper
from backend.scrapers.amex import AmexScraper
from backend.scrapers.base import BaseScraper

def test_scrapers_inherit_base():
    assert issubclass(ChaseScraper, BaseScraper)
    assert issubclass(DiscoverScraper, BaseScraper)
    assert issubclass(AmexScraper, BaseScraper)

def test_scrapers_declare_allowed_domains():
    assert "chase.com" in ChaseScraper.ALLOWED_DOMAINS
    assert "discover.com" in DiscoverScraper.ALLOWED_DOMAINS
    assert "americanexpress.com" in AmexScraper.ALLOWED_DOMAINS

def test_scrapers_declare_source():
    assert ChaseScraper.SOURCE == "chase"
    assert DiscoverScraper.SOURCE == "discover"
    assert AmexScraper.SOURCE == "amex"
