import argparse
import asyncio
import json
import logging
import os
import random
import traceback

from browser_use import Agent as BrowserUseAgent
from browser_use.browser.browser import Browser, BrowserConfig
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from eval.patcher import AgentPatcher
from eval.webvoyager.load_data import load_webvoyager_data

_ = load_dotenv()


async def main():
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--output", type=str, default="./data", help="Root directory for output files")
    _ = parser.add_argument("--max-steps", type=int, default=20, help="Max steps for the agent")
    _ = parser.add_argument("--model", type=str, default="gpt-4o", help="Agent reasoning model")
    _ = parser.add_argument("--no-vision", action="store_true", help="Dont show screenshots to agent")
    _ = parser.add_argument("--display", action="store_true", help="Whether to display browser")

    # if running a few, random tasks
    _ = parser.add_argument("--num-tasks", type=int, default=-1, help="Max number of tasks to run")
    _ = parser.add_argument("--shuffle", action="store_true", help="Shuffle order of tasks")
    _ = parser.add_argument("--seed", type=int, default=-1, help="Random seed when shuffling")
    args = parser.parse_args()

    random.seed(args.seed)

    os.makedirs(args.output, exist_ok=True)

    # Configure root logger
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Add our file handler
    file_handler = logging.FileHandler(os.path.join(args.output, "agent.log"))
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    root.addHandler(file_handler)

    # Capture all third-party loggers
    for name in logging.root.manager.loggerDict:
        logger = logging.getLogger(name)
        # Remove any existing handlers
        logger.handlers = []
        # Ensure it propagates to root
        logger.propagate = True

    tasks = load_webvoyager_data()
    enum_tasks = list(enumerate(tasks))

    if args.shuffle:
        random.shuffle(enum_tasks)

    for i, task in enum_tasks[: args.num_tasks]:
        try:
            prompt = f"""You are a helpful web agent.
            Now you are given the task: {task.question}.
            Please interact with : {task.url or "the web"} to get the answer.
            """

            llm = ChatOpenAI(
                model=args.model,
                temperature=0,
            )
            browser = Browser(
                config=BrowserConfig(
                    headless=not args.display,
                )
            )
            agent = BrowserUseAgent(
                browser=browser,
                task=prompt,
                llm=llm,
                use_vision=not args.no_vision,
            )

            patcher = AgentPatcher()
            _ = patcher.log_io(agent.llm, ["invoke", "ainvoke"])
            _ = patcher.log_timings(agent, ["step", "run"])
            result = await agent.run(max_steps=args.max_steps)

            results = {
                "task_id": i,
                "output": result.model_dump(),
                "input_tokens": patcher.input_data,
                "output_tokens": patcher.output_data,
                "timing": patcher.timing_data,
            }

            with open(os.path.join(args.output, f"task_{i:04d}.json"), "w") as f:
                _ = f.write(json.dumps(results))

        except Exception as e:
            logging.error(f"Error: {e} at task {i} {traceback.format_exc()}")


if __name__ == "__main__":
    asyncio.run(main())
