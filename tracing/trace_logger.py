from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import Page, Route, async_playwright


async def save_snapshot(page: Page, snapshot_path: Path):
    """
    Saves the current page as `index.html` and downloads all additional resources.
    Args:
        page: The Playwright Page object.
        snapshot_path: Path to save the snapshot.
    """
    snapshot_path.mkdir(parents=True, exist_ok=True)

    # Save the main page content as `index.html`
    main_html_path = snapshot_path / "index.html"
    content = await page.content()
    with main_html_path.open("w", encoding="utf-8") as f:
        _ = f.write(content)
    print(f"Saved main page as: {main_html_path}")

    # Intercept and save all additional resources (CSS, JS, images, etc.)
    async def save_resource(route: Route) -> None:
        url = route.request.url
        parsed_url = urlparse(url)
        if not parsed_url.path:
            await route.continue_()
            return

        # Clean up URL path for a valid filename
        resource_name = parsed_url.path.strip("/").replace("/", "_")
        if not resource_name:
            resource_name = "index"  # Fallback for empty paths
        if "." not in resource_name:
            resource_name += ".bin"  # Default extension for binary resources

        file_path = snapshot_path / resource_name
        try:
            # Fetch and save the resource
            response = await route.fetch()
            body = await response.body()
            with file_path.open("wb") as f:
                _ = f.write(body)
            print(f"Saved resource: {file_path}")
        except Exception as e:
            print(f"Failed to save resource {url}: {e}")

        await route.continue_()

    # Intercept network requests for this snapshot
    await page.context.route("**/*", save_resource)

    # Reload the page to trigger resource downloads
    _ = await page.reload()


async def trace_logger(
    url: str,
    steps: list[Callable[[Page], Awaitable[None]]],
    snapshot_dir: str = "./website_snapshots",
):
    snapshot_dir: Path = Path(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Set headless=True if you don't want a visible browser
        context = await browser.new_context()
        page = await context.new_page()

        # Directory to store snapshots

        # Navigate to the initial page
        _ = await page.goto(url)  # Replace with your target website
        await save_snapshot(page, snapshot_dir / "step0")

        # Example actions (trace steps)
        # 1. Click a button (replace with actual selector)
        for i, step in enumerate(steps):
            try:
                await step(page)
                await save_snapshot(page, snapshot_dir / f"step{i+1}")
            except Exception as e:
                print(f"Step {i+1} failed: {e}")
        # Add more steps as needed
        await browser.close()
