from pathlib import Path


def get_credentials_prompt() -> str:
    """Get the credentials system prompt."""
    system_prompt_file = Path(__file__).parent / "system.md"
    if not system_prompt_file.exists():
        raise FileNotFoundError(f"Credentials system prompt not found at {system_prompt_file}")
    return system_prompt_file.read_text()
