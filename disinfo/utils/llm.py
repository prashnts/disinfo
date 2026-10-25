from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from disinfo.config import app_config

# The local llm, behind open-webui.
_oai_provider = OpenAIProvider(base_url=app_config.oai_base_url, api_key=app_config.oai_api_key.get_secret_value())
model = OpenAIChatModel('openai/gpt-oss-20b', provider=_oai_provider)
