# Streaming And 600-Second Timeout Design

**Status:** Approved
**Date:** 2026-06-12

## Goal

Adapt the model client to the competition requirement that requests use
`stream=true` and allow up to 600 seconds per model request.

## Configuration

- `ModelConfig.from_env()` defaults `AGENT_DEMO_STREAM` to `true`.
- `ModelConfig.from_env()` defaults `AGENT_DEMO_TIMEOUT_SECONDS` to `600`.
- Explicit environment values still override both defaults.
- `.env.example`, README, GUIDE, and the architecture document use the same
  defaults.

## Streaming Response Contract

The OpenAI-compatible client continues to return one normalized chat completion
object to the agent loop. For SSE responses it must:

- concatenate fragmented assistant content;
- concatenate fragmented reasoning content;
- merge fragmented native tool calls by index;
- preserve completion metadata and the final finish reason;
- preserve the optional usage-only tail chunk;
- stop cleanly at `[DONE]`;
- surface stream-level error payloads as runtime errors;
- reject an SSE response that contains no usable choice.

The agent loop remains transport-agnostic and requires no separate stream path.

## Testing

Add focused tests for defaults, explicit overrides, request payload and timeout,
fragmented content, fragmented tool calls, usage tails, stream errors, and empty
streams. Then run all unit tests, source compilation, diff checks, and available
official-case regressions.
