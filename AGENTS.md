# AGENTS.md

## Project Overview

This repository is a Python 3.11+ reference implementation for the Skill
Distillation Agent Contest. It runs question batches through a contestant
agent, exposes local MCP-style tools, skills, and sub-agents, records traces,
and generates an HTML dashboard.

The normal execution flow is:

1. `source/main.py` parses CLI arguments.
2. `source/runtime/batch_runner.py` loads questions and builds an
   `AgentContext`.
3. `source/solution/contestant_agent.py` runs the model/tool loop.
4. `source/runtime/mcp_client.py` dispatches tools, skills, and sub-agents.
5. Results, traces, and the dashboard are written beside the requested output.

## Environment

- Use Python 3.11 or newer.
- Do not use Conda for this project.
- Install dependencies with:

```bash
python -m pip install -r requirements.txt
```

- Copy `.env.example` to `.env` and configure at least:
  `MODEL_CHAT_COMPLETIONS_URL`, `MODEL_API_KEY`, and `MODEL_NAME`.
- Never print, commit, or copy secret values from `.env`.
- The main runtime dependencies are `openpyxl`, `pandas`, and `numpy`.

## Common Commands

Run a question batch:

```bash
bash start.sh source/examples/questions.json source/outputs/result.json
```

Run directly with Python:

```bash
python -u -m source.main --question source/examples/questions.json --output source/outputs/result.json
```

Display answers:

```bash
python -m source.runtime.show_answers source/outputs/result.json
```

Serve the generated dashboard:

```bash
cd source/outputs
python -m http.server 8766
```

Verify the Python environment:

```bash
python -c "import openpyxl, pandas, numpy; print('deps: OK')"
```

## Code Ownership

The primary contestant-editable area is `source/solution/`:

- `contestant_agent.py`: system prompt, ReAct loop, tool-call handling, answer
  cleanup, and self-check behavior.
- `mcp/contestant_tools.py`: contestant-provided MCP-style tools.
- `skills/`: packaged skills with `SKILL.md`, `skill.json`, scripts, and
  optional resources.
- `agents/`: packaged sub-agents.
- `sub_agents.py`: sub-agent package loading and execution.

Treat `source/runtime/` and `source/toolkits/` as shared framework code. Change
them only when the requested behavior cannot be implemented cleanly in
`source/solution/`, or when fixing a framework-level defect.

Do not edit generated files in `source/outputs/` as source code. Regenerate
them by running the appropriate question batch.

## Question Files

Question JSON may contain `id`, `title`, `description`, `files`, `level`,
`tools`, `skills`, and `sub_agents`.

Important path rule: entries in `files` are resolved relative to the directory
containing the question JSON file. File contents are not inserted into the
prompt automatically; the agent must use an allowed file-reading tool.

When adding an example:

1. Put the question JSON under `source/examples/`.
2. Put its fixture files under a nearby directory such as
   `source/examples/files/`.
3. Use relative paths in the question's `files` field.
4. Write outputs under `source/outputs/`.

## Tools, Skills, and Sub-agents

Register a direct tool in `source/solution/mcp/contestant_tools.py` using the
existing `register_tool` and `object_schema` pattern.

Tool requirements:

- Use a unique, descriptive name.
- Declare an accurate JSON input schema.
- Return text, normally JSON serialized with `ensure_ascii=False`.
- Handle expected failures explicitly instead of leaking tracebacks to the
  model.
- Apply path validation and timeouts to filesystem, archive, network, and
  subprocess operations.
- Keep tool output bounded because results enter the model context.

A skill package should contain:

```text
source/solution/skills/<skill-name>/
├── SKILL.md
├── skill.json
├── scripts/run.py
└── references/ or assets/     # optional
```

Skill scripts communicate through JSON on stdin/stdout. Follow the package's
`SKILL.md` before changing or invoking its implementation.

A sub-agent package lives under `source/solution/agents/<agent-name>/` and is
discovered through its `agent.json` metadata.

## Implementation Rules

- Preserve the public result shape: a JSON array of
  `{"id": "...", "answer": "..."}` objects.
- Final model answers must contain only the requested answer body. Do not add
  explanations, Markdown fences, `<think>` tags, or wrapper objects unless the
  question explicitly requires them.
- Maintain compatibility with both native tool calling and the JSON-tool
  fallback.
- Use async APIs consistently in the agent/runtime path. Avoid blocking work
  in async code unless it is isolated behind the existing subprocess model.
- Use `pathlib.Path` for filesystem operations.
- Use UTF-8 and `ensure_ascii=False` for user-facing Chinese content.
- Prefer atomic writes for result or trace files.
- Do not broaden file access beyond the paths declared by the question.
- Do not silently weaken subprocess, archive extraction, network, or timeout
  safeguards.
- Keep changes scoped. Do not refactor unrelated runtime code while modifying
  a tool, skill, prompt, or test case.

## Validation

There is no dedicated pytest suite configured. Validate changes with the
smallest relevant example first, then a broader batch when the change affects
shared behavior.

Suggested validation order:

1. Compile changed Python modules:

```bash
python -m compileall source
```

2. Run a focused example that exercises the changed behavior:

```bash
bash start.sh source/examples/test_react_simple.json source/outputs/test_react_simple_result.json
```

3. For tools or skills, run their corresponding example file.
4. For shared agent/runtime changes, run `source/examples/questions.json`.
5. Inspect the answer JSON, `traces.json`, and `dashboard.html`.

LLM-backed tests depend on external model credentials and may be slow or
nondeterministic. Report clearly when they were not run.

## Git and Generated Artifacts

- The worktree may already contain user changes. Never discard or overwrite
  unrelated modifications.
- Do not use destructive Git commands unless explicitly requested.
- Avoid committing `.env`, temporary extraction directories, archives,
  generated outputs, or dashboard artifacts unless the user specifically asks
  for them.
- Before committing, inspect `git status` and ensure only intended files are
  staged.

## CodeGraph

This project has a local CodeGraph index in `.codegraph/`.

Use CodeGraph for structural questions:

| Need | Tool |
|---|---|
| Find a symbol definition | `codegraph_search` |
| Understand a feature or symbol in context | `codegraph_context` |
| Find callers or callees | `codegraph_callers` / `codegraph_callees` |
| Estimate change impact | `codegraph_impact` |
| Inspect a symbol signature or source | `codegraph_node` |
| Survey an unfamiliar area | `codegraph_explore` |
| Inspect indexed files | `codegraph_files` |
| Check index health | `codegraph_status` |

Prefer CodeGraph over grep for symbol and dependency questions. Use native
search for literal strings, comments, logs, and exact text. After changing
Python files, allow the watcher time to update or run:

```bash
codegraph sync .
```

Do not re-verify CodeGraph structural results with grep unless the index is
stale or reports an error.

## Documentation

Use these documents as supporting context:

- `README.md`: current project overview and quick start.
- `GUIDE.md`: detailed operation, examples, extension points, and debugging.
- `P0_TOOLS.md`: tool-specific behavior.
- `CAPABILITY_GAP.md`: contest capability coverage.
- `DESIGN_CORE_ENHANCEMENTS.md`: architecture and enhancement rationale.

When documentation conflicts with executable code, verify the current code
path and update documentation as part of the same scoped change when
appropriate.
