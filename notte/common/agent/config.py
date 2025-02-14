from argparse import ArgumentParser, Namespace
from typing import Any, ClassVar, get_type_hints

from pydantic import BaseModel

from notte.env import NotteEnvConfig


class AgentConfig(BaseModel):
    model: str = "openai/gpt-4o"
    headless: bool = False
    max_steps: int = 20
    include_screenshot: bool = False
    max_history_tokens: int = 16000
    max_error_length: int = 500
    raise_on_failure: bool = False
    max_consecutive_failures: int = 3
    disable_web_security: bool = False

    def update_env_config(self, env_config: NotteEnvConfig) -> NotteEnvConfig:
        env_config.browser.disable_web_security = self.disable_web_security
        env_config.max_steps = self.max_steps
        env_config.browser.headless = self.headless
        return env_config

    @staticmethod
    def _get_arg_type(python_type: Any) -> Any:
        """Maps Python types to argparse types."""
        type_map = {
            str: str,
            int: int,
            float: float,
            bool: bool,
        }
        return type_map.get(python_type, str)

    @classmethod
    def create_parser(cls) -> ArgumentParser:
        """Creates an ArgumentParser with all the fields from the config."""
        parser = ArgumentParser()
        hints = get_type_hints(cls)

        for field_name, field_info in cls.model_fields.items():
            field_type = hints.get(field_name)
            if isinstance(field_type, ClassVar):
                continue

            default = field_info.default
            help_text = field_info.description or ""
            arg_type = cls._get_arg_type(field_type)

            _ = parser.add_argument(
                f"--{field_name.replace('_', '-')}",
                type=arg_type,
                default=default,
                help=help_text,
            )

        return parser

    @classmethod
    def from_args(cls, args: Namespace) -> "AgentConfig":
        """Creates an AgentConfig from a Namespace of arguments."""
        return cls(**vars(args))
