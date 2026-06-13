from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from source.runtime.tracing import QuestionTrace, RunTrace, SpanEvent


STATUS_LABELS = {
    "success": "完成",
    "error": "错误",
    "running": "运行中",
    "pending": "等待",
}


def write_dashboard(
    *,
    output_path: str | Path,
    run_trace: RunTrace,
    questions: list[dict[str, Any]],
    current_question_id: str | None,
    result_path: str | Path,
    trace_path: str | Path,
) -> None:
    """Write a compact, self-contained diagnostic dashboard atomically."""

    output_path = Path(output_path)
    traces = {trace.id: trace for trace in run_trace.questions}
    statuses = [
        _question_status(
            question_id=str(question.get("id", index)),
            trace=traces.get(str(question.get("id", index))),
            current_question_id=current_question_id,
        )
        for index, question in enumerate(questions, start=1)
    ]
    success_count = statuses.count("success")
    error_count = statuses.count("error")
    running_count = statuses.count("running")
    pending_count = statuses.count("pending")
    completed_count = success_count + error_count
    total = len(questions)
    progress = round((completed_count / total) * 100) if total else 0
    llm_calls = sum(
        span.type == "llm_call"
        for trace in run_trace.questions
        for span in trace.spans
    )
    tool_calls = sum(
        span.type == "tool_call"
        for trace in run_trace.questions
        for span in trace.spans
    )
    elapsed_ms = run_trace.total_duration_ms or sum(
        _trace_duration_ms(trace) for trace in run_trace.questions
    )
    cards = [
        _question_card(
            question=question,
            trace=traces.get(str(question.get("id", index))),
            status=statuses[index - 1],
            fallback_id=str(index),
        )
        for index, question in enumerate(questions, start=1)
    ]

    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="3">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Contest Dashboard</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #080d18;
      --surface: #101827;
      --surface-2: #151f31;
      --surface-3: #0c1321;
      --line: #25324a;
      --line-soft: #1b2639;
      --text: #edf4ff;
      --muted: #94a3ba;
      --dim: #66758d;
      --accent: #67b7ff;
      --accent-2: #8a7dff;
      --success: #4bd68a;
      --error: #ff6f7d;
      --warning: #ffbf69;
      --tool: #41d5c0;
      --shadow: 0 18px 60px rgba(0, 0, 0, .25);
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      background:
        radial-gradient(circle at 12% -10%, rgba(103, 183, 255, .15), transparent 30rem),
        radial-gradient(circle at 88% 0%, rgba(138, 125, 255, .10), transparent 26rem),
        var(--bg);
      font-family: Inter, "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
    }}
    main {{ width: min(1440px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 56px; }}
    .topbar {{
      display: grid;
      grid-template-columns: minmax(260px, 1fr) auto;
      gap: 24px;
      align-items: end;
      margin-bottom: 20px;
    }}
    .eyebrow {{
      color: var(--accent);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: .16em;
      text-transform: uppercase;
    }}
    h1 {{ margin: 7px 0 5px; font-size: clamp(26px, 3vw, 38px); letter-spacing: -.04em; }}
    .subtitle {{ color: var(--muted); font-size: 14px; }}
    .live-chip {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      border: 1px solid rgba(103, 183, 255, .28);
      border-radius: 999px;
      color: #cfe9ff;
      background: rgba(103, 183, 255, .08);
      font-size: 12px;
      white-space: nowrap;
    }}
    .live-dot {{
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 0 5px rgba(103, 183, 255, .10);
      animation: pulse 1.7s ease-in-out infinite;
    }}
    @keyframes pulse {{ 50% {{ opacity: .45; transform: scale(.82); }} }}
    .overview {{
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: linear-gradient(145deg, rgba(21, 31, 49, .96), rgba(13, 21, 35, .96));
      box-shadow: var(--shadow);
      margin-bottom: 18px;
    }}
    .progress-head {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
      margin-bottom: 11px;
      font-size: 13px;
    }}
    .progress-head strong {{ font-size: 15px; }}
    .progress-track {{
      height: 8px;
      overflow: hidden;
      border-radius: 999px;
      background: #080e19;
      border: 1px solid var(--line-soft);
    }}
    .progress-fill {{
      height: 100%;
      width: {progress}%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      box-shadow: 0 0 18px rgba(103, 183, 255, .32);
      transition: width .3s ease;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(7, minmax(100px, 1fr));
      gap: 10px;
      margin-top: 16px;
    }}
    .metric {{
      min-height: 82px;
      padding: 12px 14px;
      border-radius: 12px;
      background: rgba(8, 14, 25, .64);
      border: 1px solid var(--line-soft);
    }}
    .metric span {{ display: block; color: var(--muted); font-size: 12px; margin-bottom: 7px; }}
    .metric strong {{ font-size: 23px; letter-spacing: -.03em; }}
    .metric small {{ color: var(--dim); font-size: 11px; margin-left: 4px; }}
    .section-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin: 24px 2px 10px;
    }}
    .section-head h2 {{ margin: 0; font-size: 16px; }}
    .section-head span {{ color: var(--muted); font-size: 12px; }}
    .question-list {{ display: grid; gap: 10px; }}
    .question-card {{
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(16, 24, 39, .94);
      overflow: hidden;
      box-shadow: 0 8px 28px rgba(0, 0, 0, .14);
    }}
    .question-card.status-running {{
      border-color: rgba(103, 183, 255, .55);
      box-shadow: 0 0 0 1px rgba(103, 183, 255, .10), 0 12px 36px rgba(0, 0, 0, .20);
    }}
    .question-card.status-error {{ border-color: rgba(255, 111, 125, .48); }}
    .question-summary {{
      display: grid;
      grid-template-columns: auto minmax(180px, 1fr) minmax(180px, .8fr) auto;
      align-items: center;
      gap: 14px;
      min-height: 70px;
      padding: 13px 16px;
      cursor: pointer;
      list-style: none;
    }}
    .question-summary::-webkit-details-marker {{ display: none; }}
    .chevron {{
      width: 28px;
      height: 28px;
      display: grid;
      place-items: center;
      border-radius: 8px;
      color: var(--muted);
      background: var(--surface-3);
      border: 1px solid var(--line-soft);
      transition: transform .2s ease;
    }}
    details[open] .chevron {{ transform: rotate(90deg); }}
    .question-title {{ min-width: 0; }}
    .question-title strong {{
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 14px;
    }}
    .question-title span {{ color: var(--muted); font-size: 12px; }}
    .answer-preview {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: #c9d7eb;
      font: 12px/1.4 "Cascadia Code", Consolas, monospace;
      background: rgba(8, 14, 25, .65);
      border: 1px solid var(--line-soft);
      border-radius: 8px;
      padding: 8px 10px;
    }}
    .summary-meta {{ display: flex; align-items: center; justify-content: flex-end; gap: 8px; }}
    .mini-stat {{
      color: var(--muted);
      font: 11px/1 "Cascadia Code", Consolas, monospace;
      white-space: nowrap;
    }}
    .badge {{
      padding: 5px 9px;
      border-radius: 999px;
      border: 1px solid currentColor;
      font-size: 10px;
      font-weight: 800;
      letter-spacing: .05em;
      white-space: nowrap;
    }}
    .badge.success {{ color: var(--success); }}
    .badge.error {{ color: var(--error); }}
    .badge.running {{ color: var(--accent); }}
    .badge.pending {{ color: var(--dim); }}
    .question-body {{
      padding: 0 16px 18px 58px;
      border-top: 1px solid var(--line-soft);
    }}
    .description {{
      margin: 14px 0;
      color: #c3cfe0;
      font-size: 13px;
      line-height: 1.65;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .detail-grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(100px, 1fr));
      gap: 8px;
      margin-bottom: 16px;
    }}
    .detail-item {{
      padding: 10px 11px;
      border-radius: 9px;
      background: var(--surface-3);
      border: 1px solid var(--line-soft);
    }}
    .detail-item span {{ display: block; color: var(--dim); font-size: 10px; margin-bottom: 5px; }}
    .detail-item strong {{ font: 13px/1.2 "Cascadia Code", Consolas, monospace; }}
    .block-label {{
      margin: 16px 0 8px;
      color: var(--muted);
      font-size: 11px;
      font-weight: 800;
      letter-spacing: .08em;
      text-transform: uppercase;
    }}
    .answer-box, .error-box {{
      padding: 12px 14px;
      border-radius: 9px;
      white-space: pre-wrap;
      word-break: break-word;
      font: 12px/1.6 "Cascadia Code", Consolas, monospace;
    }}
    .answer-box {{
      color: #d9f8e7;
      background: rgba(75, 214, 138, .07);
      border: 1px solid rgba(75, 214, 138, .22);
    }}
    .answer-box.empty {{ color: var(--dim); background: var(--surface-3); border-color: var(--line-soft); }}
    .error-box {{ color: #ffd5da; background: rgba(255, 111, 125, .07); border: 1px solid rgba(255, 111, 125, .24); }}
    .call-timeline {{
      position: relative;
      display: grid;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
    }}
    .call-timeline::before {{
      content: "";
      position: absolute;
      top: 17px;
      bottom: 17px;
      left: 17px;
      width: 1px;
      background: var(--line);
    }}
    .call-item {{
      position: relative;
      display: grid;
      grid-template-columns: 35px minmax(0, 1fr);
      gap: 10px;
    }}
    .call-marker {{
      z-index: 1;
      width: 35px;
      height: 35px;
      display: grid;
      place-items: center;
      border-radius: 10px;
      color: #07101d;
      font-size: 9px;
      font-weight: 900;
      letter-spacing: .04em;
      box-shadow: 0 0 0 4px var(--surface);
    }}
    .call-item.llm .call-marker {{ background: var(--accent); }}
    .call-item.tool .call-marker {{ background: var(--tool); }}
    .call-panel {{
      min-width: 0;
      padding: 10px 12px;
      border-radius: 10px;
      background: var(--surface-3);
      border: 1px solid var(--line-soft);
    }}
    .call-head {{ display: flex; justify-content: space-between; gap: 12px; align-items: center; }}
    .call-name {{ font: 12px/1.4 "Cascadia Code", Consolas, monospace; color: #dce8f8; }}
    .call-time {{ color: var(--dim); font: 11px/1 "Cascadia Code", Consolas, monospace; }}
    .call-preview {{
      margin-top: 7px;
      color: var(--muted);
      font: 11px/1.55 "Cascadia Code", Consolas, monospace;
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 150px;
      overflow: auto;
    }}
    .call-detail {{ margin-top: 8px; }}
    .call-detail summary {{ color: var(--accent); cursor: pointer; font-size: 11px; }}
    .call-detail pre {{
      max-height: 220px;
      overflow: auto;
      margin: 8px 0 0;
      padding: 10px;
      color: #b9c7da;
      background: #070c15;
      border: 1px solid var(--line-soft);
      border-radius: 8px;
      white-space: pre-wrap;
      word-break: break-word;
      font: 10px/1.55 "Cascadia Code", Consolas, monospace;
    }}
    .empty-calls {{ color: var(--dim); font-size: 12px; padding: 8px 0; }}
    .run-meta {{
      margin-top: 16px;
      color: var(--dim);
      font-size: 11px;
    }}
    .run-meta summary {{ cursor: pointer; color: var(--muted); }}
    .run-meta div {{ margin-top: 8px; line-height: 1.7; word-break: break-all; }}
    @media (max-width: 980px) {{
      .metrics {{ grid-template-columns: repeat(3, 1fr); }}
      .question-summary {{ grid-template-columns: auto minmax(0, 1fr) auto; }}
      .answer-preview {{ grid-column: 2 / -1; grid-row: 2; }}
      .summary-meta {{ grid-column: 3; grid-row: 1; }}
      .detail-grid {{ grid-template-columns: repeat(3, 1fr); }}
    }}
    @media (max-width: 640px) {{
      main {{ width: min(100% - 20px, 1440px); padding-top: 18px; }}
      .topbar {{ grid-template-columns: 1fr; gap: 12px; }}
      .metrics {{ grid-template-columns: repeat(2, 1fr); }}
      .question-summary {{ padding: 12px; gap: 9px; }}
      .question-body {{ padding: 0 12px 15px; }}
      .detail-grid {{ grid-template-columns: repeat(2, 1fr); }}
      .summary-meta .mini-stat {{ display: none; }}
    }}
  </style>
</head>
<body>
<main>
  <header class="topbar">
    <div>
      <div class="eyebrow">Local diagnostics</div>
      <h1>Agent Contest Dashboard</h1>
      <div class="subtitle">实时查看题目状态、模型调用、工具调用和最终答案</div>
    </div>
    <div class="live-chip"><span class="live-dot"></span>每 3 秒刷新 · {_text(run_trace.model)}</div>
  </header>

  <section class="overview">
    <div class="progress-head">
      <strong>整体进度</strong>
      <span>{completed_count} / {total} 题完成 · {progress}%</span>
    </div>
    <div class="progress-track"><div class="progress-fill"></div></div>
    <div class="metrics">
      {_metric("题目", total, f"{pending_count} 等待")}
      {_metric("已完成", success_count, "成功")}
      {_metric("运行中", running_count, "当前")}
      {_metric("错误", error_count, "需检查")}
      {_metric("累计耗时", _duration(elapsed_ms), "")}
      {_metric("LLM 调用", llm_calls, "次")}
      {_metric("工具调用", tool_calls, "次")}
    </div>
  </section>

  <div class="section-head">
    <h2>题目执行记录</h2>
    <span>运行中和错误题自动展开</span>
  </div>
  <section class="question-list">
    {''.join(cards)}
  </section>

  <details class="run-meta">
    <summary>运行文件</summary>
    <div>
      Result: {_text(str(Path(result_path).resolve()))}<br>
      Trace: {_text(str(Path(trace_path).resolve()))}<br>
      Run ID: {_text(run_trace.run_id)}
    </div>
  </details>
</main>
<script>
  const storageKey = "agent-dashboard-open-questions";
  const stored = new Set(JSON.parse(sessionStorage.getItem(storageKey) || "[]"));
  document.querySelectorAll("details.question-card").forEach((card) => {{
    if (stored.has(card.id)) card.open = true;
    card.addEventListener("toggle", () => {{
      const openIds = [...document.querySelectorAll("details.question-card[open]")]
        .filter((item) => !item.classList.contains("status-running") && !item.classList.contains("status-error"))
        .map((item) => item.id);
      sessionStorage.setItem(storageKey, JSON.stringify(openIds));
    }});
  }});
</script>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.name}.tmp")
    temporary_path.write_text(document, encoding="utf-8")
    temporary_path.replace(output_path)


def _question_status(
    *,
    question_id: str,
    trace: QuestionTrace | None,
    current_question_id: str | None,
) -> str:
    if trace is not None:
        return trace.status
    if question_id == current_question_id:
        return "running"
    return "pending"


def _question_card(
    *,
    question: dict[str, Any],
    trace: QuestionTrace | None,
    status: str,
    fallback_id: str,
) -> str:
    question_id = str(question.get("id", fallback_id))
    title = str(question.get("title", "")).strip() or f"Question {question_id}"
    description = str(question.get("description", ""))
    open_attribute = " open" if status in {"running", "error"} else ""
    counts = (
        trace.diagnostic_counts()
        if trace is not None
        else {"llm_calls": 0, "tool_calls": 0}
    )
    duration_ms = _trace_duration_ms(trace) if trace is not None else 0
    answer = trace.answer if trace is not None else ""
    preview = answer.strip() or (
        "正在执行，等待最终答案..." if status == "running" else "尚未开始"
    )
    if len(preview) > 120:
        preview = preview[:117] + "..."

    if trace is None:
        detail_grid = ""
        answer_block = ""
        error_block = ""
        timeline = '<div class="empty-calls">等待 Agent 开始执行。</div>'
    else:
        detail_grid = f"""
        <div class="detail-grid">
          {_detail_item("耗时", _duration(duration_ms))}
          {_detail_item("LLM", str(counts["llm_calls"]))}
          {_detail_item("工具", str(counts["tool_calls"]))}
          {_detail_item("Prompt", str(trace.tokens.get("prompt", 0)))}
          {_detail_item("Completion", str(trace.tokens.get("completion", 0)))}
        </div>
        """
        answer_class = "answer-box" if answer else "answer-box empty"
        answer_text = answer or (
            "Agent 正在处理，最终答案尚未生成。"
            if status == "running"
            else "(empty)"
        )
        answer_block = (
            '<div class="block-label">最终答案</div>'
            f'<div class="{answer_class}">{_text(answer_text)}</div>'
        )
        error_block = (
            '<div class="block-label">错误</div>'
            f'<div class="error-box">{_text(trace.error)}</div>'
            if trace.error
            else ""
        )
        timeline = _call_timeline(trace)

    return f"""
    <details id="question-{_text(question_id)}" class="question-card status-{_text(status)}"{open_attribute}>
      <summary class="question-summary">
        <span class="chevron">›</span>
        <span class="question-title">
          <strong>{_text(question_id)} · {_text(title)}</strong>
          <span>{counts["llm_calls"]} LLM · {counts["tool_calls"]} Tool · {_duration(duration_ms)}</span>
        </span>
        <span class="answer-preview">{_text(preview)}</span>
        <span class="summary-meta">
          <span class="mini-stat">{counts["llm_calls"] + counts["tool_calls"]} calls</span>
          <span class="badge {_text(status)}">{_text(STATUS_LABELS.get(status, status))}</span>
        </span>
      </summary>
      <div class="question-body">
        <div class="block-label">题目描述</div>
        <div class="description">{_text(description)}</div>
        {detail_grid}
        {answer_block}
        {error_block}
        <div class="block-label">调用时间线</div>
        {timeline}
      </div>
    </details>
    """


def _call_timeline(trace: QuestionTrace) -> str:
    if not trace.spans:
        return '<div class="empty-calls">暂时没有已完成的调用。</div>'
    return (
        '<ol class="call-timeline">'
        + "".join(_call_item(span) for span in trace.spans)
        + "</ol>"
    )


def _call_item(span: SpanEvent) -> str:
    is_llm = span.type == "llm_call"
    item_class = "llm" if is_llm else "tool"
    marker = "AI" if is_llm else "TOOL"
    if is_llm:
        name = str(span.data.get("model", "LLM"))
        preview = str(span.data.get("output_preview", "")) or "(empty response)"
        usage = span.data.get("usage") or {}
        requested_tools = span.data.get("tool_calls") or []
        detail_parts = [
            f"messages={span.data.get('messages_count', 0)}",
            f"tools={span.data.get('tools_count', 0)}",
            f"finish_reason={span.data.get('finish_reason') or '-'}",
            f"prompt_tokens={usage.get('prompt_tokens', 0)}",
            f"completion_tokens={usage.get('completion_tokens', 0)}",
        ]
        if requested_tools:
            detail_parts.append(
                "requested_tools="
                + ", ".join(str(call.get("name", "")) for call in requested_tools)
            )
        detail = "\n".join(detail_parts)
    else:
        name = str(span.data.get("tool_name", "tool"))
        preview = str(span.data.get("error") or span.data.get("result", "")) or "(empty result)"
        detail = (
            "arguments:\n"
            + _pretty(span.data.get("arguments", {}))
            + "\n\nresult:\n"
            + str(span.data.get("result", ""))
        )
        if span.data.get("error"):
            detail += "\n\nerror:\n" + str(span.data["error"])

    return f"""
    <li class="call-item {item_class}">
      <div class="call-marker">{marker}</div>
      <div class="call-panel">
        <div class="call-head">
          <span class="call-name">{_text(name)}</span>
          <span class="call-time">{_duration(span.duration_ms)}</span>
        </div>
        <div class="call-preview">{_text(preview)}</div>
        <details class="call-detail">
          <summary>查看详情</summary>
          <pre>{_text(detail)}</pre>
        </details>
      </div>
    </li>
    """


def _trace_duration_ms(trace: QuestionTrace) -> int:
    if trace.duration_ms:
        return trace.duration_ms
    return sum(span.duration_ms for span in trace.spans)


def _metric(label: str, value: Any, note: str) -> str:
    return (
        '<div class="metric">'
        f"<span>{_text(label)}</span>"
        f"<strong>{value}</strong>"
        f"<small>{_text(note)}</small>"
        "</div>"
    )


def _detail_item(label: str, value: str) -> str:
    return (
        '<div class="detail-item">'
        f"<span>{_text(label)}</span>"
        f"<strong>{_text(value)}</strong>"
        "</div>"
    )


def _duration(milliseconds: int) -> str:
    if milliseconds < 1000:
        return f"{milliseconds}ms"
    if milliseconds < 60_000:
        return f"{milliseconds / 1000:.1f}s"
    minutes, seconds = divmod(milliseconds // 1000, 60)
    return f"{minutes}m {seconds}s"


def _pretty(value: Any) -> str:
    import json

    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(value)


def _text(value: Any) -> str:
    return escape(str(value), quote=True)
