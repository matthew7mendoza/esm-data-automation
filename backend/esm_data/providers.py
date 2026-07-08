"""LLM Provider Protocols identifying active operational execution engines."""
import os
from collections.abc import Callable
from typing import Final, Protocol, TypedDict, Unpack, cast, runtime_checkable

import openai
from google import genai
from google.genai import types
from pydantic import BaseModel

from backend.esm_data.config import settings_engine

__all__: Final[list[str]] = [
    "GeminiProvider",
    "LLMProvider",
    "OpenAIProvider",
    "ProviderArgs",
    "get_provider",
    "register_provider",
]

@runtime_checkable
class LLMProvider(Protocol):
    """Duck typing structural interface for concrete LLM client abstractions."""

    def generate_structured[T: BaseModel](
        self, *, prompt: str, system_instruction: str, response_schema: type[T]
    ) -> T: ...

    async def generate_structured_async[T: BaseModel](
        self, *, prompt: str, system_instruction: str, response_schema: type[T]
    ) -> T: ...

class GeminiProvider:
    """Connector engine optimized for Google's Gemini API architectures."""

    __slots__ = ("client", "model_name")

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str = "gemini-3.1-pro-preview",
    ) -> None:
        key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise ValueError("Execution failed: Missing GEMINI_API_KEY value.")

        self.client = genai.Client(api_key=key)
        self.model_name = model_name

    def __repr__(self) -> str:
        return f"GeminiProvider(model_name={self.model_name!r})"

    def __str__(self) -> str:
        return f"Gemini Provider Engine [Active Model: {self.model_name}]"

    def generate_structured[T: BaseModel](
        self, *, prompt: str, system_instruction: str, response_schema: type[T]
    ) -> T:
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
        if (parsed := response.parsed) is None:
            raise ValueError("Failed to parse structured response from Gemini.")
        return cast(T, parsed)

    async def generate_structured_async[T: BaseModel](
        self, *, prompt: str, system_instruction: str, response_schema: type[T]
    ) -> T:
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
        if (parsed := response.parsed) is None:
            raise ValueError("Failed to parse structured response from Gemini.")
        return cast(T, parsed)

class OpenAIProvider:
    """Standardized wrapper for processing calls to OpenAI endpoint topologies."""

    __slots__ = ("async_client", "client", "model_name")

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str = "gpt-4o",
        base_url: str | None = None,
    ) -> None:
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise ValueError("Execution failed: Missing standard API key mapping.")

        self.client = openai.OpenAI(api_key=key, base_url=base_url)
        self.async_client = openai.AsyncOpenAI(api_key=key, base_url=base_url)
        self.model_name = model_name

    def __repr__(self) -> str:
        return f"OpenAIProvider(model_name={self.model_name!r})"

    def __str__(self) -> str:
        return f"OpenAI Provider Engine [Active Model: {self.model_name}]"

    def generate_structured[T: BaseModel](
        self, *, prompt: str, system_instruction: str, response_schema: type[T]
    ) -> T:
        response = self.client.beta.chat.completions.parse(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            response_format=response_schema,
            temperature=0.0,
        )
        if (parsed := response.choices[0].message.parsed) is None:
            raise ValueError("Failed to parse structured response from OpenAI.")
        return parsed

    async def generate_structured_async[T: BaseModel](
        self, *, prompt: str, system_instruction: str, response_schema: type[T]
    ) -> T:
        response = await self.async_client.beta.chat.completions.parse(
            model=self.model_name,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt},
            ],
            response_format=response_schema,
            temperature=0.0,
        )
        if (parsed := response.choices[0].message.parsed) is None:
            raise ValueError("Failed to parse structured response from OpenAI.")
        return parsed

class ProviderArgs(TypedDict, total=False):
    api_key: str | None
    model_name: str
    base_url: str | None

_REGISTRY: Final[dict[str, Callable[..., LLMProvider]]] = {}

def register_provider(
    name: str, provider_factory: Callable[..., LLMProvider]) -> None:
    _REGISTRY[name.lower()] = provider_factory


BUILTIN_PROVIDERS = {
    "gemini": "gemini",
    "openai": "openai",
    "nvidia": "nemotron",
    "nemotron": "nemotron",
}

def get_provider(  # noqa: C901
    name: str | None = None, **kwargs: Unpack[ProviderArgs]
) -> LLMProvider:
    """Resolves the correct provider instance matching active configurations."""
    raw_choice = name or os.environ.get("DEFAULT_PROVIDER", "gemini")
    clean_name = raw_choice.lower()

    active_config = settings_engine.get_current()
    matched_key = next(
        (key for key in active_config.custom_key_providers if key.lower() == clean_name),  # noqa: E501
        None,
    )

    custom_provider_type = ""
    if matched_key is not None:
        custom_provider_type = active_config.custom_key_providers[matched_key].lower()

    is_unregistered_custom = matched_key is not None and custom_provider_type not in _REGISTRY  # noqa: E501
    if is_unregistered_custom:
        raise ValueError(
            f"Custom provider type '{custom_provider_type}' for key '{matched_key}' is not registered."  # noqa: E501
        )

    if matched_key is not None:
        custom_api_key = active_config.custom_api_keys.get(matched_key)
        factory_kwargs = {"api_key": custom_api_key, **kwargs} if custom_api_key else {**kwargs}  # noqa: E501
        return _REGISTRY[custom_provider_type](**factory_kwargs)

    matched_trigger = next(
        (trigger for trigger in BUILTIN_PROVIDERS if trigger in clean_name),
        None,
    )

    is_builtin_matched = matched_trigger is not None
    provider_id = BUILTIN_PROVIDERS[cast(str, matched_trigger)] if is_builtin_matched else ""  # noqa: E501

    is_unregistered_builtin = is_builtin_matched and provider_id not in _REGISTRY
    if is_unregistered_builtin:
        raise ValueError(f"Built-in provider '{provider_id}' is not registered.")

    if is_builtin_matched:
        return _REGISTRY[provider_id](**kwargs)

    if clean_name not in _REGISTRY:
        raise ValueError(f"Unknown LLM provider: {clean_name}")

    return _REGISTRY[clean_name](**kwargs)

def _nemotron_factory(**kwargs: Unpack[ProviderArgs]) -> LLMProvider:
    api_key = kwargs.get("api_key") or os.environ.get("NVIDIA_API_KEY", "")
    if not api_key:
        raise ValueError("Execution failed: Missing NVIDIA_API_KEY value.")
    return OpenAIProvider(
        api_key=api_key,
        model_name=kwargs.get("model_name", "nvidia/nemotron-4-340b-instruct"),
        base_url=kwargs.get("base_url", "https://integrate.api.nvidia.com/v1"),
    )

register_provider("gemini", GeminiProvider)
register_provider("openai", OpenAIProvider)
register_provider("nemotron", _nemotron_factory)
