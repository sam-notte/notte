from loguru import logger
from playwright.async_api import Page
from typing_extensions import final

from notte.browser.driver import BrowserDriver
from notte.browser.snapshot import BrowserSnapshot
from notte.controller.actions import (
    BaseAction,
    CheckAction,
    ClickAction,
    CompletionAction,
    FillAction,
    GoBackAction,
    GoForwardAction,
    GotoAction,
    ListDropdownOptionsAction,
    PressKeyAction,
    ReloadAction,
    ScrapeAction,
    ScreenshotAction,
    ScrollDownAction,
    ScrollUpAction,
    SelectDropdownOptionAction,
    WaitAction,
)
from notte.pipe.preprocessing.dom.dropdown_menu import dropdown_menu_options


@final
class BrowserController:
    def __init__(self, driver: BrowserDriver) -> None:
        self.driver: BrowserDriver = driver

    @property
    def page(self) -> Page:
        return self.driver.page

    async def execute(self, action: BaseAction) -> BrowserSnapshot:
        _press_enter = False
        match action:
            case GotoAction(url=url):
                return await self.driver.goto(url)
            case WaitAction(time_ms=time_ms):
                await self.page.wait_for_timeout(time_ms)
            case GoBackAction():
                _ = await self.page.go_back()
            case GoForwardAction():
                _ = await self.page.go_forward()
            case ReloadAction():
                _ = await self.page.reload()
                await self.driver.long_wait()
            case PressKeyAction(key=key):
                await self.page.keyboard.press(key)
            case ScrollUpAction(amount=amount):
                if amount is not None:
                    await self.page.mouse.wheel(delta_x=0, delta_y=amount)
                else:
                    await self.page.keyboard.press("PageDown")
            case ScrollDownAction(amount=amount):
                if amount is not None:
                    await self.page.mouse.wheel(delta_x=0, delta_y=-amount)
                else:
                    await self.page.keyboard.press("PageUp")
            case ScreenshotAction():
                return await self.driver.snapshot(screenshot=True)
            case ScrapeAction():
                raise NotImplementedError("Scrape action is not supported in the browser controller")
            case CompletionAction(success=success, answer=answer):
                logger.info(f"Completion action: status={'success' if success else 'failure'} with answer = {answer}")
                await self.driver.close()
            # Interaction actions
            case ClickAction(selector=selector, press_enter=press_enter):
                if press_enter is not None:
                    _press_enter = press_enter
                if selector is None:
                    raise ValueError("Selector is required for ClickAction")
                await self.page.click(f"xpath={selector}")
            case FillAction(selector=selector, value=value, press_enter=press_enter):
                if press_enter is not None:
                    _press_enter = press_enter
                if selector is None:
                    raise ValueError("Selector is required for FillAction")
                await self.page.fill(f"xpath={selector}", value)
            case CheckAction(selector=selector, value=value, press_enter=press_enter):
                if press_enter is not None:
                    _press_enter = press_enter
                if selector is None:
                    raise ValueError("Selector is required for CheckAction")
                if value:
                    await self.page.check(f"xpath={selector}")
                else:
                    await self.page.uncheck(selector)
            case SelectDropdownOptionAction(
                selector=selector, value=value, press_enter=press_enter, option_selector=option_selector
            ):
                if press_enter is not None:
                    _press_enter = press_enter
                if selector is None:
                    raise ValueError("Selector is required for `SelectDropdownOptionAction`")
                # Get element info
                select_element = await self.page.query_selector(f"xpath={selector}")
                if not select_element:
                    raise ValueError(f"Select element not found: {selector}")

                # Check if it's a standard HTML select
                tag_name: str = await select_element.evaluate("el => el.tagName.toLowerCase()")
                if tag_name == "select":
                    # Handle standard HTML select
                    _ = await self.page.select_option(f"xpath={selector}", value)
                else:
                    # Handle non-standard select
                    # await self.page.click(f"xpath={selector}")
                    await self.page.click(f"xpath={option_selector}")

            case ListDropdownOptionsAction(selector=selector):
                if selector is None:
                    raise ValueError("Selector is required for ListDropdownOptionsAction")
                options = await dropdown_menu_options(self.page, selector)
                logger.info(f"Dropdown options: {options}")
                raise NotImplementedError("ListDropdownOptionsAction is not supported in the browser controller")
            case _:
                raise ValueError(f"Unsupported action type: {type(action)}")
        if _press_enter:
            logger.info(f"🪦 Pressing enter for action {action.id}")
            await self.driver.short_wait()
            await self.page.keyboard.press("Enter")
        await self.driver.short_wait()
        return await self.driver.snapshot()

    async def execute_multiple(self, actions: list[BaseAction]) -> list[BrowserSnapshot]:
        snapshots: list[BrowserSnapshot] = []
        for action in actions:
            snapshots.append(await self.execute(action))
        return snapshots
