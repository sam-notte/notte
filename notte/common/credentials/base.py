from abc import ABC, abstractmethod
from typing import Optional

from notte.actions.base import ActionParameterValue
from notte.common.credentials.models import Credentials


class BaseVault(ABC):
    """Base class for vault implementations that handle credential storage and retrieval."""

    @abstractmethod
    def add_credentials(self, url: str, username: str, password: str) -> None:
        """Store credentials for a given URL"""
        pass

    @abstractmethod
    def get_credentials(self, url: str) -> Optional[Credentials]:
        """Retrieve credentials for a given URL"""
        pass

    @abstractmethod
    def remove_credentials(self, url: str) -> None:
        """Remove credentials for a given URL"""
        pass

    def replace_placeholder_credentials(
        self, url: str | None, value: str | list[ActionParameterValue] | None
    ) -> str | list[ActionParameterValue] | None:
        """Replace placeholder credentials with actual credentials

        Args:
            url: The URL to get credentials for
            value: Either a string (text_label) or list of ActionParameterValue objects

        Returns:
            The value with credentials replaced, maintaining the same type as input
        """
        if not value:
            return value

        if not url:
            return value

        # Get credentials for current domain
        creds = self.get_credentials(url)
        if not creds:
            return value

        # Handle string case (text_label)
        if isinstance(value, str):
            if value == "login@login_page.com":
                return creds.username
            elif value == "login_password":
                return creds.password
            return value

        # Handle ActionParameterValue list case
        new_params = []
        for param in value:
            new_param = ActionParameterValue(name=param.name, value=param.value)

            if param.value == "login@login_page.com":
                new_param.value = creds.username
            elif param.value == "login_password":
                new_param.value = creds.password

            new_params.append(new_param)

        return new_params


def get_credentials_prompt() -> str:
    """Get the credentials system prompt."""
    return """- If you are asked to signin/signup to continue, fill the
    parameters with login@login_page.com / login_password"""
