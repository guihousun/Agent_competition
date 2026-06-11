"""Generate a self-contained dashboard HTML from traces.json.

Usage:
    python -m source.runtime.generate_dashboard source/outputs/traces.json source/outputs/dashboard.html

Or called automatically by BatchRunner after a run completes.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def collect_capabilities(project_root: Path) -> dict:
    """Collect agent capabilities by scanning the project structure."""
    caps = {
        "system_prompt": "",
        "tools": [],
        "skills": [],
        "sub_agents": [],
        "config": {},
    }

    # 1. System Prompt from contestant_agent.py
    agent_file = project_root / "source" / "solution" / "contestant_agent.py"
    if agent_file.exists():
        content = agent_file.read_text(encoding="utf-8")
        match = re.search(r'SYSTEM_PROMPT\s*=\s*"""(.*?)"""', content, re.DOTALL)
        if match:
            caps["system_prompt"] = match.group(1).strip()

    # 2. Tools from contestant_tools.py
    tools_file = project_root / "source" / "solution" / "mcp" / "contestant_tools.py"
    if tools_file.exists():
        content = tools_file.read_text(encoding="utf-8")
        # Find all name="..." patterns after @register_tool
        # Format: @register_tool(\n        name="...",\n        description="...",
        for match in re.finditer(
            r'@register_tool\([^)]*name="([^"]+)"[^)]*description="([^"]*)"',
            content,
            re.DOTALL,
        ):
            caps["tools"].append({
                "name": match.group(1),
                "description": match.group(2),
            })

    # 3. Skills from source/solution/skills/
    skills_dir = project_root / "source" / "solution" / "skills"
    if skills_dir.exists():
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            skill_json = skill_dir / "skill.json"
            skill_info = {"name": skill_dir.name, "description": ""}
            if skill_json.exists():
                try:
                    meta = json.loads(skill_json.read_text(encoding="utf-8"))
                    skill_info["description"] = meta.get("description", "")
                    skill_info["entrypoint"] = meta.get("entrypoint", "")
                except:
                    pass
            elif skill_md.exists():
                # Extract first line after frontmatter
                content = skill_md.read_text(encoding="utf-8")
                lines = content.split("\n")
                for line in lines:
                    if line.strip() and not line.startswith("---") and not line.startswith("name:") and not line.startswith("description:"):
                        skill_info["description"] = line.strip().lstrip("#").strip()
                        break
            caps["skills"].append(skill_info)

    # 4. Sub-agents from source/solution/agents/
    agents_dir = project_root / "source" / "solution" / "agents"
    if agents_dir.exists():
        for agent_dir in sorted(agents_dir.iterdir()):
            if not agent_dir.is_dir():
                continue
            agent_json = agent_dir / "agent.json"
            agent_info = {"name": agent_dir.name, "description": ""}
            if agent_json.exists():
                try:
                    meta = json.loads(agent_json.read_text(encoding="utf-8"))
                    agent_info["description"] = meta.get("description", meta.get("role", ""))
                    agent_info["entrypoint"] = meta.get("entrypoint", "")
                except:
                    pass
            caps["sub_agents"].append(agent_info)

    # 5. Config from .env
    env_file = project_root / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                # Only include non-sensitive config
                if key in ("MODEL_NAME", "AGENT_DEMO_MAX_ITER", "AGENT_DEMO_TEMPERATURE"):
                    caps["config"][key] = value

    return caps


_DASHBOARD_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Agent Contest Dashboard</title>
<style>
/* ============================================================
   CSS — LangSmith-inspired dark theme
   ============================================================ */
:root {
  --bg-primary: #0d1117;
  --bg-secondary: #161b22;
  --bg-tertiary: #21262d;
  --bg-hover: #30363d;
  --border: #30363d;
  --text-primary: #e6edf3;
  --text-secondary: #8b949e;
  --text-muted: #6e7681;
  --accent-blue: #58a6ff;
  --accent-green: #3fb950;
  --accent-red: #f85149;
  --accent-orange: #d29922;
  --accent-purple: #bc8cff;
  --accent-cyan: #39d2c0;
  --accent-pink: #f778ba;
  --span-llm: #58a6ff;
  --span-tool: #3fb950;
  --span-skill: #bc8cff;
  --span-agent: #d29922;
  --span-file: #39d2c0;
  --span-error: #f85149;
  --radius: 8px;
  --shadow: 0 1px 3px rgba(0,0,0,0.3);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  line-height: 1.5;
  min-height: 100vh;
  padding-top: 57px;
}

/* Header */
.header {
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  padding: 16px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-logo {
  font-size: 20px;
  font-weight: 700;
  color: var(--accent-blue);
}

.header-title {
  font-size: 14px;
  color: var(--text-secondary);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 12px;
  color: var(--text-secondary);
}

.header-badge {
  background: var(--bg-tertiary);
  padding: 4px 10px;
  border-radius: 12px;
  font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
  font-size: 11px;
}

/* Container */
.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

/* Summary Cards */
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}

.summary-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  text-align: center;
}

.summary-card .label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.summary-card .value {
  font-size: 28px;
  font-weight: 700;
  font-family: 'SF Mono', 'Cascadia Code', monospace;
}

.summary-card .value.green { color: var(--accent-green); }
.summary-card .value.red { color: var(--accent-red); }
.summary-card .value.blue { color: var(--accent-blue); }
.summary-card .value.orange { color: var(--accent-orange); }
.summary-card .value.purple { color: var(--accent-purple); }

/* Search */
.search-bar {
  margin-bottom: 20px;
}

.search-bar input {
  width: 100%;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 16px;
  color: var(--text-primary);
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}

.search-bar input:focus {
  border-color: var(--accent-blue);
}

.search-bar input::placeholder {
  color: var(--text-muted);
}

/* Waterfall Timeline */
.waterfall-section {
  margin-bottom: 24px;
}

.section-title {
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  margin-bottom: 12px;
  font-weight: 600;
}

.waterfall {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.waterfall-row {
  display: grid;
  grid-template-columns: 200px 1fr 80px;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.15s;
  gap: 12px;
}

.waterfall-row:last-child { border-bottom: none; }
.waterfall-row:hover { background: var(--bg-hover); }

.wf-label {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: flex;
  align-items: center;
  gap: 6px;
}

.wf-status {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.wf-status.success { background: var(--accent-green); }
.wf-status.error { background: var(--accent-red); }

.wf-bar-container {
  height: 22px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
  display: flex;
  align-items: center;
  position: relative;
}

.wf-bar {
  height: 100%;
  display: flex;
  align-items: center;
  gap: 1px;
  padding: 0 2px;
}

.wf-segment {
  height: 16px;
  border-radius: 2px;
  min-width: 3px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  color: rgba(255,255,255,0.9);
  font-weight: 600;
  padding: 0 3px;
  white-space: nowrap;
  overflow: hidden;
}

.wf-segment.llm_call { background: var(--span-llm); }
.wf-segment.tool_call { background: var(--span-tool); }
.wf-segment.skill { background: var(--span-skill); }
.wf-segment.agent { background: var(--span-agent); }
.wf-segment.file { background: var(--span-file); }

.wf-duration {
  font-size: 12px;
  color: var(--text-secondary);
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  text-align: right;
}

/* Question Detail Cards */
.question-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.question-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.question-header {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.15s;
  gap: 12px;
}

.question-header:hover { background: var(--bg-hover); }

.question-header .chevron {
  color: var(--text-muted);
  transition: transform 0.2s;
  font-size: 12px;
  flex-shrink: 0;
}

.question-card.expanded .chevron { transform: rotate(90deg); }

.question-header .qid {
  font-weight: 600;
  font-size: 14px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.question-header .meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.status-badge {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.status-badge.success {
  background: rgba(63, 185, 80, 0.15);
  color: var(--accent-green);
}

.status-badge.error {
  background: rgba(248, 81, 73, 0.15);
  color: var(--accent-red);
}

.token-badge {
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  color: var(--accent-purple);
}

.duration-badge {
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  color: var(--text-secondary);
}

/* Question Body */
.question-body {
  display: none;
  border-top: 1px solid var(--border);
}

.question-card.expanded .question-body { display: block; }

/* Span list */
.span-list {
  padding: 0;
}

.span-item {
  border-bottom: 1px solid var(--border);
}

.span-item:last-child { border-bottom: none; }

.span-header {
  display: flex;
  align-items: center;
  padding: 10px 16px 10px 32px;
  cursor: pointer;
  transition: background 0.15s;
  gap: 10px;
}

.span-header:hover { background: var(--bg-hover); }

.span-icon {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  color: white;
  flex-shrink: 0;
}

.span-icon.llm_call { background: var(--span-llm); }
.span-icon.tool_call { background: var(--span-tool); }
.span-icon.skill { background: var(--span-skill); }
.span-icon.agent { background: var(--span-agent); }
.span-icon.file { background: var(--span-file); }

.span-type {
  font-size: 12px;
  font-weight: 600;
  min-width: 80px;
}

.span-name {
  font-size: 13px;
  color: var(--text-secondary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: 'SF Mono', 'Cascadia Code', monospace;
}

.span-duration {
  font-size: 12px;
  color: var(--text-muted);
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  flex-shrink: 0;
}

.span-tokens {
  font-size: 11px;
  color: var(--accent-purple);
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  flex-shrink: 0;
}

/* Span Detail */
.span-detail {
  display: none;
  padding: 12px 16px 12px 64px;
  background: var(--bg-primary);
  border-top: 1px solid var(--border);
}

.span-item.expanded .span-detail { display: block; }

.detail-section {
  margin-bottom: 12px;
}

.detail-section:last-child { margin-bottom: 0; }

.detail-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  margin-bottom: 4px;
  font-weight: 600;
}

.detail-content {
  font-size: 13px;
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  color: var(--text-secondary);
  background: var(--bg-secondary);
  border-radius: 4px;
  padding: 8px 12px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid var(--border);
}

.detail-content.error { color: var(--accent-red); }

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
}

.detail-kv {
  font-size: 12px;
}

.detail-kv .k {
  color: var(--text-muted);
  margin-right: 4px;
}

.detail-kv .v {
  color: var(--text-primary);
  font-family: 'SF Mono', 'Cascadia Code', monospace;
}

/* Tool call list in LLM span */
.tool-call-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tool-call-item {
  font-size: 12px;
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  color: var(--accent-cyan);
  padding: 4px 8px;
  background: rgba(57, 210, 192, 0.08);
  border-radius: 4px;
  border-left: 2px solid var(--accent-cyan);
}

/* Answer section */
.answer-section {
  padding: 16px;
  background: var(--bg-primary);
  border-top: 1px solid var(--border);
}

.answer-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
  margin-bottom: 6px;
  font-weight: 600;
}

.answer-content {
  font-size: 14px;
  color: var(--accent-green);
  background: rgba(63, 185, 80, 0.06);
  border: 1px solid rgba(63, 185, 80, 0.2);
  border-radius: var(--radius);
  padding: 12px 16px;
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  white-space: pre-wrap;
  word-break: break-all;
}

.answer-content.error {
  color: var(--accent-red);
  background: rgba(248, 81, 73, 0.06);
  border-color: rgba(248, 81, 73, 0.2);
}

/* Token bar */
.token-bar {
  display: flex;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  margin-top: 4px;
  background: var(--bg-tertiary);
}

.token-bar .prompt {
  background: var(--accent-blue);
  transition: width 0.3s;
}

.token-bar .completion {
  background: var(--accent-purple);
  transition: width 0.3s;
}

/* Legend */
.legend {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

/* Empty state */
.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-muted);
}

.empty-state .icon { font-size: 48px; margin-bottom: 12px; }
.empty-state .msg { font-size: 14px; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--bg-hover); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

/* Responsive */
@media (max-width: 768px) {
  .container { padding: 12px; }
  .summary-grid { grid-template-columns: repeat(3, 1fr); }
  .waterfall-row { grid-template-columns: 120px 1fr 60px; }
  .question-header .meta { gap: 8px; }
}

/* Capabilities Section */
.capabilities-section {
  margin-top: 24px;
}

.capabilities-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
}

.capability-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.capability-header {
  padding: 12px 16px;
  background: var(--bg-tertiary);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: background 0.15s;
}

.capability-header:hover {
  background: var(--bg-hover);
}

.capability-icon {
  font-size: 16px;
}

.capability-title {
  font-size: 13px;
  font-weight: 600;
  flex: 1;
}

.capability-count {
  font-size: 11px;
  color: var(--text-muted);
  font-family: 'SF Mono', monospace;
}

.capability-body {
  padding: 12px 16px;
  max-height: 400px;
  overflow-y: auto;
}

.capability-item {
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}

.capability-item:last-child {
  border-bottom: none;
}

.capability-item-name {
  font-size: 13px;
  font-weight: 600;
  font-family: 'SF Mono', monospace;
  color: var(--accent-cyan);
  margin-bottom: 4px;
}

.capability-item-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.system-prompt-content {
  font-size: 12px;
  font-family: 'SF Mono', monospace;
  color: var(--text-secondary);
  background: var(--bg-primary);
  padding: 12px;
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid var(--border);
  line-height: 1.6;
}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <div class="header-logo">&#x1f916; Agent Contest</div>
    <div class="header-title" id="header-info">Dashboard</div>
  </div>
  <div class="header-right">
    <span class="header-badge" id="header-model">-</span>
    <span class="header-badge" id="header-time">-</span>
    <span class="header-badge" id="header-runid">-</span>
  </div>
</div>

<div class="container">
  <!-- Summary Cards -->
  <div class="summary-grid" id="summary-grid"></div>

  <!-- Search -->
  <div class="search-bar">
    <input type="text" id="search-input" placeholder="&#x1f50d; Search questions, tools, spans..." />
  </div>

  <!-- Legend -->
  <div class="legend">
    <div class="legend-item"><div class="legend-dot" style="background:var(--span-llm)"></div> LLM Call</div>
    <div class="legend-item"><div class="legend-dot" style="background:var(--span-tool)"></div> Tool</div>
    <div class="legend-item"><div class="legend-dot" style="background:var(--span-skill)"></div> Skill</div>
    <div class="legend-item"><div class="legend-dot" style="background:var(--span-agent)"></div> Agent</div>
    <div class="legend-item"><div class="legend-dot" style="background:var(--span-file)"></div> File</div>
    <div class="legend-item"><div class="legend-dot" style="background:var(--span-error)"></div> Error</div>
  </div>

  <!-- Waterfall -->
  <div class="waterfall-section">
    <div class="section-title">Timeline</div>
    <div class="waterfall" id="waterfall"></div>
  </div>

  <!-- Question Details -->
  <div class="section-title">Questions</div>
  <div class="question-list" id="question-list"></div>

  <!-- Agent Capabilities -->
  <div class="capabilities-section">
    <div class="section-title">Agent Capabilities</div>
    <div class="capabilities-grid" id="capabilities-grid"></div>
  </div>
</div>

<script>
// ============================================================
// Data — injected at generation time
// ============================================================
const TRACES = /*__TRACES_DATA__*/null/*/__TRACES_DATA__*/;

// ============================================================
// Render
// ============================================================
function fmt(ms) {
  if (ms < 1000) return ms + 'ms';
  return (ms / 1000).toFixed(1) + 's';
}

function fmtNum(n) {
  return n.toLocaleString();
}

function escapeHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function spanTypeLabel(type, data) {
  if (type === 'llm_call') {
    // Show tool call count if LLM requested tools
    const tc = data?.tool_calls?.length || 0;
    return tc > 0 ? `AI→${tc}` : 'AI';
  }
  const tt = data?.tool_type || 'tool';
  const map = { skill: 'SK', agent: 'AG', file: 'FL', tool: 'TL' };
  return map[tt] || 'TL';
}

function spanTypeClass(type, data) {
  if (type === 'llm_call') return 'llm_call';
  return data?.tool_type || 'tool_call';
}

function spanIcon(type, data) {
  if (type === 'llm_call') return 'AI';
  const tt = data?.tool_type;
  if (tt === 'skill') return 'SK';
  if (tt === 'agent') return 'AG';
  if (tt === 'file') return 'FL';
  return 'TL';
}

function spanName(type, data) {
  if (type === 'llm_call') {
    const model = data?.model || '';
    const tc = data?.tool_calls?.length || 0;
    return model + (tc > 0 ? ' → ' + data.tool_calls.map(c => c.name).join(', ') : ' → answer');
  }
  return data?.tool_name || '';
}

function renderSummary(data) {
  const qs = data.questions || [];
  const total = qs.length;
  const pass = qs.filter(q => q.status === 'success').length;
  const fail = total - pass;
  const totalTokens = qs.reduce((s, q) => s + (q.tokens?.prompt || 0) + (q.tokens?.completion || 0), 0);
  const totalMs = data.total_duration_ms || qs.reduce((s, q) => s + (q.duration_ms || 0), 0);
  const totalSpans = qs.reduce((s, q) => s + (q.spans?.length || 0), 0);

  const grid = document.getElementById('summary-grid');
  grid.innerHTML = `
    <div class="summary-card"><div class="label">Questions</div><div class="value blue">${total}</div></div>
    <div class="summary-card"><div class="label">Passed</div><div class="value green">${pass}</div></div>
    <div class="summary-card"><div class="label">Failed</div><div class="value red">${fail}</div></div>
    <div class="summary-card"><div class="label">Total Spans</div><div class="value purple">${totalSpans}</div></div>
    <div class="summary-card"><div class="label">Tokens</div><div class="value orange">${fmtNum(totalTokens)}</div></div>
    <div class="summary-card"><div class="label">Duration</div><div class="value blue">${fmt(totalMs)}</div></div>
  `;
}

function renderWaterfall(data) {
  const qs = data.questions || [];
  const maxDur = Math.max(...qs.map(q => q.duration_ms || 0), 1);
  const el = document.getElementById('waterfall');

  if (qs.length === 0) {
    el.innerHTML = '<div class="empty-state"><div class="icon">&#x1f4ed;</div><div class="msg">No questions in trace</div></div>';
    return;
  }

  el.innerHTML = qs.map((q, i) => {
    const dur = q.duration_ms || 0;
    const spans = q.spans || [];
    const segments = spans.map(s => {
      const cls = spanTypeClass(s.type, s.data);
      const label = spanTypeLabel(s.type, s.data);
      const w = Math.max((s.duration_ms / maxDur) * 100, 0.5);
      const toolName = s.data?.tool_name || '';
      const displayName = w > 8 ? label : '';
      const tooltip = `${toolName || s.type} - ${s.duration_ms}ms`;
      return `<div class="wf-segment ${cls}" style="width:${w}%" title="${escapeHtml(tooltip)}">${displayName}</div>`;
    }).join('');

    return `
      <div class="waterfall-row" data-qid="${escapeHtml(q.id)}" onclick="scrollToQuestion('${escapeHtml(q.id)}')">
        <div class="wf-label">
          <span class="wf-status ${q.status}"></span>
          ${escapeHtml(q.id)}
        </div>
        <div class="wf-bar-container">
          <div class="wf-bar">${segments}</div>
        </div>
        <div class="wf-duration">${fmt(dur)}</div>
      </div>
    `;
  }).join('');
}

function renderQuestions(data) {
  const qs = data.questions || [];
  const el = document.getElementById('question-list');

  if (qs.length === 0) {
    el.innerHTML = '<div class="empty-state"><div class="icon">&#x1f4ed;</div><div class="msg">No questions in trace</div></div>';
    return;
  }

  el.innerHTML = qs.map((q, i) => {
    const spans = q.spans || [];
    const promptT = q.tokens?.prompt || 0;
    const compT = q.tokens?.completion || 0;
    const totalT = promptT + compT;
    const promptPct = totalT > 0 ? (promptT / totalT * 100).toFixed(0) : 0;
    const compPct = totalT > 0 ? (compT / totalT * 100).toFixed(0) : 0;

    const spanHtml = spans.map((s, si) => {
      const cls = spanTypeClass(s.type, s.data);
      const icon = spanIcon(s.type, s.data);
      const label = spanTypeLabel(s.type, s.data);
      const name = spanName(s.type, s.data);
      const usage = s.data?.usage;
      const tokStr = usage ? `${usage.prompt_tokens || 0}+${usage.completion_tokens || 0}` : '';

      let detailHtml = '';

      if (s.type === 'llm_call') {
        const d = s.data || {};
        detailHtml = `
          <div class="detail-grid">
            <div class="detail-kv"><span class="k">Model:</span><span class="v">${escapeHtml(d.model)}</span></div>
            <div class="detail-kv"><span class="k">Messages:</span><span class="v">${d.messages_count}</span></div>
            <div class="detail-kv"><span class="k">Tools:</span><span class="v">${d.tools_count}</span></div>
            <div class="detail-kv"><span class="k">Finish:</span><span class="v">${escapeHtml(d.finish_reason || '-')}</span></div>
          </div>
          ${d.output_preview ? `<div class="detail-section" style="margin-top:8px"><div class="detail-label">Output Preview</div><div class="detail-content">${escapeHtml(d.output_preview)}</div></div>` : ''}
          ${(d.tool_calls?.length) ? `<div class="detail-section" style="margin-top:8px"><div class="detail-label">Tool Calls Requested</div><div class="tool-call-list">${d.tool_calls.map(tc => `<div class="tool-call-item">→ ${escapeHtml(tc.name)}(${escapeHtml(tc.arguments?.slice(0, 120) || '')})</div>`).join('')}</div></div>` : ''}
          ${usage ? `<div class="detail-section" style="margin-top:8px"><div class="detail-grid"><div class="detail-kv"><span class="k">Prompt:</span><span class="v">${fmtNum(usage.prompt_tokens || 0)}</span></div><div class="detail-kv"><span class="k">Completion:</span><span class="v">${fmtNum(usage.completion_tokens || 0)}</span></div></div></div>` : ''}
        `;
      } else {
        const d = s.data || {};
        detailHtml = `
          <div class="detail-section"><div class="detail-label">Arguments</div><div class="detail-content">${escapeHtml(JSON.stringify(d.arguments, null, 2))}</div></div>
          ${d.error ? `<div class="detail-section"><div class="detail-label">Error</div><div class="detail-content error">${escapeHtml(d.error)}</div></div>` : ''}
          <div class="detail-section"><div class="detail-label">Result</div><div class="detail-content">${escapeHtml(d.result || '(empty)')}</div></div>
        `;
      }

      return `
        <div class="span-item" id="span-${i}-${si}">
          <div class="span-header" onclick="this.parentElement.classList.toggle('expanded')">
            <div class="span-icon ${cls}">${icon}</div>
            <div class="span-type">${label}</div>
            <div class="span-name">${escapeHtml(name)}</div>
            ${tokStr ? `<div class="span-tokens">${tokStr} tok</div>` : ''}
            <div class="span-duration">${fmt(s.duration_ms)}</div>
          </div>
          <div class="span-detail">${detailHtml}</div>
        </div>
      `;
    }).join('');

    const isError = q.status === 'error';

    return `
      <div class="question-card" id="q-${escapeHtml(q.id)}" data-search="${escapeHtml(q.id)} ${spans.map(s => escapeHtml(s.data?.tool_name || '')).join(' ')}">
        <div class="question-header" onclick="this.parentElement.classList.toggle('expanded')">
          <span class="chevron">▶</span>
          <span class="qid">Q${i + 1}: ${escapeHtml(q.id)}</span>
          <div class="meta">
            <span class="status-badge ${q.status}">${q.status}</span>
            <span class="duration-badge">${fmt(q.duration_ms)}</span>
            ${totalT > 0 ? `<span class="token-badge">${fmtNum(totalT)} tok</span>` : ''}
          </div>
        </div>
        <div class="question-body">
          <div class="span-list">${spanHtml}</div>
          ${totalT > 0 ? `
          <div style="padding:8px 16px 4px 32px">
            <div style="font-size:11px;color:var(--text-muted);margin-bottom:2px">Token Distribution: ${fmtNum(promptT)} prompt (${promptPct}%) + ${fmtNum(compT)} completion (${compPct}%)</div>
            <div class="token-bar"><div class="prompt" style="width:${promptPct}%"></div><div class="completion" style="width:${compPct}%"></div></div>
          </div>` : ''}
          <div class="answer-section">
            <div class="answer-label">Final Answer</div>
            <div class="answer-content ${isError ? 'error' : ''}">${escapeHtml(isError ? (q.error || 'Unknown error') : (q.answer || '(empty)'))}</div>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function scrollToQuestion(qid) {
  const el = document.getElementById('q-' + qid);
  if (el) {
    el.classList.add('expanded');
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

// Search
function initSearch() {
  const input = document.getElementById('search-input');
  input.addEventListener('input', () => {
    const q = input.value.toLowerCase().trim();
    document.querySelectorAll('.question-card').forEach(card => {
      const text = card.getAttribute('data-search') || '';
      card.style.display = (!q || text.toLowerCase().includes(q)) ? '' : 'none';
    });
  });
}

// Header
function renderHeader(data) {
  document.getElementById('header-model').textContent = data.model || 'unknown';
  document.getElementById('header-runid').textContent = data.run_id || '';
  if (data.start_time) {
    try {
      const d = new Date(data.start_time);
      document.getElementById('header-time').textContent = d.toLocaleString();
    } catch { document.getElementById('header-time').textContent = data.start_time; }
  }
  document.getElementById('header-info').textContent = `${(data.questions||[]).length} questions · ${fmt(data.total_duration_ms || 0)}`;
}

// Main
function render(data) {
  if (!data) {
    document.querySelector('.container').innerHTML = '<div class="empty-state"><div class="icon">⚠️</div><div class="msg">No trace data found</div></div>';
    return;
  }
  renderHeader(data);
  renderSummary(data);
  renderWaterfall(data);
  renderQuestions(data);
  renderCapabilities(data);
  initSearch();
}

function renderCapabilities(data) {
  const caps = data.capabilities || {};
  const grid = document.getElementById('capabilities-grid');
  if (!grid) return;

  const html = [];

  // System Prompt
  if (caps.system_prompt) {
    html.push(`
      <div class="capability-card" style="grid-column: 1 / -1;">
        <div class="capability-header" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'block' : 'none'">
          <span class="capability-icon">📝</span>
          <span class="capability-title">System Prompt</span>
          <span class="capability-count">${caps.system_prompt.length} chars</span>
        </div>
        <div class="capability-body">
          <div class="system-prompt-content">${escapeHtml(caps.system_prompt)}</div>
        </div>
      </div>
    `);
  }

  // Tools
  if (caps.tools && caps.tools.length > 0) {
    const toolsHtml = caps.tools.map(t => `
      <div class="capability-item">
        <div class="capability-item-name">${escapeHtml(t.name)}</div>
        <div class="capability-item-desc">${escapeHtml(t.description)}</div>
      </div>
    `).join('');
    html.push(`
      <div class="capability-card">
        <div class="capability-header">
          <span class="capability-icon">🔧</span>
          <span class="capability-title">MCP Tools</span>
          <span class="capability-count">${caps.tools.length}</span>
        </div>
        <div class="capability-body">${toolsHtml}</div>
      </div>
    `);
  }

  // Skills
  if (caps.skills && caps.skills.length > 0) {
    const skillsHtml = caps.skills.map(s => `
      <div class="capability-item">
        <div class="capability-item-name">${escapeHtml(s.name)}</div>
        <div class="capability-item-desc">${escapeHtml(s.description || 'No description')}</div>
      </div>
    `).join('');
    html.push(`
      <div class="capability-card">
        <div class="capability-header">
          <span class="capability-icon">📦</span>
          <span class="capability-title">Skills</span>
          <span class="capability-count">${caps.skills.length}</span>
        </div>
        <div class="capability-body">${skillsHtml}</div>
      </div>
    `);
  }

  // Sub-agents
  if (caps.sub_agents && caps.sub_agents.length > 0) {
    const agentsHtml = caps.sub_agents.map(a => `
      <div class="capability-item">
        <div class="capability-item-name">${escapeHtml(a.name)}</div>
        <div class="capability-item-desc">${escapeHtml(a.description || 'No description')}</div>
      </div>
    `).join('');
    html.push(`
      <div class="capability-card">
        <div class="capability-header">
          <span class="capability-icon">🤖</span>
          <span class="capability-title">Sub-Agents</span>
          <span class="capability-count">${caps.sub_agents.length}</span>
        </div>
        <div class="capability-body">${agentsHtml}</div>
      </div>
    `);
  }

  // Config
  if (caps.config && Object.keys(caps.config).length > 0) {
    const configHtml = Object.entries(caps.config).map(([k, v]) => `
      <div class="capability-item">
        <div class="capability-item-name">${escapeHtml(k)}</div>
        <div class="capability-item-desc">${escapeHtml(v)}</div>
      </div>
    `).join('');
    html.push(`
      <div class="capability-card">
        <div class="capability-header">
          <span class="capability-icon">⚙️</span>
          <span class="capability-title">Configuration</span>
          <span class="capability-count">${Object.keys(caps.config).length}</span>
        </div>
        <div class="capability-body">${configHtml}</div>
      </div>
    `);
  }

  grid.innerHTML = html.join('') || '<div class="empty-state"><div class="msg">No capabilities data</div></div>';
}

render(TRACES);
</script>
</body>
</html>"""


def generate_dashboard(
    traces_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    """Read traces.json and produce a self-contained dashboard.html."""
    traces_path = Path(traces_path)
    if output_path is None:
        output_path = traces_path.with_name("dashboard.html")
    output_path = Path(output_path)

    traces_data = json.loads(traces_path.read_text(encoding="utf-8"))

    # Collect capabilities from project structure
    # traces.json is in source/outputs/, project root is 3 levels up
    project_root = traces_path.resolve().parent.parent.parent
    capabilities = collect_capabilities(project_root)

    # Merge capabilities into traces data
    traces_data["capabilities"] = capabilities

    traces_json = json.dumps(traces_data, ensure_ascii=False)

    html = _DASHBOARD_TEMPLATE.replace(
        "/*__TRACES_DATA__*/null/*/__TRACES_DATA__*/",
        traces_json,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m source.runtime.generate_dashboard <traces.json> [dashboard.html]")
        sys.exit(1)
    traces_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    result = generate_dashboard(traces_path, output_path)
    print(f"dashboard generated: {result}")


if __name__ == "__main__":
    main()
