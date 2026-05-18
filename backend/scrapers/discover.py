import tempfile
from datetime import date
from pathlib import Path
from backend.scrapers.base import BaseScraper

class DiscoverScraper(BaseScraper):
    ALLOWED_DOMAINS = ["discover.com", "www.discover.com", "portal.discover.com"]
    SOURCE = "discover"
    LOGIN_URL = "https://portal.discover.com/customersvcs/universalLogin/ac_main"
    DASHBOARD_URL_PATTERN = "**/cardmembersvcs/**"
    MFA_URL_PATTERNS = ["**/otp**", "**/multifactor**", "**/challenge**"]

    async def login(self) -> None:
        await self._page.goto(self.LOGIN_URL, wait_until="domcontentloaded")
        await self._page.wait_for_selector("#userid", timeout=20000)
        await self._page.fill("#userid", self._username)
        await self._page.fill("#password", self._password)
        await self._page.click("#log-in-button")
        await self._wait_for_login()

    async def download_transactions(self, since: date) -> Path:
        await self._page.goto("https://www.discover.com/credit-cards/cardmembersvcs/acctsvcs.svc/summary")
        await self._page.wait_for_selector("[data-testid='download-link']", timeout=10000)
        await self._page.click("[data-testid='download-link']")
        await self._page.wait_for_selector("[data-testid='date-range-custom']", timeout=5000)
        await self._page.click("[data-testid='date-range-custom']")
        await self._page.fill("[data-testid='from-date']", since.strftime("%m/%d/%Y"))
        await self._page.fill("[data-testid='to-date']", date.today().strftime("%m/%d/%Y"))
        await self._page.select_option("[data-testid='file-format']", "csv")
        tmp_dir = Path(tempfile.mkdtemp())
        async with self._page.expect_download() as download_info:
            await self._page.click("[data-testid='download-submit']")
        download = await download_info.value
        dest = tmp_dir / f"discover_{since.isoformat()}.csv"
        await download.save_as(str(dest))
        return dest

    async def logout(self) -> None:
        await self._page.click("[aria-label='Sign Out']")
