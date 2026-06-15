from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


_NOISE_WORDS = {
    "background",
    "diagnostic",
    "precheck",
    "pre-check",
    "replay",
    "static",
    "后台",
    "回放",
    "诊断",
    "预校验",
    "静态资源",
}
_FAILURE_WORDS = {"error", "fail", "failed", "failure", "异常", "失败"}
_MODULE_KEYS = ("module", "pagegroup", "pagemodule", "businessmodule")
_CODE_KEYS = ("validationcode", "code")


def analyze_evidence_chain(
    *,
    frontend_paths: list[str] | None = None,
    backend_paths: list[str] | None = None,
    har_paths: list[str] | None = None,
    schema_path: str,
    screenshot_paths: list[str] | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    events: list[dict[str, Any]] = []
    for role, paths in (
        ("frontend", frontend_paths or []),
        ("backend", backend_paths or []),
        ("network", har_paths or []),
        ("screenshot", screenshot_paths or []),
    ):
        for path in paths:
            parsed, parse_warnings = _load_events(Path(path), role)
            events.extend(parsed)
            warnings.extend(parse_warnings)

    try:
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"error": f"Could not read schema: {exc}", "warnings": warnings}
    if not isinstance(schema, dict):
        return {"error": "Schema must be a JSON object.", "warnings": warnings}
    if not events:
        return {"error": "No evidence events could be parsed.", "warnings": warnings}

    components = _connected_components(events)
    candidates = [_summarize_component(component, schema) for component in components]
    candidates.sort(
        key=lambda item: (
            -item["score"],
            item.get("endpoint", ""),
            json.dumps(item.get("correlation_values", []), ensure_ascii=False),
        )
    )
    if not candidates:
        return {"error": "No candidate flow could be constructed.", "warnings": warnings}

    highest_score = candidates[0]["score"]
    top = [candidate for candidate in candidates if candidate["score"] == highest_score]
    rejected = candidates[len(top):]
    if len(top) != 1:
        return {
            "ambiguous": True,
            "candidates": [_public_candidate(item) for item in top],
            "rejected_candidates": [_public_candidate(item) for item in rejected],
            "warnings": warnings,
        }

    selected = top[0]
    return {
        "ambiguous": False,
        "selected_flow": _public_candidate(selected),
        "evidence": selected["evidence"],
        "rejected_candidates": [_public_candidate(item) for item in rejected],
        "warnings": warnings,
    }


def _load_events(path: Path, role: str) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    if not path.exists():
        return [], [f"File not found: {path}"]
    if role == "screenshot":
        return [
            _make_event(
                {"screenshotFile": path.name, "visibleFailure": True},
                role=role,
                source=f"{path}:1",
            )
        ], warnings

    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception as exc:
        return [], [f"Could not read {path}: {exc}"]

    if role == "network":
        try:
            payload = json.loads(text)
            entries = payload.get("log", {}).get("entries", [])
            if isinstance(entries, list):
                return [
                    _make_event(
                        _normalize_har_entry(entry),
                        role=role,
                        source=f"{path}:{index + 1}",
                    )
                    for index, entry in enumerate(entries)
                    if isinstance(entry, dict)
                ], warnings
        except json.JSONDecodeError:
            warnings.append(f"Invalid HAR JSON, falling back to line parsing: {path}")

    records: list[Any] = []
    try:
        payload = json.loads(text)
        if isinstance(payload, list):
            records.extend(payload)
        elif isinstance(payload, dict):
            records.append(payload)
    except json.JSONDecodeError:
        for line_number, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                record = _parse_key_value_line(line)
                if record:
                    records.append(record)
                else:
                    warnings.append(f"Skipped unparseable line {path}:{line_number}")

    events = [
        _make_event(record, role=role, source=f"{path}:{index + 1}")
        for index, record in enumerate(records)
        if isinstance(record, (dict, list))
    ]
    return events, warnings


def _normalize_har_entry(entry: dict[str, Any]) -> dict[str, Any]:
    request = entry.get("request") if isinstance(entry.get("request"), dict) else {}
    response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
    normalized: dict[str, Any] = {
        "timestamp": entry.get("startedDateTime"),
        "method": request.get("method"),
        "url": request.get("url"),
        "status": response.get("status"),
    }
    for headers in (request.get("headers"), response.get("headers")):
        if not isinstance(headers, list):
            continue
        for header in headers:
            if isinstance(header, dict) and header.get("name"):
                normalized[str(header["name"])] = header.get("value")
    for container in (request.get("postData"), response.get("content")):
        if not isinstance(container, dict):
            continue
        text = container.get("text")
        if not isinstance(text, str):
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            normalized.update(parsed)
    return normalized


def _parse_key_value_line(line: str) -> dict[str, Any]:
    pairs = re.findall(
        r"([A-Za-z_][\w.-]*)\s*[=:]\s*(\"[^\"]*\"|'[^']*'|[^\s,;]+)",
        line,
    )
    return {
        key: value.strip("\"'")
        for key, value in pairs
    }


def _make_event(record: Any, *, role: str, source: str) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    _flatten(record, flat)
    text = json.dumps(record, ensure_ascii=False).lower()
    identifiers: dict[str, str] = {}
    for key, value in flat.items():
        canonical = _canonical_key(key)
        if canonical.startswith("x") and _is_identifier_key(canonical[1:]):
            canonical = canonical[1:]
        if _is_identifier_key(canonical) and _is_scalar(value) and str(value).strip():
            identifiers[canonical] = str(value).strip()

    url = _exact_value(
        flat,
        ("url", "requesturl", "requestpath", "path", "endpoint", "interface"),
    )
    endpoint = ""
    if url:
        parsed = urlparse(str(url))
        endpoint = parsed.path if parsed.scheme else str(url).split("?", 1)[0]
    status = _as_int(_first_value(flat, ("status", "statuscode", "httpstatus")))
    noise = any(word in text for word in _NOISE_WORDS)
    failure = (
        status is not None and status >= 400
        or any(word in text for word in _FAILURE_WORDS)
    )
    page = any(
        token in _canonical_key(key)
        for key in flat
        for token in ("page", "screen", "display")
    )
    manual = role == "frontend" and any(
        token in text for token in ("manual", "submit", "click", "人工", "提交", "点击")
    )
    return {
        "role": role,
        "source": source,
        "flat": {_canonical_key(key): value for key, value in flat.items()},
        "identifiers": identifiers,
        "endpoint": endpoint,
        "status": status,
        "noise": noise,
        "failure": failure,
        "page": page or role == "screenshot",
        "manual": manual,
    }


def _flatten(value: Any, output: dict[str, Any], prefix: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            _flatten(child, output, child_prefix)
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _flatten(child, output, f"{prefix}.{index}" if prefix else str(index))
        return
    if prefix:
        output[prefix] = value


def _connected_components(events: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    parents = list(range(len(events)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    values_to_indexes: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, event in enumerate(events):
        for key, value in event["identifiers"].items():
            values_to_indexes[(key, value)].append(index)
    for indexes in values_to_indexes.values():
        for index in indexes[1:]:
            union(indexes[0], index)

    components: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, event in enumerate(events):
        components[find(index)].append(event)
    return list(components.values())


def _summarize_component(
    events: list[dict[str, Any]],
    schema: dict[str, Any],
) -> dict[str, Any]:
    roles = {event["role"] for event in events}
    has_page = any(event["page"] for event in events)
    has_manual = any(event["manual"] for event in events)
    has_failure = any(event["failure"] for event in events)
    noise_count = sum(1 for event in events if event["noise"])
    correlation_values = sorted(
        {
            value
            for event in events
            for value in event["identifiers"].values()
        }
    )
    score = (
        10 * len(roles & {"frontend", "network", "backend", "screenshot"})
        + 6 * int(has_page)
        + 6 * int(has_manual)
        + 6 * int(has_failure)
        + min(len(correlation_values), 5)
        - 12 * noise_count
    )
    module = _component_value(events, _MODULE_KEYS)
    endpoint = next(
        (event["endpoint"] for event in events if event["endpoint"]),
        "",
    )
    root_causes = _map_root_causes(events, schema, module)
    return {
        "score": score,
        "module": module,
        "endpoint": endpoint,
        "root_causes": root_causes,
        "event_count": len(events),
        "correlation_values": correlation_values,
        "evidence": [
            {
                "role": event["role"],
                "source": event["source"],
                "endpoint": event["endpoint"],
                "identifiers": event["identifiers"],
                "noise": event["noise"],
            }
            for event in events
        ],
    }


def _map_root_causes(
    events: list[dict[str, Any]],
    schema: dict[str, Any],
    module: str,
) -> list[str]:
    backend_events = [
        event for event in events
        if event["role"] == "backend" and not event["noise"]
    ]
    effective_rule = schema.get("effectiveValidationRule")
    if isinstance(effective_rule, dict):
        backend_events = [
            event
            for event in backend_events
            if _matches_rule(event["flat"], effective_rule, module)
        ]

    causes: list[str] = []
    rules = schema.get("rootCauseRules")
    if isinstance(rules, list):
        for event in backend_events:
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                cause = rule.get("rootCause")
                conditions = {
                    key: value
                    for key, value in rule.items()
                    if key not in {"rootCause", "description", "name"}
                }
                if cause and _matches_rule(event["flat"], conditions, module):
                    _append_unique(causes, str(cause))
        return causes

    code_map = schema.get("validationCodeMap")
    if isinstance(code_map, dict):
        for event in backend_events:
            code = _first_value(event["flat"], _CODE_KEYS)
            if code is not None and str(code) in code_map:
                _append_unique(causes, str(code_map[str(code)]))
    return causes


def _matches_rule(flat: dict[str, Any], rule: dict[str, Any], module: str) -> bool:
    for raw_key, expected in rule.items():
        key = _canonical_key(raw_key)
        if key in {"all", "conditions", "required"} and isinstance(expected, dict):
            if not _matches_rule(flat, expected, module):
                return False
            continue
        actual = module if key == "module" else _first_value(flat, (key,))
        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected and str(actual) != str(expected):
            return False
    return True


def _public_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "module": candidate["module"],
        "endpoint": candidate["endpoint"],
        "root_causes": candidate["root_causes"],
        "event_count": candidate["event_count"],
        "correlation_values": candidate["correlation_values"],
        "score": candidate["score"],
    }


def _component_value(events: list[dict[str, Any]], keys: tuple[str, ...]) -> str:
    for event in events:
        value = _first_value(event["flat"], keys)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _first_value(flat: dict[str, Any], keys: tuple[str, ...]) -> Any:
    canonical = {_canonical_key(key): value for key, value in flat.items()}
    for key in keys:
        normalized = _canonical_key(key)
        if normalized in canonical:
            return canonical[normalized]
        for candidate_key, value in canonical.items():
            if candidate_key.endswith(normalized):
                return value
    return None


def _exact_value(flat: dict[str, Any], keys: tuple[str, ...]) -> Any:
    canonical = {_canonical_key(key): value for key, value in flat.items()}
    for key in keys:
        normalized = _canonical_key(key)
        if normalized in canonical:
            return canonical[normalized]
    return None


def _canonical_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _is_identifier_key(key: str) -> bool:
    if key in {"validationcode", "userid", "fieldid", "schemaid"}:
        return False
    return (
        key.endswith("id")
        or key.endswith("ref")
        or any(token in key for token in ("workflow", "action", "request", "trace"))
    )


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
