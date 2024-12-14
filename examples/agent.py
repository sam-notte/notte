import asyncio
from argparse import ArgumentParser

from dotenv import load_dotenv
from loguru import logger

from notte.common.parser import BaseNotteParser, Parser
from notte.env import NotteEnv
from notte.llms.engine import LLMEngine

parser: ArgumentParser = ArgumentParser()
parser.add_argument(
    "--goal",
    type=str,
    required=True,
)
parser.add_argument(
    "--model",
    type=str,
    default="openai/gpt-4o",
)

parser.add_argument(
    "--headless",
    type=bool,
    default=False,
)

parser.add_argument(
    "--max-steps",
    type=int,
    default=10,
)


class Agent:
    def __init__(
        self,
        goal: str,
        model: str,
        max_steps: int,
        headless: bool,
        parser: Parser | None = None,
    ):
        self.goal: str = goal
        self.model: str = model
        self.llm: LLMEngine = LLMEngine()
        _ = load_dotenv()
        # You should tune this parser to your needs
        self.max_steps: int = max_steps
        self.headless: bool = headless
        self.parser: Parser = parser or BaseNotteParser()

    def think(self, messages: list[dict[str, str]]) -> str:
        response = self.llm.completion(
            messages=messages,
            model=self.model,
        )
        return response.choices[0].message.content

    async def ask_notte(self, env: NotteEnv, text: str) -> str:
        """
        This function is used to ask the Notte environment to perform an action.
        It is used to interact with the Notte environment in a conversational way.

        We provided a parse parser to demonstrate how one could interact with the Notte environment
        in a conversational way.
        However, users should implement their own parser to fit their needs.
        """
        notte_endpoint = self.parser.which(text)
        logger.debug(f"Picking {notte_endpoint} endpoint")
        match notte_endpoint:
            case "observe":
                observe_params = self.parser.observe(text)
                obs = await env.observe(observe_params.url)
                return self.parser.textify(obs)
            case "step":
                step_params = self.parser.step(text)
                obs = await env.step(step_params.action_id, step_params.params)
                return self.parser.textify(obs)
            case _:
                logger.debug(f"Unknown provided endpoint: {notte_endpoint}")
                return self.parser.rules()

    def is_done(self, text: str) -> bool:
        return self.parser.is_done(text)

    async def run(self) -> None:
        logger.info("🚀 starting")
        # Notte is run in full mode, which means that both data extraction and action listing are enabled
        async with NotteEnv(headless=self.headless) as env:
            messages = [
                {
                    "role": "system",
                    "content": "You are a helpful web agent. Your goal is to " + self.goal,
                },
                {"role": "user", "content": await self.ask_notte(env, "")},
            ]

            for i in range(self.max_steps):
                logger.info(f"> step {i}: looping in")
                # Let the LLM Agent think about the next action
                resp: str = self.think(messages)
                messages.append({"role": "assistant", "content": resp})
                logger.info(f"🤖 {resp}")
                # Check if the task is done
                if self.is_done(resp):
                    done_answer = self.parser.get_done_answer(resp)
                    logger.info(f"😎 task completed with answer: {done_answer}")
                    return
                # Ask Notte to perform the selected action
                obs: str = await self.ask_notte(env, resp)
                messages.append({"role": "user", "content": obs})
                logger.info(f"🌌 {obs}")
            # If the task is not done, raise an error
            logger.info(f"👿 failed to solve task in {self.max_steps} steps")


if __name__ == "__main__":
    args = parser.parse_args()
    out = asyncio.run(
        Agent(
            goal=args.goal,
            model=args.model,
            max_steps=args.max_steps,
            headless=args.headless,
        ).run()
    )
