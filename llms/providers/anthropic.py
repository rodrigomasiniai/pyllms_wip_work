# llms/providers/anthropic.py

from typing import AsyncGenerator, Dict, Generator, List, Optional, Union

import anthropic

from ..results.result import AsyncStreamResult, Result, StreamResult
from .base_provider import BaseProvider


class AnthropicProvider(BaseProvider):
    MODEL_INFO = {
        "claude-instant-v1.1": {
            "prompt": 1.63,
            "completion": 5.51,
            "token_limit": 9000,
        },
        "claude-instant-v1": {"prompt": 1.63, "completion": 5.51, "token_limit": 9000},
        "claude-v1": {"prompt": 11.02, "completion": 32.68, "token_limit": 9000},
        "claude-v1-100k": {
            "prompt": 11.02,
            "completion": 32.68,
            "token_limit": 100_000,
        },
        "claude-instant-1": {
            "prompt": 1.63,
            "completion": 5.51,
            "token_limit": 100_000,
        },
         "claude-instant-1.2": {
            "prompt": 1.63,
            "completion": 5.51,
            "token_limit": 100_000,
        },
        "claude-2": {"prompt": 8.00, "completion": 24.00, "token_limit": 200_000},
    }

    def __init__(
        self,
        api_key: Union[str, None] = None,
        model: Union[str, None] = None,
        client_kwargs: Union[dict, None] = None,
        async_client_kwargs: Union[dict, None] = None,
    ):
        if model is None:
            model = list(self.MODEL_INFO.keys())[0]
        self.model = model

        if client_kwargs is None:
            client_kwargs = {}
        self.client = anthropic.Anthropic(api_key=api_key, **client_kwargs)
        if async_client_kwargs is None:
            async_client_kwargs = {}
        self.async_client = anthropic.AsyncAnthropic(api_key=api_key, **async_client_kwargs)

    def count_tokens(self, content: str) -> int:
        return self.client.count_tokens(content)

    def _prepare_model_inputs(
        self,
        prompt: str,
        history: Optional[List[dict]] = None,
        temperature: float = 0,
        max_tokens: int = 300,
        stop_sequences: Optional[List[str]] = None,
        ai_prompt: str = "",
        system_message: Union[str, None] = None,
        stream: bool = False,
        **kwargs,
    ) -> Dict:
        if system_message is None:
            system_prompts = ""
        else:
            if self.model != "claude-2":
                raise ValueError("System message only available for Claude-2 model")
            system_prompts = f"{system_message.rstrip()}\n\n"

        formatted_prompt = (
            f"{system_prompts}{anthropic.HUMAN_PROMPT}{prompt}{anthropic.AI_PROMPT}{ai_prompt}"
        )

        if history is not None:
            history_text_list = []
            for message in history:
                role = message["role"]
                content = message["content"]
                if role == "user":
                    role_prompt = anthropic.HUMAN_PROMPT
                elif role == "assistant":
                    role_prompt = anthropic.AI_PROMPT
                else:
                    raise ValueError(
                        f"Invalid role {role}, role must be user or assistant."
                    )

                formatted_message = f"{role_prompt}{content}"
                history_text_list.append(formatted_message)

            history_prompt = "".join(history_text_list)
            formatted_prompt = f"{history_prompt}{formatted_prompt}"

        max_tokens_to_sample = kwargs.pop("max_tokens_to_sample", max_tokens)

        if stop_sequences is None:
            stop_sequences = [anthropic.HUMAN_PROMPT]
        model_inputs = {
            "prompt": formatted_prompt,
            "temperature": temperature,
            "max_tokens_to_sample": max_tokens_to_sample,
            "stop_sequences": stop_sequences,
            "stream": stream,
            **kwargs,
        }
        return model_inputs

    def complete(
        self,
        prompt: str,
        history: Optional[List[dict]] = None,
        temperature: float = 0,
        max_tokens: int = 300,
        stop_sequences: Optional[List[str]] = None,
        ai_prompt: str = "",
        system_message: Union[str, None] = None,
        **kwargs,
    ) -> Result:
        """
        Args:
            history: messages in OpenAI format,
              each dict must include role and content key.
            ai_prompt: prefix of AI response, for finer control on the output.
        """

        model_inputs = self._prepare_model_inputs(
            prompt=prompt,
            history=history,
            temperature=temperature,
            max_tokens=max_tokens,
            stop_sequences=stop_sequences,
            ai_prompt=ai_prompt,
            system_message=system_message,
            **kwargs,
        )

        with self.track_latency():
            response = self.client.completions.create(model=self.model, **model_inputs)

        completion = response.completion.strip()

        return Result(
            text=completion,
            model_inputs=model_inputs,
            provider=self,
            meta={"latency": self.latency},
        )

    async def acomplete(
        self,
        prompt: str,
        history: Optional[List[dict]] = None,
        temperature: float = 0,
        max_tokens: int = 300,
        stop_sequences: Optional[List[str]] = None,
        ai_prompt: str = "",
        system_message: Union[str, None] = None,
        **kwargs,
    ):
        """
        Args:
            history: messages in OpenAI format,
              each dict must include role and content key.
            ai_prompt: prefix of AI response, for finer control on the output.
        """
        model_inputs = self._prepare_model_inputs(
            prompt=prompt,
            history=history,
            temperature=temperature,
            max_tokens=max_tokens,
            stop_sequences=stop_sequences,
            ai_prompt=ai_prompt,
            system_message=system_message,
            **kwargs,
        )
        with self.track_latency():
            response = await self.async_client.completions.create(
                model=self.model, **model_inputs
            )
        completion = response.completion.strip()

        return Result(
            text=completion,
            model_inputs=model_inputs,
            provider=self,
            meta={"latency": self.latency},
        )

    def complete_stream(
        self,
        prompt: str,
        history: Optional[List[dict]] = None,
        temperature: float = 0,
        max_tokens: int = 300,
        stop_sequences: Optional[List[str]] = None,
        ai_prompt: str = "",
        system_message: Union[str, None] = None,
        **kwargs,
    ) -> StreamResult:
        """
        Args:
            history: messages in OpenAI format,
              each dict must include role and content key.
            ai_prompt: prefix of AI response, for finer control on the output.
        """
        model_inputs = self._prepare_model_inputs(
            prompt=prompt,
            history=history,
            temperature=temperature,
            max_tokens=max_tokens,
            stop_sequences=stop_sequences,
            ai_prompt=ai_prompt,
            system_message=system_message,
            stream=True,
            **kwargs,
        )
        response = self.client.completions.create(model=self.model, **model_inputs)
        stream = self._process_stream(response)

        return StreamResult(stream=stream, model_inputs=model_inputs, provider=self)

    def _process_stream(self, response: Generator) -> Generator:
        first_completion = next(response).completion
        yield first_completion.lstrip()

        for data in response:
            yield data.completion

    async def acomplete_stream(
        self,
        prompt: str,
        history: Optional[List[dict]] = None,
        temperature: float = 0,
        max_tokens: int = 300,
        stop_sequences: Optional[List[str]] = None,
        ai_prompt: str = "",
        system_message: Union[str, None] = None,
        **kwargs,
    ) -> AsyncStreamResult:
        """
        Args:
            history: messages in OpenAI format,
              each dict must include role and content key.
            ai_prompt: prefix of AI response, for finer control on the output.
        """
        model_inputs = self._prepare_model_inputs(
            prompt=prompt,
            history=history,
            temperature=temperature,
            max_tokens=max_tokens,
            stop_sequences=stop_sequences,
            ai_prompt=ai_prompt,
            system_message=system_message,
            stream=True,
            **kwargs,
        )

        response = await self.async_client.completions.create(
            model=self.model, **model_inputs
        )

        stream = self._aprocess_stream(response)

        return AsyncStreamResult(
            stream=stream, model_inputs=model_inputs, provider=self
        )

    async def _aprocess_stream(self, response: AsyncGenerator) -> AsyncGenerator:
        first_completion = (await response.__anext__()).completion
        yield first_completion.lstrip()

        async for data in response:
            yield data.completion
