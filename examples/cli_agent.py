import typer
from dotenv import load_dotenv
from notte_agent import Agent
from notte_core.common.config import LlmModel

# Load environment variables
_ = load_dotenv()


def main(
    task: str = typer.Option(..., help="Task to perform"),
    reasoning_model: str = typer.Option(LlmModel.default, help="Reasoning model to use"),
    headless: bool = typer.Option(False, help="Run in headless mode"),
):
    reasoning_model = LlmModel(reasoning_model) if isinstance(reasoning_model, str) else reasoning_model.default
    headless = headless if isinstance(headless, bool) else headless.default
    agent = Agent(headless=headless, reasoning_model=reasoning_model)
    return agent.run(task)


if __name__ == "__main__":
    print(typer.run(main))

# export task="open google flights and book cheapest flight from nyc to sf"
# uv run examples/cli_agent.py --task $task --reasoning_model "openai/gpt-4o"
