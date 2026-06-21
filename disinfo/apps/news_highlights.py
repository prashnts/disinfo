from dataclasses import dataclass
from threading import Thread
from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from disinfo.data_structures import AppBaseModel
from disinfo.config import app_config


_oai_provider = OpenAIProvider(base_url=app_config.oai_base_url, api_key=app_config.oai_api_key.get_secret_value())
model = OpenAIChatModel('phi4-mini:latest', provider=_oai_provider)

@dataclass
class Deps:
    story: object
    n_max_words: int = 10
    n_avg_words: int = 5

class Output(AppBaseModel):
    highlight_1: str
    highlight_2: str
    highlight_3: str | None = None


agent = Agent(model, deps_type=Deps)

@agent.instructions
async def prompt(ctx) -> str:
    deps = ctx.deps
    return f"""
Extract three key highlights from the given news story given to you.

- Ensure to have < {deps.n_max_words} words per line, but we'd prefer <= {deps.n_avg_words} words.
- Do not invent new details or and do not use your training data to fill in the gaps.
- Do not repeat the details within the title as is.
- Use the same language as the story to generate the highlights.

[!] It's ok to return fewer lines if necessary.
[!] The idea is similar to writing telegrams, but in natural language.
"""

_running_threads = dict()

def extract_highlights(story) -> Output:
    deps = Deps(story=story)
    content = f"""
BEGINSTORY
{deps.story.title}

{deps.story.short_summary}
ENDSTORY
"""
    def runner():
        if not story.extracts:
            story.extracts = agent.run_sync(content, deps=deps).output
            story.save()

    if story.uid not in _running_threads:
        t = Thread(target=runner)
        t.start()
        _running_threads[story.uid] = t

