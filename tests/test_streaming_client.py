from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from source.runtime.env_config import ModelConfig
from source.runtime.openai_chat_client import ChatCompletionClient, first_message


def model_config(*, stream: bool = True, timeout_seconds: int = 600) -> ModelConfig:
    return ModelConfig(
        chat_completions_url="https://model.example/v1/chat/completions",
        api_key="test-key",
        model="test-model",
        timeout_seconds=timeout_seconds,
        temperature=0.2,
        max_tokens=0,
        stream=stream,
        package_id="",
    )


class StreamingParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = ChatCompletionClient(model_config())

    def test_fragmented_content_reasoning_tool_calls_and_usage_are_merged(self) -> None:
        chunks = [
            {
                "id": "chat-1",
                "model": "competition-model",
                "created": 123,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "reasoning_content": "先",
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "date_",
                                        "arguments": '{"expression":"2026',
                                    },
                                }
                            ],
                        },
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": "chat-1",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "reasoning_content": "计算",
                            "content": "调用工具",
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {
                                        "name": "compute",
                                        "arguments": '-05-06"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
            },
            {
                "id": "chat-1",
                "choices": [],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "total_tokens": 14,
                },
            },
        ]
        data = "\n\n".join(
            f"data: {json.dumps(chunk, ensure_ascii=False)}" for chunk in chunks
        ) + "\n\ndata: [DONE]\n\n"

        completion = self.client._parse_response(data)
        message = first_message(completion)

        self.assertEqual(message["content"], "调用工具")
        self.assertEqual(message["reasoning_content"], "先计算")
        self.assertEqual(
            message["tool_calls"][0]["function"],
            {
                "name": "date_compute",
                "arguments": '{"expression":"2026-05-06"}',
            },
        )
        self.assertEqual(completion["choices"][0]["finish_reason"], "tool_calls")
        self.assertEqual(completion["usage"]["total_tokens"], 14)

    def test_stream_error_payload_is_raised(self) -> None:
        data = 'data: {"error":{"message":"gateway overloaded","code":"busy"}}\n\n'

        with self.assertRaisesRegex(RuntimeError, "gateway overloaded"):
            self.client._parse_response(data)

    def test_stream_without_a_choice_is_rejected(self) -> None:
        data = (
            'data: {"id":"chat-empty","choices":[],"usage":{"total_tokens":0}}\n\n'
            "data: [DONE]\n\n"
        )

        with self.assertRaisesRegex(RuntimeError, "no usable choices"):
            self.client._parse_response(data)


class StreamingRequestTests(unittest.TestCase):
    def test_request_sends_stream_true_and_uses_600_second_timeout(self) -> None:
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return (
                    b'data: {"choices":[{"delta":{"content":"ok"},'
                    b'"finish_reason":"stop"}]}\n\n'
                    b"data: [DONE]\n\n"
                )

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["headers"] = dict(request.headers)
            captured["timeout"] = timeout
            return FakeResponse()

        client = ChatCompletionClient(model_config())
        with patch(
            "source.runtime.openai_chat_client.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            completion = client._create_sync(
                messages=[{"role": "user", "content": "hello"}],
                tools=[],
                tool_choice="none",
                response_format=None,
            )

        self.assertTrue(captured["payload"]["stream"])
        self.assertEqual(captured["timeout"], 600)
        self.assertEqual(captured["headers"]["Accept"], "text/event-stream")
        self.assertEqual(first_message(completion)["content"], "ok")


if __name__ == "__main__":
    unittest.main()
