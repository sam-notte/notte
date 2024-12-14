from dataclasses import dataclass
from typing import Any

from PIL import Image

from notte.actions.space import ActionSpace
from notte.browser.snapshot import clean_url
from notte.utils import image


@dataclass
class Observation:
    url: str
    screenshot: bytes | None = None
    _space: ActionSpace | None = None
    data: str = ""

    @property
    def clean_url(self) -> str:
        return clean_url(self.url)

    @property
    def space(self) -> ActionSpace:
        if self._space is None:
            raise ValueError("Space is not available for this observation")
        return self._space

    @space.setter
    def space(self, space: ActionSpace) -> None:
        self._space = space

    def has_space(self) -> bool:
        return self._space is not None

    def has_data(self) -> bool:
        return self.data != ""

    def display_screenshot(self) -> Image.Image | None:
        if self.screenshot is None:
            return None
        return image.image_from_bytes(self.screenshot)

    @staticmethod
    def from_json(json: dict[str, Any]) -> "Observation":
        url: str | None = json.get("url", None)
        if not isinstance(url, str):
            raise ValueError("url must be a string")
        screenshot: bytes | None = json.get("screenshot", None)
        space: ActionSpace | None = json.get("space", None)
        if not isinstance(space, dict):
            raise ValueError("space must be a dictionary")
        return Observation(
            url=url,
            screenshot=screenshot,
            _space=ActionSpace.from_json(space),
        )


# @dataclass
# class PreObservation(Observation):
#     _space: ActionSpace | None = None  # type: ignore

#     @property
#     @override
#     def space(self) -> ActionSpace:
#         raise ValueError("space is not available for pre-observations")
