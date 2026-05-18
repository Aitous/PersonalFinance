import tempfile
from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import ClassVar, List
from urllib.parse import urlparse
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

class BaseScraper(ABC):
    ALLOWED_DOMAINS: ClassVar[List[str]] = []
    SOURCE: ClassVar[str] = ""

    def __init__(self, username: str, password: str):
        self._username = username
        self._password = password
        self._browser: Browser = None
        self._context: BrowserContext = None
        self._page: Page = None
        self._logged_in = False

    def _is_allowed(self, url: str) -> bool:
        hostname = urlparse(url).hostname or ""
        return any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in self.ALLOWED_DOMAINS
        )

    def _assert_allowed(self, url: str) -> None:
        if not self._is_allowed(url):
            raise ValueError(f"Navigation to {url} blocked — not in allowed domains {self.ALLOWED_DOMAINS}")

    async def _block_mutations_after_login(self, route, request):
        if request.method != "GET":
            await route.abort()
        else:
            await route.continue_()

    async def _setup_context(self) -> None:
        playwright = await async_playwright().start()
        self._browser = await playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context(accept_downloads=True)

        async def enforce_allowlist(route, request):
            if not self._is_allowed(request.url):
                await route.abort()
            else:
                await route.continue_()

        await self._context.route("**/*", enforce_allowlist)
        self._page = await self._context.new_page()

    async def _enable_mutation_blocking(self) -> None:
        await self._context.route("**/*", self._block_mutations_after_login)

    async def _teardown(self) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()

    @abstractmethod
    async def login(self) -> None: ...

    @abstractmethod
    async def download_transactions(self, since: date) -> Path: ...

    @abstractmethod
    async def logout(self) -> None: ...

    async def sync(self, since: date) -> Path:
        await self._setup_context()
        try:
            await self.login()
            self._logged_in = True
            await self._enable_mutation_blocking()
            download_path = await self.download_transactions(since)
            await self.logout()
            return download_path
        finally:
            await self._teardown()
