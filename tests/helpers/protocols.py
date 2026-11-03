"""The requests the integrated tools send Eden AI, made with the official SDKs.

Each function sends what a tool sends rather than the simplest call that would
succeed: streamed, because every chat tool streams, with tool definitions when
the tool is an agent, and authenticated the way the tool authenticates. Claude
Code sends its key as x-api-key, not as a bearer token, and that is a
different code path on the server.

`round_trip` is the paid mode. A real model is given a task that needs the
tool, is handed the tool's result, and has to answer with it, which is the
loop an agent runs on every turn. The call is asked for, not forced: no agent
sets tool_choice, and the newest Claude models refuse a forced one. The result
carries a random word the model cannot know any other way, so an answer
containing it proves the tool call came back in a shape the protocol allows
and the result went in the same way. The sandbox answers every request with
one canned completion, so on the sandbox only the first request is sent, and
what is checked is that it is served at all.

The task is deliberately dull. A request to read a file and repeat it word for
word reads like exfiltration to a provider's safety classifier, and Claude
Opus refuses it outright, which would fail a page for a reason that has
nothing to do with Eden AI.

A function returns nothing and raises on anything wrong: the SDK's own
APIStatusError for a refusal, AssertionError for a response that arrived but
cannot be what the tool expects.
"""

import json
import secrets

import anthropic
import openai

from tests.helpers.file_generators import silent_wav

__all__ = ["PING", "secret", "send"]

_TIMEOUT = 120

_SYSTEM = "You are a helpful assistant."
PING = "Reply with the single word: pong"
_TASK = (
    "What is the weather in Paris right now? Use the get_weather tool, then "
    "quote its report word for word."
)

# A cap on the answer, which every tool sets one way or another. Without it the
# API reserves the model's whole output ceiling, often 128k tokens, against the
# key's spending limit before it sends anything, and a key with a limit is
# refused for a request that would have cost a fraction of a cent.
_MAX_TOKENS = 4096

# One tool, in the shape each protocol declares it.
_TOOL_NAME = "get_weather"
_TOOL_DESCRIPTION = "Get the current weather report for a city."
_TOOL_SCHEMA = {
    "type": "object",
    "properties": {"city": {"type": "string", "description": "City name"}},
    "required": ["city"],
}
_CHAT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": _TOOL_NAME,
            "description": _TOOL_DESCRIPTION,
            "parameters": _TOOL_SCHEMA,
        },
    }
]
_MESSAGES_TOOLS = [
    {"name": _TOOL_NAME, "description": _TOOL_DESCRIPTION, "input_schema": _TOOL_SCHEMA}
]
_RESPONSES_TOOLS = [
    {
        "type": "function",
        "name": _TOOL_NAME,
        "description": _TOOL_DESCRIPTION,
        "parameters": _TOOL_SCHEMA,
    }
]


def secret() -> str:
    """A word no model can produce unless the tool result reached it."""
    return f"heron-{secrets.token_hex(3)}"


def _report(word: str) -> str:
    """What the tool returns, with the secret where the model has to quote it."""
    return f"Light rain, 14 degrees, reported by weather station {word}."


def _assert_called(calls: list, response) -> None:
    assert calls, f"the model did not call {_TOOL_NAME}: {response}"


def _assert_quotes(word: str, text: str | None) -> None:
    assert word in (text or ""), (
        f"the answer does not contain the tool result {word!r}: {text!r}"
    )


def _openai(base_url: str, token: str) -> openai.OpenAI:
    return openai.OpenAI(
        api_key=token, base_url=base_url, timeout=_TIMEOUT, max_retries=2
    )


# --- chat completions ------------------------------------------------------


def _chat_turn(client, model, messages, tools):
    with client.chat.completions.stream(
        model=model,
        messages=messages,
        max_completion_tokens=_MAX_TOKENS,
        stream_options={"include_usage": True},
        **({"tools": _CHAT_TOOLS} if tools else {}),
    ) as stream:
        for _ in stream:
            pass
        completion = stream.get_final_completion()
    assert completion.choices, "the stream ended without a choice"
    choice = completion.choices[0]
    assert choice.finish_reason, "the stream ended without a finish_reason"
    return choice.message


def chat(base_url, token, model, *, tools, round_trip):
    client = _openai(base_url, token)
    prompt = _TASK if tools and round_trip else PING
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": prompt},
    ]
    message = _chat_turn(client, model, messages, tools)
    if not (tools and round_trip):
        assert message.content, "the reply has no text"
        return

    _assert_called(message.tool_calls, message)
    word = secret()
    messages.append(message.model_dump(exclude_none=True))
    # A model can call the tool twice in one turn, and the next request is
    # refused unless every call has its result.
    for call in message.tool_calls:
        json.loads(call.function.arguments)
        messages.append(
            {"role": "tool", "tool_call_id": call.id, "content": _report(word)}
        )
    _assert_quotes(word, _chat_turn(client, model, messages, tools).content)


# --- Anthropic Messages ----------------------------------------------------


def _messages_turn(client, model, history, tools):
    with client.messages.stream(
        model=model,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM,
        messages=history,
        **({"tools": _MESSAGES_TOOLS} if tools else {}),
    ) as stream:
        message = stream.get_final_message()
    assert message.stop_reason, "the stream ended without a stop_reason"
    return message


def _text_of(message) -> str:
    return "".join(block.text for block in message.content if block.type == "text")


def messages(base_url, token, model, *, tools, round_trip):
    # api_key, not auth_token: ANTHROPIC_API_KEY is sent as x-api-key, which
    # is what the Claude Code page has the reader export.
    client = anthropic.Anthropic(
        api_key=token, base_url=base_url, timeout=_TIMEOUT, max_retries=2
    )
    prompt = _TASK if tools and round_trip else PING
    history = [{"role": "user", "content": prompt}]
    message = _messages_turn(client, model, history, tools)
    if not (tools and round_trip):
        assert _text_of(message), f"the reply has no text: {message.content}"
        return

    calls = [block for block in message.content if block.type == "tool_use"]
    # The stop_reason is what says a refusal is a refusal.
    _assert_called(calls, f"stop_reason {message.stop_reason}, {message.content}")
    word = secret()
    history += [
        {"role": "assistant", "content": message.content},
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": _report(word),
                }
                for call in calls
            ],
        },
    ]
    _assert_quotes(word, _text_of(_messages_turn(client, model, history, tools)))


# --- Responses -------------------------------------------------------------


def _responses_turn(client, model, items, tools):
    """One streamed Responses call, read the way Codex reads it.

    Codex is not built on the SDK. It reads the raw events and takes the
    finished response from response.completed, so that is what this does
    rather than handing the stream to the SDK's accumulator.
    """
    final = None
    # Codex keeps the conversation itself and sends all of it every turn. As
    # the server stores nothing, a reasoning model's reasoning only reaches
    # the next turn encrypted, so Codex asks for it on every request.
    for event in client.responses.create(
        model=model,
        instructions=_SYSTEM,
        input=items,
        max_output_tokens=_MAX_TOKENS,
        stream=True,
        store=False,
        include=["reasoning.encrypted_content"],
        **({"tools": _RESPONSES_TOOLS} if tools else {}),
    ):
        assert event.type not in ("error", "response.failed"), f"stream failed: {event}"
        assert event.type != "response.incomplete", (
            f"the answer was cut off: {event.response.incomplete_details}"
        )
        if event.type == "response.completed":
            final = event.response
    assert final is not None, "the stream ended without response.completed"
    return final


def responses(base_url, token, model, *, tools, round_trip):
    client = _openai(base_url, token)
    prompt = _TASK if tools and round_trip else PING
    items = [{"role": "user", "content": prompt}]
    final = _responses_turn(client, model, items, tools)
    if not (tools and round_trip):
        assert final.output_text, f"the reply has no text: {final.output}"
        return

    calls = [item for item in final.output if item.type == "function_call"]
    _assert_called(calls, final.output)
    word = secret()
    # Every item the model produced goes back, reasoning and all, as Codex
    # sends it, followed by a result for every call.
    items += [item.model_dump(exclude_none=True) for item in final.output]
    for call in calls:
        json.loads(call.arguments)
        items.append(
            {
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": _report(word),
            }
        )
    _assert_quotes(word, _responses_turn(client, model, items, tools).output_text)


# --- the other routes ------------------------------------------------------


def embeddings(base_url, token, model, **_):
    result = _openai(base_url, token).embeddings.create(model=model, input="Eden AI")
    assert result.data and result.data[0].embedding, "no embedding came back"


def images(base_url, token, model, **_):
    result = _openai(base_url, token).images.generate(
        model=model, prompt="A red circle on a white background", n=1
    )
    assert result.data and (result.data[0].url or result.data[0].b64_json), (
        "no image came back"
    )


def speech(base_url, token, model, **_):
    audio = _openai(base_url, token).audio.speech.create(
        model=model, voice="alloy", input="Eden AI"
    )
    assert audio.content, "no audio came back"


def transcriptions(base_url, token, model, **_):
    # Silence transcribes to an empty string, which is a valid answer: the
    # question is whether the route takes the model and the file.
    _openai(base_url, token).audio.transcriptions.create(
        model=model, file=("silence.wav", silent_wav())
    )


def moderations(base_url, token, model, **_):
    result = _openai(base_url, token).moderations.create(model=model, input="Eden AI")
    assert result.results, "no moderation result came back"


_REQUESTS = {
    "chat": chat,
    "messages": messages,
    "responses": responses,
    "embeddings": embeddings,
    "images": images,
    "speech": speech,
    "transcriptions": transcriptions,
    "moderations": moderations,
}


def send(request, base_url, token, model, *, tools, round_trip):
    """Send one request the way the tool that makes it would."""
    _REQUESTS[request](base_url, token, model, tools=tools, round_trip=round_trip)
