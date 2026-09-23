"""Version 1: the bare LLM answers alone, with no internet. The baseline that shows search matters."""
from . import prompts
from .llm import LLM
from .schemas import Report


async def run_v1(question: str, llm: LLM) -> Report:
    llm.trace.event("step", name="answer")
    answer = await llm.chat(prompts.v1_messages(question), purpose="v1_answer")
    return Report(question=question, mode="v1", answer=answer, models={"main": llm.settings.main_model})
