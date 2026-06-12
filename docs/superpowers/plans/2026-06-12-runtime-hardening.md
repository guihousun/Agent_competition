# Runtime Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent unsafe task replay, make Java execution reliable, provide safe readable archive workspaces, and propagate the contest package identifier automatically.

**Architecture:** Keep capabilities default-open as requested. Add narrow error classification around native-tool fallback, execute Java in a correctly named UTF-8 temporary project, route archive extraction into a per-question temporary workspace already included in the file allowlist, and inject `X-Package-Id` at the MCP runtime boundary.

**Tech Stack:** Python standard library, `unittest`, Java/Javac runtime, existing MCP and AgentContext layers.

---

### Task 1: Regression tests

**Files:**
- Create: `tests/test_runtime_hardening.py`

- [ ] Verify generic model/tool exceptions do not trigger JSON replay.
- [ ] Verify explicit tool-compatibility gateway errors can trigger JSON fallback.
- [ ] Verify Java public classes compile as UTF-8 and receive command-line arguments.
- [ ] Verify one Java compilation can run multiple stdin cases.
- [ ] Verify ZIP/TAR files extract into a readable question workspace.
- [ ] Verify traversal archive members are rejected.
- [ ] Verify `X-Package-Id` is injected and explicit headers take precedence.

### Task 2: Narrow fallback

**Files:**
- Modify: `source/solution/contestant_agent.py`

- [ ] Add explicit unsupported-native-tools error classification.
- [ ] Preserve the original exception for network, timeout, model, and tool failures.

### Task 3: Java execution

**Files:**
- Modify: `source/solution/mcp/contestant_tools.py`

- [ ] Detect the public class or class containing `static void main`.
- [ ] Compile in a temporary directory using `javac -encoding UTF-8`.
- [ ] Add shared command-line `args` and optional `stdin_cases`.
- [ ] Return structured per-run results without recompiling each case.

### Task 4: Archive workspace

**Files:**
- Modify: `source/runtime/agent_context.py`
- Modify: `source/runtime/batch_runner.py`
- Modify: `source/runtime/mcp_client.py`
- Modify: `source/solution/mcp/contestant_tools.py`

- [ ] Create and clean one temporary workspace per question.
- [ ] Include that workspace in allowed file roots.
- [ ] Force archive output underneath the workspace.
- [ ] Validate every ZIP/TAR member before extraction and reject traversal or links.

### Task 5: Package header

**Files:**
- Modify: `source/runtime/agent_context.py`
- Modify: `source/runtime/batch_runner.py`
- Modify: `source/runtime/mcp_client.py`

- [ ] Propagate `ModelConfig.package_id` into runtime context.
- [ ] Add `X-Package-Id` to every `http_request`, including an empty value locally.
- [ ] Preserve a caller-provided case-insensitive package header.

### Task 6: Verification

**Files:**
- Test: `tests/test_p0_runtime_fixes.py`
- Test: `tests/test_runtime_hardening.py`

- [ ] Run all unit tests.
- [ ] Run source compilation.
- [ ] Re-run Java and archive integration probes.
- [ ] Run `git diff --check`.
