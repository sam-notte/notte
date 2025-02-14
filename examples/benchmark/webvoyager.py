import argparse
import asyncio
import base64
import itertools
import json
import logging
import os
import random
import traceback

from browseruse_eval import auto_eval_by_gpt4o
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, computed_field

from eval.patcher import AgentPatcher
from eval.webvoyager.load_data import WebVoyagerTask, load_webvoyager_data
from examples.simple.agent import RaiseCondition, SimpleAgent
from notte.common.agent import AgentOutput

_ = load_dotenv()


class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int


class TaskStep(BaseModel):
    url: str
    duration_in_s: float
    token_usage: TokenUsage
    messages: list[str]


class TaskResult(BaseModel):
    agent_key: str
    finished: bool = False
    evaluation: int | str | None
    evaluation_reason: str | None
    duration_in_s: float
    agent_answer: str
    task: WebVoyagerTask
    task_id: int
    steps: list[TaskStep]

    @computed_field
    def task_description(self) -> str:
        return self.task.question

    @computed_field
    def task_website(self) -> str:
        return self.task.name

    @computed_field
    def reference_answer(self) -> str:
        return self.task.ref_answers[0].answer

    @computed_field
    def num_steps(self) -> int:
        return len(self.steps)


PROMPT = """You are a helpful web agent.
Now you are given the task: {question}.
Please interact with : {url} to get the answer.
"""


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

    outputs = []
    for i, task in enum_tasks[: args.num_tasks]:
        try:
            agent = SimpleAgent(
                model=args.model,
                headless=not args.display,
                include_screenshot=not args.no_vision,
                raise_condition=RaiseCondition.NEVER,
                disable_web_security=True,
            )

            # only use for timing step
            patcher = AgentPatcher()
            _ = patcher.log_timings(agent, ["step", "run"])
            result = await agent.run(PROMPT.format(question=task.question, url=task.url or "the web"))

            result_dict = {
                "task_id": i,
                "output": result.model_dump_json(),
                "input_tokens": patcher.input_data,
                "output_tokens": patcher.output_data,
                "timing": patcher.timing_data,
            }

            # save the dump so we can reload it, but would rather do it directly
            with open(os.path.join(args.output, f"task_{i:04d}.json"), "w") as f:
                _ = f.write(json.dumps(result_dict))

            outputs.append((i, task, patcher, result))

        except Exception as e:
            logging.error(f"Error: {e} at task {i} {traceback.format_exc()}")

    eval_client = ChatOpenAI(name="gpt-4o", temperature=0.0)

    for i, task, patcher, res in outputs:
        processed_output = await process_output(task, patcher, res, eval_client)

        with open(os.path.join(args.output, f"result_{i:04d}.json"), "w") as f:
            _ = f.write(processed_output.model_dump_json(indent=2))


async def process_output(task: WebVoyagerTask, patcher: AgentPatcher, res: AgentOutput, llm_client: ChatOpenAI):

    # # agent has the initial step (go to website) + the last step (completion), but we sort of ignore those
    steps = []
    for step_timing, agent_step, env_step, llm_call in itertools.zip_longest(
        patcher.timing_data["SimpleAgent.step"],
        res.agent_trajectory,
        [None] + res.env_trajectory,
        res.llm_usage,
        fillvalue=None,
    ):

        # we ignore actions for now, but could be useful at some point
        if agent_step is None:
            action = ""
        else:
            try:
                action = agent_step.results[0].input.description
            except IndexError:
                action = ""

        if step_timing is None:
            step_timing = 0

        if env_step is None:
            url = ""
        else:
            url = env_step.obs.metadata.url

        if llm_call is not None:
            token_usage = llm_call.usage
            messages = json.loads(json.dumps(llm_call.messages, default=str))
            messages = [message["content"] for message in messages]
        else:
            raise ValueError("No llm call")

        step = TaskStep(
            url=url,
            duration_in_s=step_timing,
            token_usage=TokenUsage(
                input_tokens=token_usage["prompt_tokens"], output_tokens=token_usage["completion_tokens"]
            ),
            messages=messages,
        )
        steps.append(step)

    screenshots = [
        base64.b64encode(x.obs.screenshot).decode() for x in res.env_trajectory if x.obs.screenshot is not None
    ]

    evaluation, reason = await auto_eval_by_gpt4o(
        res.answer, screenshots, PROMPT.format(question=task.question, url=task.url or "the web"), llm_client
    )

    task_res = TaskResult(
        agent_key="notte",
        finished=res.success,
        evaluation=evaluation,
        evaluation_reason=reason,
        duration_in_s=res.duration_in_s,
        agent_answer=res.answer,
        task=task,
        task_id=task.id,
        steps=steps,
    )
    return task_res


if __name__ == "__main__":
    asyncio.run(main())
