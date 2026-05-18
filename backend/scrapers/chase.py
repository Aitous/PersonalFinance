import tempfile
from datetime import date
from pathlib import Path
from backend.scrapers.base import BaseScraper

class ChaseScraper(BaseScraper):
    ALLOWED_DOMAINS = ["chase.com", "www.chase.com"]
    SOURCE = "chase"
    LOGIN_URL = "https://www.chase.com"

    async def login(self) -> None:
        await self._page.goto(self.LOGIN_URL)
        await self._page.wait_for_selector("#userId-input", timeout=15000)
        await self._page.fill("#userId-input", self._username)
        await self._page.click("#password-input")
        await self._page.fill("#password-input", self._password)
        await self._page.click("#signin-button")
        await self._page.wait_for_url("**/dashboard/**", timeout=30000)

    async def download_transactions(self, since: date) -> Path:
        await self._page.goto("https://www.chase.com/digital/advanced-transactions/activity")
        await self._page.wait_for_selector("[data-testid='download-activity-button']", timeout=10000)
        await self._page.click("[data-testid='date-range-custom']")
        await self._page.fill("[data-testid='start-date-input']", since.strftime("%m/%d/%Y"))
        await self._page.fill("[data-testid='end-date-input']", date.today().strftime("%m/%d/%Y"))
        await self._page.select_option("[data-testid='file-type-select']", "csv")
        tmp_dir = Path(tempfile.mkdtemp())
        async with self._page.expect_download() as download_info:
            await self._page.click("[data-testid='download-button']")
        download = await download_info.value
        dest = tmp_dir / f"chase_{since.isoformat()}.csv"
        await download.save_as(str(dest))
        return dest

    async def logout(self) -> None:
        await self._page.click("[data-testid='global-header-account-icon']")
        await self._page.click("[data-testid='logout-link']")
