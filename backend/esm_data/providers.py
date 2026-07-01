"""
LLM Provider Protocols, Identifies which Provider is being used

Abstracts any one provider so the application can switch
between providers.
"""

import os
from collections.abc import Callable
from functools import partial
from typing import Final, Protocol, TypedDict, Unpack, runtime_checkable

from google import genai
from google.genai import types
import openai
from pydantic import BaseModel

__all__: Final[list[str]] = [
    "LLMProvider",
    "GeminiProvider",
    "OpenAIProvider",
    "ProviderArgs",
    "register_provider",
    "get_provider",
]


@runtime_checkable
class LLMProvider(Protocol):
    """
    Duck typing, any class that has the same methods
    is automatically an LLMProvider.
    Protocol is used to abstract LLM Provider
    """

    def generate_structured[T: BaseModel](
        self, prompt: str, system_instruction: str, response_schema: type[T]
    ) -> T: ...

    async def generate_structured_async[T: BaseModel](
        self, prompt: str, system_instruction: str, response_schema: type[T]
    ) -> T: ...


class GeminiProvider:
    """
    Gemini API implementation, an LLMProvider
    Connector for Google's Gemini models
    """

    __slots__ = ("client", "model_name")

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str = "gemini-3.1-pro-preview",
    ) -> None:
        key = api_key or os.environ.get("GEMINI_API_KEY")
        self.client = genai.Client(api_key=key)
        self.model_name = model_name

    def __repr__(self) -> str:
        """Debugger output"""
        return f"GeminiProvider(model_name={self.model_name!r})"

    def __str__(self) -> str:
        """Readable log output string"""
        return f"Gemini Provider Engine [Active Model: {self.model_name}]"

    def generate_structured[T: BaseModel](
        self, prompt: str, system_instruction: str, response_schema: type[T]
    ) -> T:
        """
        Requests Gemini LLM to respond according to strict
        response_schema
        """
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=response_schema,
                temperature=0.0,
            ),
        )
        return response.parsed

    async def generate_structured_async[T: BaseModel](
        self, prompt: str, system_instruction: str, response_schema: type[T]
    ) -> T:
        """
        Async function for LLM Judge,
        multiple evaluations simultaneously
        """
        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=response_schema,
                temperature=0.0,
            ),
        )
        return response.parsed


class OpenAIProvider:
    """
    OpenAI API
    Also connects to Nvidia NIM and other providers
    that have the same format as OpenAI by changing base_url
    """

    __slots__ = ("client", "async_client", "model_name")

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str = "gpt-4o",
        base_url: str | None = None,
        env_var_name: str = "OPENAI_API_KEY",
    ) -> None:
        key = api_key or os.environ.get(env_var_name)
        self.client = openai.OpenAI(api_key=key, base_url=base_url)
        self.async_client = openai.AsyncOpenAI(api_key=key, base_url=base_url)
        self.model_name = model_name

    def __repr__(self) -> str:
        """Debugger output"""
        return f"OpenAIProvider(model_name={self.model_name!r})"

    def __str__(self) -> str:
        """log output string"""
        return f"OpenAI-like provider engine [Active Model: {self.model_name}]"

    def generate_structured[T: BaseModel](
        self, prompt: str, system_instruction: str, response_schema: type[T]
    ) -> T:
        """
        Requests OpenAI to reply using strict response_schema
        """
        response = self.client.beta.chat.completions.parse(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            response_format=response_schema,
            temperature=0.0,
        )
        return response.choices[0].message.parsed

    async def generate_structured_async[T: BaseModel](
        self, prompt: str, system_instruction: str, response_schema: type[T]
    ) -> T:
        """
        Async function for LLM Judge,
        multiple evaluations simultaneously
        """
        response = await self.async_client.beta.chat.completions.parse(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            response_format=response_schema,
            temperature=0.0,
        )
        return response.choices[0].message.parsed


class ProviderArgs(TypedDict, total=False):
    api_key: str | None
    model_name: str
    base_url: str | None


_REGISTRY: Final[dict[str, Callable[..., LLMProvider]]] = {}


def register_provider(
    name: str, provider_factory: Callable[..., LLMProvider]
) -> None:
    """
    Adds a new AI provider factory to the system's list
    """
    _REGISTRY[name.lower()] = provider_factory


def get_provider(
    name: str | None = None, **kwargs: Unpack[ProviderArgs]
) -> LLMProvider:
    """
    Looks at .env file to see what provider you want to use then sets
    up the class. Default is "gemini"
    """
    provider_choice = name or os.environ.get("DEFAULT_PROVIDER", "gemini")
    provider_factory = _REGISTRY.get(provider_choice.lower())

    if not provider_factory:
        available_options = list(_REGISTRY.keys())
        raise ValueError(
            f"!!!: '{provider_choice}' is not registered!.\n"
            f"Available options are: {available_options}"
        )

    return provider_factory(**kwargs)


register_provider("gemini", GeminiProvider)
register_provider("openai", OpenAIProvider)
register_provider(
    "nemotron",
    partial(
        OpenAIProvider,
        base_url="https://integrate.api.nvidia.com/v1",
        model_name="nvidia/nemotron-3-ultra-550b-a55b",
        env_var_name="NVIDIA_API_KEY",
    ),
)