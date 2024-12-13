from abc import ABC, abstractmethod
from typing import Literal, NotRequired, TypedDict, Unpack

from loguru import logger
from playwright.async_api import Page, Playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from typing_extensions import override

from notte.actions.base import ExecutableAction
from notte.actions.code import get_action_from_node, get_playwright_code_from_selector
from notte.actions.executor import get_executor, get_executor_from_code
from notte.browser.context import Context
from notte.browser.node_type import A11yTree, NotteNode
from notte.browser.snapshot import BrowserSnapshot
from notte.common.resource import AsyncResource
from notte.pipe.resolution import ActionNodeResolutionPipe


class BrowserArgs(TypedDict):
    headless: NotRequired[bool]
    timeout: NotRequired[int]
    screenshot: NotRequired[bool]


DEFAULT_LOADING_TIMEOUT = 15000
DEFAULT_WAITING_TIMEOUT = 500


class PlaywrightResource:

    def __init__(self, **kwargs: Unpack[BrowserArgs]) -> None:
        self.playwright: Playwright | None = None
        self.args: BrowserArgs = kwargs
        self._page: Page | None = None
        self._playwright: Playwright | None = None
        self.timeout: int = kwargs.get("timeout", DEFAULT_LOADING_TIMEOUT)
        self.headless: bool = kwargs.get("headless", True)

    async def start(self) -> None:
        self.playwright = await async_playwright().start()
        browser = await self.playwright.chromium.launch(headless=self.headless)
        context = await browser.new_context()
        self._page = await context.new_page()
        self._page.set_default_timeout(self.timeout)

    async def close(self) -> None:
        await self.page.close()
        if self.playwright:
            await self.playwright.stop()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Page not initialized. Call `start` first.")
        return self._page


class BaseBrowserDriver(ABC):

    def __init__(self) -> None:
        self._last_snapshot: BrowserSnapshot | None = None

    @abstractmethod
    async def _snapshot(self) -> BrowserSnapshot:
        pass

    async def snapshot(self) -> BrowserSnapshot:
        snapshot = await self._snapshot()
        id_snapshot = self.id_snapshot(snapshot)
        self._last_snapshot = id_snapshot
        return id_snapshot

    def id_snapshot(self, snapshot: BrowserSnapshot) -> BrowserSnapshot:
        # TODO: add id to the snapshot
        return snapshot

    @abstractmethod
    async def goto(self, url: str) -> BrowserSnapshot:
        pass

    @abstractmethod
    async def press(self, key: str = "Enter") -> BrowserSnapshot:
        pass

    @abstractmethod
    async def _execute(self, node_id: str, param: str | None = None) -> None:
        # TODO: execute the action
        pass

    async def execute(
        self,
        action: ExecutableAction,
        enter: bool = False,
    ) -> BrowserSnapshot:
        # TODO: check node_id is in the snapshot
        await self._execute(action.node.id, action.params_values[0].value)
        # TODO: wait for the page to be updated
        if enter:
            _ = await self.press("Enter")
        # TODO: wait for the page to be updated
        return await self.snapshot()


class NotteBrowserDriver(BaseBrowserDriver, AsyncResource):

    def __init__(self, **browser_args: Unpack[BrowserArgs]) -> None:
        self._playwright: PlaywrightResource = PlaywrightResource(**browser_args)
        self._screenshot: bool = browser_args.get("screenshot", True)
        AsyncResource.__init__(self, self._playwright)
        BaseBrowserDriver.__init__(self)

    @property
    def _page(self) -> Page:
        return self._playwright.page

    @override
    async def _snapshot(self, retries: int = 5) -> BrowserSnapshot:
        if not self._page:
            raise RuntimeError("Browser not started. Call `start` first.")
        if retries <= 0:
            raise ValueError("Browser snapshot failed after 5 retries to get a non-empty web page")
        html_content = await self._page.content()
        a11y_tree = A11yTree(
            simple=await self._page.accessibility.snapshot(),  # type: ignore
            raw=await self._page.accessibility.snapshot(interesting_only=False),  # type: ignore
        )
        if len(a11y_tree.simple.get("children", [])) == 0:
            logger.warning(f"Simple tree is empty for page {self._page.url}. Retry in {DEFAULT_WAITING_TIMEOUT}ms")
            await self._page.wait_for_timeout(DEFAULT_WAITING_TIMEOUT)
            return await self._snapshot(retries=retries - 1)

        screenshot = await self._page.screenshot() if self._screenshot else None
        return BrowserSnapshot(
            url=self._page.url,
            html_content=html_content,
            a11y_tree=a11y_tree,
            screenshot=screenshot,
        )

    @override
    async def press(self, key: str = "Enter") -> BrowserSnapshot:
        if not self._page:
            raise RuntimeError("Browser not started. Call `start` first.")
        await self._page.keyboard.press(key)
        # update context
        await self._page.wait_for_timeout(DEFAULT_WAITING_TIMEOUT)
        return await self.snapshot()

    @override
    async def goto(
        self,
        url: str,
        wait_for: Literal["domcontentloaded", "load", "networkidle"] = "networkidle",
    ) -> BrowserSnapshot:
        if not self._page:
            raise RuntimeError("Browser not started. Call `start` first.")
        _ = await self._page.goto(url)
        try:
            await self._page.wait_for_load_state(wait_for, timeout=self._playwright.timeout)
        except PlaywrightTimeoutError:
            logger.warning(f"Timeout while waiting for {wait_for} state for '{url}'")
        await self._page.wait_for_timeout(DEFAULT_WAITING_TIMEOUT)
        return await self.snapshot()

    @override
    async def _execute(self, node_id: str, param: str | None = None) -> None:
        # TODO: execute the action
        node: NotteNode = self._last_snapshot.a11y_tree.raw.get(node_id)
        node.attributes_post = await ActionNodeResolutionPipe(self).compute_attributes(node, self._last_snapshot)
        action_type = get_action_from_node(node)

        code = get_playwright_code_from_selector(
            selectors=node.attributes_post.selectors,
            action_type=action_type,
            param_value=param,
        )

        action_executor = get_executor_from_code(code)
        await action_executor(self._page)


class BrowserDriver(AsyncResource):

    def __init__(
        self,
        **browser_args: Unpack[BrowserArgs],
    ) -> None:
        self._playwright: PlaywrightResource = PlaywrightResource(**browser_args)
        self._screenshot: bool = browser_args.get("screenshot", True)
        super().__init__(self._playwright)

    @property
    def page(self) -> Page:
        return self._playwright.page

    async def snapshot(self, retries: int = 5) -> BrowserSnapshot:
        if not self.page:
            raise RuntimeError("Browser not started. Call `start` first.")
        if retries <= 0:
            raise ValueError("Browser snapshot failed after 5 retries to get a non-empty web page")
        html_content = await self.page.content()
        a11y_tree = A11yTree(
            simple=await self.page.accessibility.snapshot(),  # type: ignore
            raw=await self.page.accessibility.snapshot(interesting_only=False),  # type: ignore
        )
        if len(a11y_tree.simple.get("children", [])) == 0:
            logger.warning(f"Simple tree is empty for page {self.page.url}. Retry in {DEFAULT_WAITING_TIMEOUT}ms")
            await self.page.wait_for_timeout(DEFAULT_WAITING_TIMEOUT)
            return await self.snapshot(retries=retries - 1)

        screenshot = await self.page.screenshot() if self._screenshot else None
        return BrowserSnapshot(
            url=self.page.url,
            html_content=html_content,
            a11y_tree=a11y_tree,
            screenshot=screenshot,
        )

    async def press(self, key: str = "Enter") -> BrowserSnapshot:
        if not self.page:
            raise RuntimeError("Browser not started. Call `start` first.")
        await self.page.keyboard.press(key)
        # update context
        await self.page.wait_for_timeout(DEFAULT_WAITING_TIMEOUT)
        return await self.snapshot()

    async def goto(
        self,
        url: str,
        wait_for: Literal["domcontentloaded", "load", "networkidle"] = "networkidle",
    ) -> BrowserSnapshot:
        if not self.page:
            raise RuntimeError("Browser not started. Call `start` first.")
        _ = await self.page.goto(url)
        try:
            await self.page.wait_for_load_state(wait_for, timeout=self._playwright.timeout)
        except PlaywrightTimeoutError:
            logger.warning(f"Timeout while waiting for {wait_for} state for '{url}'")
        await self.page.wait_for_timeout(DEFAULT_WAITING_TIMEOUT)
        return await self.snapshot()

    async def execute_action(
        self,
        action: ExecutableAction,
        context: Context,
        enter: bool = False,
    ) -> BrowserSnapshot:
        """Execute action in async mode"""
        if not self.page:
            raise RuntimeError("Browser not started. Call `start` first.")
        # TODO: refactor this ()
        if self.page.url != context.snapshot.url:
            raise ValueError(("Browser is not on the expected page. " "Use `goto` to navigate to the expected page."))
        action_executor = get_executor(action)
        await action_executor(self.page)
        # TODO: find a better way to wait for the page to be updated
        await self.page.wait_for_timeout(DEFAULT_WAITING_TIMEOUT)
        if enter:
            _ = await self.press("Enter")
            await self.page.wait_for_timeout(DEFAULT_WAITING_TIMEOUT)
        return await self.snapshot()
