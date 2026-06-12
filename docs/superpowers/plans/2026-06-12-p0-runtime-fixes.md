# P0 Runtime Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the non-functional answer checker and data reader, correct competition date calculations, clarify dashboard execution status, and raise the model timeout and tool-output budget.

**Architecture:** Keep the existing agent packages as prompt builders, but execute their prompt envelopes through the shared `ChatCompletionClient`. Pass the current question and allowed MCP tools through `AgentContext -> LocalMCPClient -> AgentRegistry`, so `data_reader` can run a bounded tool loop without bypassing file permissions. Keep date parsing deterministic and covered by official-case regressions.

**Tech Stack:** Python 3.11+, standard-library `unittest`, existing OpenAI-compatible client and local MCP runtime.

---

### Task 1: Add P0 regression coverage

**Files:**
- Create: `tests/test_p0_runtime_fixes.py`

- [x] Add tests for the 300-second timeout default and 65,536-character tool result budget.
- [x] Add tests reproducing `大后天`, natural-week weekdays, hour offsets, day offsets, and fiscal-week Friday failures.
- [x] Add mocked-client tests proving both sub-agents execute an LLM call and that `data_reader` can execute an allowed MCP tool.
- [x] Add a dashboard rendering test that distinguishes execution completion from answer correctness.
- [x] Run `python -m unittest discover -s tests -v` and confirm the new tests fail for the expected missing behavior.

### Task 2: Implement LLM-backed sub-agents

**Files:**
- Modify: `source/solution/sub_agents.py`
- Modify: `source/runtime/agent_registry.py`
- Modify: `source/runtime/mcp_client.py`
- Modify: `source/runtime/agent_context.py`
- Modify: `source/solution/contestant_agent.py`
- Modify: `source/solution/agents/answer_checker/agent.json`
- Modify: `source/solution/agents/data_reader/agent.json`

- [x] Enrich prompt-builder payloads with the public question, declared files, and inferred data-reader mode.
- [x] Execute prompt envelopes with `ChatCompletionClient`.
- [x] Allow only non-agent MCP tools inside the data-reader loop and preserve the original runtime permission context.
- [x] Include recent tool evidence when the main answer is verified.
- [x] Fail closed when checker output is malformed or omits `overall_valid`.
- [x] Run the sub-agent regression tests and confirm they pass.

### Task 3: Repair date calculations

**Files:**
- Modify: `source/solution/mcp/contestant_tools.py`

- [x] Parse explicit base dates and optional hours before applying relative expressions.
- [x] Match longer relative-date phrases before shorter substrings.
- [x] Implement `上周/下周/本周` against calendar-week boundaries.
- [x] Handle signed hour/day/week offsets before generic month parsing.
- [x] Treat an explicitly declared fiscal-week start as the start of that named week.
- [x] Run the date regression tests and confirm they pass.

### Task 4: Update runtime budgets and dashboard semantics

**Files:**
- Modify: `source/runtime/env_config.py`
- Modify: `source/solution/contestant_agent.py`
- Modify: `source/runtime/generate_dashboard.py`
- Modify: `.env.example`
- Modify: `DESIGN_CORE_ENHANCEMENTS.md`

- [x] Set the default LLM timeout to 300 seconds.
- [x] Centralize tool-history truncation with a 65,536-character default and environment override.
- [x] Rename dashboard summary labels from pass/fail to completed/errors.
- [x] Remove unsupported documentation claims that execution success means official-answer correctness.

### Task 5: Verify the integrated runtime

**Files:**
- Test: `tests/test_p0_runtime_fixes.py`

- [x] Run `python -m unittest discover -s tests -v`.
- [x] Run `python -m compileall -q source tests`.
- [x] Run targeted local probes for the official date expressions.
- [x] Inspect `git diff --check` and `git status --short` without changing unrelated user files.
