import tiktoken
from typing import Dict, Union, Optional, List, Generator, AsyncGenerator
from mistralai.client import MistralClient
from mistralai.async_client import MistralAsyncClient
from mistralai.models.chat_completion import ChatMessage



from ..results.result import AsyncStreamResult, Result, StreamResult
from .base_provider import BaseProvider


class MistralProvider(BaseProvider):
    MODEL_INFO = {
        "mistral-tiny": {"prompt": 0.14, "completion": 0.42, "token_limit": 32_000},
        "mistral-small": {"prompt": 0.6, "completion": 1.8, "token_limit": 32_000},
        "mistral-medium": {"prompt": 2.5, "completion": 7.5, "token_limit": 32_000},
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
        self.client = MistralClient(api_key=api_key, **client_kwargs)

        if async_client_kwargs is None:
            async_client_kwargs = {}
        self.async_client = MistralAsyncClient(api_key=api_key, **async_client_kwargs)

    def count_tokens(self, content: Union[str, List[dict]]) -> int:
        # TODO: update after Mistarl support count token in their SDK
        # use gpt 3.5 turbo for estimation now
        enc = tiktoken.encoding_for_model(self.model)
        if isinstance(content, list):
            # When field name is present, ChatGPT will ignore the role token.
            # Adopted from OpenAI cookbook
            # https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
            # every message follows <im_start>{role/name}\n{content}<im_end>\n
            formatting_token_count = 4

            messages = content
            messages_text = ["".join(message.values()) for message in messages]
            tokens = [enc.encode(t, disallowed_special=()) for t in messages_text]

            n_tokens_list = []
            for token, message in zip(tokens, messages):
                n_tokens = len(token) + formatting_token_count
                if "name" in message:
                    n_tokens += -1
                n_tokens_list.append(n_tokens)
            return sum(n_tokens_list)
        else:
            return len(enc.encode(content, disallowed_special=()))

    def _prepare_model_inputs(
        self,
        prompt: str,
        history: Optional[List[dict]] = None,
        temperature: float = 0,
        max_tokens: int = 300,
        stop_sequences: Optional[List[str]] = None,
        system_message: Union[str, None] = None,
        safe_prompt: bool = False,
        random_seed: Union[int, None] = None,
        **kwargs,
    ) -> Dict:
        if stop_sequences:
            raise ValueError("Parameter `stop` is not supported")

        messages = [ChatMessage(role="user", content=prompt)]
        if history:
            messages = [ChatMessage(**utterance) for utterance in history] + messages

        if system_message is None:
            pass
        elif isinstance(system_message, str):
            messages = [ChatMessage(role="system", content=system_message), *messages]

        model_inputs = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "safe_prompt": safe_prompt,
            "random_seed": random_seed,
            **kwargs,
        }

        return model_inputs

    def complete(
        self,
        prompt: str,
        history: Optional[List[dict]] = None,
        system_message: Optional[List[dict]] = None,
        temperature: float = 0,
        max_tokens: int = 300,
        safe_prompt: bool = False,
        random_seed: Union[int, None] = None,
        **kwargs,
    ) -> Result:
        model_inputs = self._prepare_model_inputs(
            prompt=prompt,
            history=history,
            system_message=system_message,
            temperature=temperature,
            max_tokens=max_tokens,
            safe_prompt=safe_prompt,
            random_seed=random_seed,
            **kwargs,
        )

        with self.track_latency():
            response = self.client.chat(model=self.model, **model_inputs)

        completion = response.choices[0].message.content
        usage = response.usage

        meta = {
            "tokens_prompt": usage.prompt_tokens,
            "tokens_completion": usage.completion_tokens,
            "latency": self.latency,
        }

        return Result(
            text=completion,
            model_inputs=model_inputs,
            provider=self,
            meta=meta,
        )

    async def acomplete(
        self,
        prompt: str,
        history: Optional[List[dict]] = None,
        system_message: Optional[List[dict]] = None,
        temperature: float = 0,
        max_tokens: int = 300,
        safe_prompt: bool = False,
        random_seed: Union[int, None] = None,
        **kwargs,
    ) -> Result:

        model_inputs = self._prepare_model_inputs(
            prompt=prompt,
            history=history,
            system_message=system_message,
            temperature=temperature,
            max_tokens=max_tokens,
            safe_prompt=safe_prompt,
            random_seed=random_seed,
            **kwargs,
        )
        with self.track_latency():
            response = await self.async_client.chat(model=self.model, **model_inputs)

        completion = response.choices[0].message.content
        usage = response.usage

        meta = {
            "tokens_prompt": usage.prompt_tokens,
            "tokens_completion": usage.completion_tokens,
            "latency": self.latency,
        }

        return Result(
            text=completion,
            model_inputs=model_inputs,
            provider=self,
            meta=meta,
        )

    def complete_stream(
        self,
        prompt: str,
        history: Optional[List[dict]] = None,
        system_message: Optional[List[dict]] = None,
        temperature: float = 0,
        max_tokens: int = 300,
        safe_prompt: bool = False,
        random_seed: Union[int, None] = None,
        **kwargs,
    ) -> StreamResult:

        model_inputs = self._prepare_model_inputs(
            prompt=prompt,
            history=history,
            system_message=system_message,
            temperature=temperature,
            max_tokens=max_tokens,
            safe_prompt=safe_prompt,
            random_seed=random_seed,
            **kwargs,
        )

        response = self.client.chat_stream(model=self.model, **model_inputs)
        stream = self._process_stream(response)
        return StreamResult(stream=stream, model_inputs=model_inputs, provider=self)

    def _process_stream(self, response: Generator) -> Generator:
        chunk_generator = (
            chunk.choices[0].delta.content for chunk in response
        )

        while not (first_text := next(chunk_generator)):
            continue
        yield first_text.lstrip()
        for chunk in chunk_generator:
            if chunk is not None:
                yield chunk

    async def acomplete_stream(
        self,
        prompt: str,
        history: Optional[List[dict]] = None,
        system_message: Optional[List[dict]] = None,
        temperature: float = 0,
        max_tokens: int = 300,
        safe_prompt: bool = False,
        random_seed: Union[int, None] = None,
        **kwargs,
    ) -> AsyncStreamResult:

        model_inputs = self._prepare_model_inputs(
            prompt=prompt,
            history=history,
            system_message=system_message,
            temperature=temperature,
            max_tokens=max_tokens,
            safe_prompt=safe_prompt,
            random_seed=random_seed,
            **kwargs,
        )

        with self.track_latency():
            response = self.async_client.chat_stream(model=self.model, **model_inputs)
        stream = self._aprocess_stream(response)
        return AsyncStreamResult(
            stream=stream, model_inputs=model_inputs, provider=self
        )

    async def _aprocess_stream(self, response) -> AsyncGenerator:
        while True:
            first_completion = (await response.__anext__()).choices[0].delta.content
            if first_completion:
                yield first_completion.lstrip()
                break

        async for chunk in response:
            completion = chunk.choices[0].delta.content
            if completion is not None:
                yield completion
