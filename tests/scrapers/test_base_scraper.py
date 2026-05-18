import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.scrapers.base import BaseScraper

class DummyScraper(BaseScraper):
    ALLOWED_DOMAINS = ["example.com"]
    SOURCE = "dummy"

    async def login(self): pass
    async def download_transactions(self, since): return None
    async def logout(self): pass

def test_is_allowed_domain():
    scraper = DummyScraper(username="u", password="p")
    assert scraper._is_allowed("https://example.com/transactions") is True
    assert scraper._is_allowed("https://evil.com/steal") is False
    assert scraper._is_allowed("https://sub.example.com/page") is True

def test_not_allowed_domain_raises():
    scraper = DummyScraper(username="u", password="p")
    with pytest.raises(ValueError, match="blocked"):
        scraper._assert_allowed("https://evil.com/steal")
