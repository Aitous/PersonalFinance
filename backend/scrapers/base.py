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
        self._playwright = None
        self._browser: Browser = None
        self._context: BrowserContext = None
        self._page: Page = None

    def _is_allowed(self, url: str) -> bool:
        hostname = urlparse(url).hostname or ""
        return any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in self.ALLOWED_DOMAINS
        )

    def _assert_allowed(self, url: str) -> None:
        if not self._is_allowed(url):
            raise ValueError(f"Navigation to {url} blocked — not in allowed domains {self.ALLOWED_DOMAINS}")

    async def _setup_context(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = await self._browser.new_context(
            accept_downloads=True,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        await self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        async def enforce_allowlist(route, request):
            if not self._is_allowed(request.url):
                await route.abort()
            else:
                await route.continue_()

        await self._context.route("**/*", enforce_allowlist)
        self._page = await self._context.new_page()

    async def _enable_mutation_blocking(self) -> None:
        # Replaces the allowlist-only handler with one that enforces both
        # the allowlist AND blocks non-GET requests. A second context.route()
        # call would shadow the first handler entirely in Playwright.
        async def allowlist_and_block_mutations(route, request):
            if not self._is_allowed(request.url):
                await route.abort()
            elif request.method != "GET":
                await route.abort()
            else:
                await route.continue_()

        await self._context.unroute("**/*")
        await self._context.route("**/*", allowlist_and_block_mutations)

    async def _teardown(self) -> None:
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    @abstractmethod
    async def login(self) -> None: ...

    @abstractmethod
    async def download_transactions(self, since: date) -> Path: ...

    @abstractmethod
    async def logout(self) -> None: ...

    async def sync(self, since: date) -> Path:
        try:
            await self._setup_context()
            await self.login()
            await self._enable_mutation_blocking()
            download_path = await self.download_transactions(since)
            await self.logout()
            return download_path
        finally:
            await self._teardown()
