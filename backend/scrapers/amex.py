import tempfile
from datetime import date
from pathlib import Path
from backend.scrapers.base import BaseScraper

class AmexScraper(BaseScraper):
    ALLOWED_DOMAINS = [
        "americanexpress.com", "www.americanexpress.com", "global.americanexpress.com",
        "apigw.americanexpress.com", "functions.americanexpress.com",
        "identity-mirror.americanexpress.com", "identitymirroruplifthydra.americanexpress.com",
        "omns.americanexpress.com", "iwmapapi.americanexpress.com",
        "aexp-static.com", "www.aexp-static.com",
    ]
    SOURCE = "amex"
    LOGIN_URL = "https://www.americanexpress.com/en-us/account/login"
    DASHBOARD_URL_PATTERN = "https://www.americanexpress.com/en-us/dashboard**"
    MFA_URL_PATTERNS = ["**/two-step-verification/**", "**/account/verify**"]

    async def login(self) -> None:
        await self._page.goto(self.LOGIN_URL, wait_until="domcontentloaded")
        await self._page.wait_for_selector("#eliloUserID", timeout=20000)
        await self._page.fill("#eliloUserID", self._username)
        await self._page.fill("#eliloPassword", self._password)
        await self._page.click("#loginSubmit")
        await self._wait_for_login()

    async def download_transactions(self, since: date) -> Path:
        await self._page.goto("https://www.americanexpress.com/en-us/account/activity")
        await self._page.wait_for_selector("[data-testid='download-transactions']", timeout=10000)
        await self._page.click("[data-testid='download-transactions']")
        await self._page.wait_for_selector("[data-testid='custom-date-range']", timeout=5000)
        await self._page.click("[data-testid='custom-date-range']")
        await self._page.fill("[data-testid='start-date']", since.strftime("%m/%d/%Y"))
        await self._page.fill("[data-testid='end-date']", date.today().strftime("%m/%d/%Y"))
        await self._page.select_option("[data-testid='file-format']", "csv")
        tmp_dir = Path(tempfile.mkdtemp())
        async with self._page.expect_download() as download_info:
            await self._page.click("[data-testid='download-btn']")
        download = await download_info.value
        dest = tmp_dir / f"amex_{since.isoformat()}.csv"
        await download.save_as(str(dest))
        return dest

    async def logout(self) -> None:
        await self._page.click("[data-testid='account-menu-trigger']")
        await self._page.click("[data-testid='logout']")
