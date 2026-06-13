from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from source.runtime.tracing import QuestionTrace, RunTrace


def write_dashboard(
    *,
    output_path: str | Path,
    run_trace: RunTrace,
    questions: list[dict[str, Any]],
    current_question_id: str | None,
    result_path: str | Path,
    trace_path: str | Path,
) -> None:
    """Write a self-contained dashboard atomically."""

    output_path = Path(output_path)
    completed = {trace.id: trace for trace in run_trace.questions}
    cards = [
        _question_card(
            question=question,
            trace=completed.get(str(question.get("id", index))),
            running=str(question.get("id", index)) == current_question_id,
            fallback_id=str(index),
        )
        for index, question in enumerate(questions, start=1)
    ]
    success_count = sum(trace.status == "success" for trace in run_trace.questions)
    error_count = sum(trace.status == "error" for trace in run_trace.questions)
    running_count = int(current_question_id is not None)
    pending_count = max(
        0,
        len(questions) - len(run_trace.questions) - running_count,
    )

    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="3">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Contest Dashboard</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0b1020;
      --panel: #151d33;
      --line: #2b3858;
      --text: #edf3ff;
      --muted: #9fb0ce;
      --success: #45d483;
      --error: #ff6b78;
      --running: #55b8ff;
      --pending: #7f8da8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, "Segoe UI", system-ui, sans-serif;
    }}
    main {{ width: min(1500px, calc(100% - 32px)); margin: 24px auto 48px; }}
    header {{ display: flex; justify-content: space-between; gap: 20px; align-items: end; }}
    h1 {{ margin: 0 0 6px; font-size: 28px; }}
    .muted {{ color: var(--muted); }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(5, minmax(110px, 1fr));
      gap: 12px;
      margin: 20px 0;
    }}
    .metric, article {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
    }}
    .metric {{ padding: 14px; }}
    .metric strong {{ display: block; font-size: 24px; margin-top: 4px; }}
    article {{ margin: 14px 0; overflow: hidden; }}
    .question-head {{ display: flex; justify-content: space-between; gap: 16px; padding: 16px; }}
    .question-body {{ border-top: 1px solid var(--line); padding: 16px; }}
    .badge {{ border-radius: 999px; padding: 5px 10px; font-size: 12px; font-weight: 700; }}
    .success {{ color: var(--success); border: 1px solid var(--success); }}
    .error {{ color: var(--error); border: 1px solid var(--error); }}
    .running {{ color: var(--running); border: 1px solid var(--running); }}
    .pending {{ color: var(--pending); border: 1px solid var(--pending); }}
    .details {{ display: grid; grid-template-columns: repeat(5, minmax(100px, 1fr)); gap: 10px; }}
    .details div {{ background: #0f1629; border-radius: 8px; padding: 10px; }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      background: #090e1a;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      max-height: 420px;
      overflow: auto;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ text-align: left; border-bottom: 1px solid var(--line); padding: 9px; vertical-align: top; }}
    @media (max-width: 800px) {{
      .summary, .details {{ grid-template-columns: repeat(2, 1fr); }}
      header {{ align-items: start; flex-direction: column; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Agent Contest Dashboard</h1>
      <div class="muted">Auto-refreshes every 3 seconds. Generated only with --dashboard.</div>
    </div>
    <div class="muted">
      Model: {_text(run_trace.model)}<br>
      Result: {_text(str(Path(result_path).resolve()))}<br>
      Trace: {_text(str(Path(trace_path).resolve()))}
    </div>
  </header>
  <section class="summary">
    {_metric("Total", len(questions))}
    {_metric("Success", success_count)}
    {_metric("Error", error_count)}
    {_metric("Running", running_count)}
    {_metric("Pending", pending_count)}
  </section>
  <section>
    {''.join(cards)}
  </section>
</main>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.name}.tmp")
    temporary_path.write_text(document, encoding="utf-8")
    temporary_path.replace(output_path)


def _question_card(
    *,
    question: dict[str, Any],
    trace: QuestionTrace | None,
    running: bool,
    fallback_id: str,
) -> str:
    question_id = str(question.get("id", fallback_id))
    title = str(question.get("title", "")).strip() or f"Question {question_id}"
    description = str(question.get("description", ""))
    if trace is not None:
        status = trace.status
    elif running:
        status = "running"
    else:
        status = "pending"

    if trace is None:
        details = ""
        answer = ""
        error = ""
        spans = ""
    else:
        counts = trace.diagnostic_counts()
        details = f"""
        <div class="details">
          <div><span class="muted">Duration</span><br>{trace.duration_ms / 1000:.2f}s</div>
          <div><span class="muted">LLM calls</span><br>{counts["llm_calls"]}</div>
          <div><span class="muted">Tool calls</span><br>{counts["tool_calls"]}</div>
          <div><span class="muted">Prompt tokens</span><br>{trace.tokens.get("prompt", 0)}</div>
          <div><span class="muted">Completion tokens</span><br>{trace.tokens.get("completion", 0)}</div>
        </div>
        """
        answer = (
            f"<h3>Answer</h3><pre>{_text(trace.answer)}</pre>"
            if trace.answer
            else "<h3>Answer</h3><pre>(empty)</pre>"
        )
        error = (
            f"<h3>Error</h3><pre>{_text(trace.error)}</pre>"
            if trace.error
            else ""
        )
        spans = _span_table(trace)

    return f"""
    <article>
      <div class="question-head">
        <div><strong>{_text(question_id)}: {_text(title)}</strong></div>
        <span class="badge {_text(status)}">{_text(status.upper())}</span>
      </div>
      <div class="question-body">
        <h3>Description</h3>
        <pre>{_text(description)}</pre>
        {details}
        {answer}
        {error}
        {spans}
      </div>
    </article>
    """


def _span_table(trace: QuestionTrace) -> str:
    if not trace.spans:
        return "<h3>Calls</h3><div class=\"muted\">No recorded calls.</div>"

    rows = []
    for span in trace.spans:
        if span.type == "llm_call":
            name = str(span.data.get("model", "LLM"))
            detail = str(span.data.get("output_preview", ""))
        else:
            name = str(span.data.get("tool_name", "tool"))
            detail = str(span.data.get("error") or span.data.get("result", ""))
        rows.append(
            "<tr>"
            f"<td>{span.seq + 1}</td>"
            f"<td>{_text(span.type)}</td>"
            f"<td>{_text(name)}</td>"
            f"<td>{span.duration_ms / 1000:.2f}s</td>"
            f"<td><pre>{_text(detail)}</pre></td>"
            "</tr>"
        )
    return (
        "<h3>Calls</h3><table><thead><tr>"
        "<th>#</th><th>Type</th><th>Name</th><th>Time</th><th>Preview</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _metric(label: str, value: int) -> str:
    return f'<div class="metric"><span class="muted">{_text(label)}</span><strong>{value}</strong></div>'


def _text(value: Any) -> str:
    return escape(str(value), quote=True)
