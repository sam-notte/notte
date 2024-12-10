from dataclasses import dataclass

from notte.browser.node_type import A11yTree


def clean_url(url: str) -> str:
    base = url.split("?")[0]
    if base.endswith("/"):
        base = base[:-1]
    if base.endswith("#"):
        base = base[:-1]
    base = base.replace("http://", "").replace("https://", "")
    base = base.replace("www.", "")
    return base


@dataclass
class BrowserSnapshot:
    url: str
    html_content: str
    a11y_tree: A11yTree
    screenshot: bytes | None

    @property
    def clean_url(self) -> str:
        return clean_url(self.url)
