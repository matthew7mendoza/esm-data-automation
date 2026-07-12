"""LLM Provider Protocols identifying active operational execution engines."""

import os
from collections.abc import Callable
from typing import Any, Final, Protocol, TypedDict, Unpack, cast, runtime_checkable

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

    def generate_structured[ResponseModelType: BaseModel](
        self,
        *,
        prompt: str,
        system_instruction: str,
        response_schema: type[ResponseModelType],
    ) -> ResponseModelType: ...

    async def generate_structured_async[ResponseModelType: BaseModel](
        self,
        *,
        prompt: str,
        system_instruction: str,
        response_schema: type[ResponseModelType],
    ) -> ResponseModelType: ...


class GeminiProvider:
    """Connector engine optimized for Google's Gemini API architectures."""

    __slots__ = ("client", "model_name")

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str = "gemini-3.1-pro-preview",
    ) -> None:
        api_key_value = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not api_key_value:
            raise ValueError(
                "Execution failed: Missing GEMINI_API_KEY value in environment."
            )

        self.client = genai.Client(api_key=api_key_value)
        self.model_name = model_name

    def __repr__(self) -> str:
        return f"GeminiProvider(model_name={self.model_name!r})"

    def __str__(self) -> str:
        return f"Gemini Provider Engine [Active Model: {self.model_name}]"

    def _build_generation_configuration[ResponseModelType: BaseModel](
        self, system_instruction_text: str, schema_type: type[ResponseModelType]
    ) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=system_instruction_text,
            response_mime_type="application/json",
            response_schema=schema_type,
            temperature=0.0,
        )

    def generate_structured[ResponseModelType: BaseModel](
        self,
        *,
        prompt: str,
        system_instruction: str,
        response_schema: type[ResponseModelType],
    ) -> ResponseModelType:
        generation_configuration = self._build_generation_configuration(
            system_instruction_text=system_instruction, schema_type=response_schema
        )
        content_response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=generation_configuration,
        )
        parsed_response_data = content_response.parsed
        if parsed_response_data is None:
            raise ValueError(
                "Failed to parse structured JSON response from Gemini engine."
            )
        return cast(ResponseModelType, parsed_response_data)

    async def generate_structured_async[ResponseModelType: BaseModel](
        self,
        *,
        prompt: str,
        system_instruction: str,
        response_schema: type[ResponseModelType],
    ) -> ResponseModelType:
        generation_configuration = self._build_generation_configuration(
            system_instruction_text=system_instruction, schema_type=response_schema
        )
        content_response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=generation_configuration,
        )
        parsed_response_data = content_response.parsed
        if parsed_response_data is None:
            raise ValueError(
                "Failed to parse structured JSON response from Gemini engine."
            )
        return cast(ResponseModelType, parsed_response_data)


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
        api_key_value = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not api_key_value:
            raise ValueError(
                "Execution failed: Missing OPENAI_API_KEY value in environment."
            )

        self.client = openai.OpenAI(api_key=api_key_value, base_url=base_url)
        self.async_client = openai.AsyncOpenAI(api_key=api_key_value, base_url=base_url)
        self.model_name = model_name

    def __repr__(self) -> str:
        return f"OpenAIProvider(model_name={self.model_name!r})"

    def __str__(self) -> str:
        return f"OpenAI Provider Engine [Active Model: {self.model_name}]"

    def _build_message_payload(
        self, system_instruction_text: str, user_prompt_text: str
    ) -> list[Any]:
        return [
            {"role": "system", "content": system_instruction_text},
            {"role": "user", "content": user_prompt_text},
        ]

    def _extract_parsed_response[ResponseModelType: BaseModel](
        self, response_object: Any, _response_schema_type: type[ResponseModelType]
    ) -> ResponseModelType:
        parsed_response_data = response_object.choices[0].message.parsed
        if parsed_response_data is None:
            raise ValueError(
                "Failed to parse structured JSON response from OpenAI engine."
            )
        return cast(ResponseModelType, parsed_response_data)

    def generate_structured[ResponseModelType: BaseModel](
        self,
        *,
        prompt: str,
        system_instruction: str,
        response_schema: type[ResponseModelType],
    ) -> ResponseModelType:
        messages_payload = self._build_message_payload(
            system_instruction_text=system_instruction, user_prompt_text=prompt
        )
        chat_completion_response = self.client.beta.chat.completions.parse(
            model=self.model_name,
            messages=messages_payload,
            response_format=response_schema,
            temperature=0.0,
        )
        return self._extract_parsed_response(chat_completion_response, response_schema)

    async def generate_structured_async[ResponseModelType: BaseModel](
        self,
        *,
        prompt: str,
        system_instruction: str,
        response_schema: type[ResponseModelType],
    ) -> ResponseModelType:
        messages_payload = self._build_message_payload(
            system_instruction_text=system_instruction, user_prompt_text=prompt
        )
        chat_completion_response = await self.async_client.beta.chat.completions.parse(
            model=self.model_name,
            messages=messages_payload,
            response_format=response_schema,
            temperature=0.0,
        )
        return self._extract_parsed_response(chat_completion_response, response_schema)


class ProviderArgs(TypedDict, total=False):
    api_key: str | None
    model_name: str
    base_url: str | None


_REGISTRY: Final[dict[str, Callable[..., LLMProvider]]] = {}


def register_provider(name: str, provider_factory: Callable[..., LLMProvider]) -> None:
    _REGISTRY[name.lower()] = provider_factory


BUILTIN_PROVIDERS = {
    "gemini": "gemini",
    "openai": "openai",
    "nvidia": "nemotron",
    "nemotron": "nemotron",
}


def get_provider(
    name: str | None = None, **kwargs: Unpack[ProviderArgs]
) -> LLMProvider:
    """Resolves the correct provider instance matching active configurations."""
    raw_provider_choice_string = name or os.environ.get("DEFAULT_PROVIDER", "gemini")
    clean_provider_name = raw_provider_choice_string.lower()

    active_system_configuration = settings_engine.get_current()
    matched_custom_key = next(
        (
            provider_key
            for provider_key in active_system_configuration.custom_key_providers
            if provider_key.lower() == clean_provider_name
        ),
        None,
    )

    if matched_custom_key is not None:
        return _instantiate_custom_provider(
            matched_custom_key=matched_custom_key,
            active_configuration=active_system_configuration,
            **kwargs,
        )

    return _instantiate_builtin_provider(
        clean_provider_name=clean_provider_name, **kwargs
    )


def _instantiate_custom_provider(
    matched_custom_key: str, active_configuration: Any, **kwargs: Unpack[ProviderArgs]
) -> LLMProvider:
    custom_providers = active_configuration.custom_key_providers
    custom_provider_type = custom_providers[matched_custom_key].lower()
    if custom_provider_type not in _REGISTRY:
        raise ValueError(
            f"Custom provider type '{custom_provider_type}' for key "
            f"'{matched_custom_key}' is not registered."
        )

    custom_api_key_value = active_configuration.custom_api_keys.get(matched_custom_key)
    factory_keyword_arguments = (
        {"api_key": custom_api_key_value, **kwargs}
        if custom_api_key_value
        else {**kwargs}
    )
    return _REGISTRY[custom_provider_type](**factory_keyword_arguments)


def _instantiate_builtin_provider(
    clean_provider_name: str, **kwargs: Unpack[ProviderArgs]
) -> LLMProvider:
    matched_builtin_trigger = next(
        (trigger for trigger in BUILTIN_PROVIDERS if trigger in clean_provider_name),
        None,
    )

    if matched_builtin_trigger is not None:
        provider_identifier = BUILTIN_PROVIDERS[matched_builtin_trigger]
        if provider_identifier not in _REGISTRY:
            raise ValueError(
                f"Built-in provider '{provider_identifier}' is not registered."
            )
        return _REGISTRY[provider_identifier](**kwargs)

    if clean_provider_name not in _REGISTRY:
        raise ValueError(f"Unknown LLM provider: {clean_provider_name}")

    return _REGISTRY[clean_provider_name](**kwargs)


def _nemotron_factory(**kwargs: Unpack[ProviderArgs]) -> LLMProvider:
    api_key_value = kwargs.get("api_key") or os.environ.get("NVIDIA_API_KEY", "")
    if not api_key_value:
        raise ValueError(
            "Execution failed: Missing NVIDIA_API_KEY value in environment."
        )
    return OpenAIProvider(
        api_key=api_key_value,
        model_name=kwargs.get("model_name", "nvidia/nemotron-4-340b-instruct"),
        base_url=kwargs.get("base_url", "https://integrate.api.nvidia.com/v1"),
    )
