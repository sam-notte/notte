import argparse
import json
import logging
import os
from glob import glob
from typing import Any

from browseruse_eval import auto_eval_by_gpt4o
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, computed_field
from tqdm import tqdm

from eval.webvoyager.load_data import WebVoyagerTask, load_webvoyager_data


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


def parse_agent_output(agent_output: dict[str, Any]) -> str:

    try:
        final_output = agent_output["output"]["history"][-1]["model_output"]["action"][-1]["done"]["text"]
    except Exception:
        try:
            final_output = agent_output["output"]["history"][-1]["model_output"]["current_state"]["memory"]
        except Exception:
            final_output = "Could not parse response"

    return final_output


async def evaluate_browseruse(
    agent_task: dict[str, Any], task: WebVoyagerTask, llm: ChatOpenAI
) -> tuple[str, str, str]:

    agent_output = parse_agent_output(agent_task)
    screenshots = []

    for hist_step in agent_task["output"]["history"]:
        if "state" in hist_step:
            screenshots.append(hist_step["state"]["screenshot"])

    decision, reasoning = await auto_eval_by_gpt4o(agent_output, screenshots, task.question, llm)
    return agent_output, decision, reasoning


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="gpt-4o", help="Model to use for evaluation")
    parser.add_argument("--input-glob", type=str, required=True, help="Glob pattern for input files")
    parser.add_argument("--agent-key", type=str, required=True, help="Name of the agent in output table")
    parser.add_argument("--output", type=str, required=True, help="Name of the output file (jsonl)")
    parser.add_argument("--log-file", type=str, default="eval.log", help="Log file path")

    # invocation function, timing (depends on capture)
    parser.add_argument(
        "--llm-invocation-function",
        type=str,
        default="BaseChatModel.ainvoke",
        help="LLM call that we patch during benchmark",
    )
    parser.add_argument(
        "--step-function", type=str, default="Agent.step", help="Name of function that runs a single step (for timing)"
    )
    parser.add_argument(
        "--run-function", type=str, default="Agent.run", help="Name of funtcion that runs e2e (for timing)"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(args.log_file), logging.StreamHandler()],
    )
    args = parser.parse_args()

    tasks = load_webvoyager_data()
    agent_tasks = sorted(glob(args.input_glob))

    llm = ChatOpenAI(model=args.model)

    if os.path.isfile(args.output):
        raise ValueError(f"Output file {args.output} already exists")

    with open(args.output, "a") as output_file:
        for task_path in tqdm(agent_tasks):

            with open(task_path) as f:
                agent_task = json.load(f)

            task_id = agent_task["task_id"]
            webvoyager_task = tasks[task_id]

            agent_output, evaluation, reason = await evaluate_browseruse(agent_task, webvoyager_task, llm)

            steps = []
            for output_tokens, step_timing, state in zip(
                agent_task["output_tokens"][args.llm_invocation_function],
                agent_task["timing"][args.step_function],
                agent_task["output"]["history"],
            ):
                token_usage_dic = json.loads(output_tokens)["kwargs"]["response_metadata"]["token_usage"]
                token_usage = TokenUsage(
                    input_tokens=token_usage_dic["prompt_tokens"], output_tokens=token_usage_dic["completion_tokens"]
                )
                messages = [x.get("extracted_content", x.get("error")) for x in state["result"]]
                step = TaskStep(
                    url=state["state"]["url"], duration_in_s=step_timing, token_usage=token_usage, messages=messages
                )
                steps.append(step)

            try:
                finished = any("done" in x for x in agent_task["output"]["history"][-1]["model_output"]["action"])
            except (KeyError, TypeError):
                finished = False

            task_result = TaskResult(
                task=tasks[task_id],
                evaluation=evaluation,
                evaluation_reason=reason,
                agent_answer=agent_output,
                duration_in_s=agent_task["timing"][args.run_function][0],
                steps=steps,
                finished=finished,
                task_id=task_id,
                agent_key=args.agent_key,
            )

            output_file.write(task_result.model_dump_json() + "\n")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
