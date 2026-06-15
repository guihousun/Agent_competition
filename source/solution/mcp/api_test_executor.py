from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


_VARIABLE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def execute_api_test_plan(
    *,
    plan: dict[str, Any],
    package_id: str,
    auth_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors = _validate_plan(plan)
    if errors:
        return {"error": "invalid plan", "details": errors}

    base_url = str(plan["base_url"]).rstrip("/")
    package_header = str(plan.get("package_header") or "X-Package-Id")
    timeout = max(1, min(int(plan.get("timeout", 30)), 120))
    variables = {
        str(key): value
        for key, value in (plan.get("variables") or {}).items()
    }
    cached_access_token: str | None = None
    single_use_token = _single_use_token(auth_config)
    case_results: list[dict[str, Any]] = []

    for case in plan["cases"]:
        assertion_errors: list[str] = []
        step_results: list[dict[str, Any]] = []
        auth_requests = 0
        for step_index, raw_step in enumerate(case["steps"]):
            step = _substitute(raw_step, variables)
            if (
                _requires_auth(step, auth_config)
                and not _has_authorization_header(step)
            ):
                if cached_access_token is None or single_use_token:
                    token_result = _fetch_access_token(
                        base_url=base_url,
                        package_header=package_header,
                        package_id=package_id,
                        auth_config=auth_config or {},
                        timeout=timeout,
                    )
                    auth_requests += 1
                    if token_result.get("error"):
                        assertion_errors.append(
                            f"step {step_index}: automatic authentication failed: "
                            f"{token_result['error']}"
                        )
                        break
                    cached_access_token = str(token_result["access_token"])
                step = _with_authorization(
                    step,
                    auth_config or {},
                    cached_access_token,
                )
            response = _request(
                base_url=base_url,
                package_header=package_header,
                package_id=package_id,
                step=step,
                timeout=timeout,
            )
            step_results.append(response)
            if response.get("request_error"):
                assertion_errors.append(
                    f"step {step_index}: request failed: {response['request_error']}"
                )
                break
            if _requires_auth(step, auth_config) and single_use_token:
                cached_access_token = None
            extract = raw_step.get("extract") or {}
            if isinstance(extract, dict):
                for variable_name, path in extract.items():
                    found, value = _json_path(response.get("json"), str(path))
                    if found:
                        variables[str(variable_name)] = value
                    else:
                        assertion_errors.append(
                            f"step {step_index}: extraction path not found: {path}"
                        )
            step_assertion = raw_step.get("assert")
            if isinstance(step_assertion, dict):
                assertion_errors.extend(
                    f"step {step_index}: {message}"
                    for message in _assert_response(response, step_assertion)
                )

        case_assertion = case.get("assert")
        if isinstance(case_assertion, dict):
            assertion_index = int(case.get("assert_step", -1))
            if step_results:
                try:
                    assertion_response = step_results[assertion_index]
                except IndexError:
                    assertion_errors.append(
                        f"assert_step is outside executed steps: {assertion_index}"
                    )
                else:
                    assertion_errors.extend(
                        _assert_response(assertion_response, case_assertion)
                    )
            else:
                assertion_errors.append("no response available for assertion")

        case_results.append(
            {
                "id": str(case["id"]),
                "passed": not assertion_errors,
                "assertion_errors": assertion_errors,
                "steps_executed": len(step_results),
                "auth_requests": auth_requests,
                "responses": [
                    {
                        "status": result.get("status"),
                        "json": result.get("json"),
                        "body": result.get("body", "")[:2000],
                    }
                    for result in step_results
                ],
            }
        )

    failed_ids = [
        result["id"] for result in case_results if not result["passed"]
    ]
    return {
        "failed_case_ids": failed_ids,
        "passed_count": len(case_results) - len(failed_ids),
        "failed_count": len(failed_ids),
        "cases": case_results,
    }


def _requires_auth(
    step: dict[str, Any],
    auth_config: dict[str, Any] | None,
) -> bool:
    if "requires_auth" in step:
        return bool(step["requires_auth"])
    if not isinstance(auth_config, dict):
        return False
    token = auth_config.get("token")
    if not isinstance(token, dict):
        return False
    step_path = str(step.get("path") or step.get("url") or "").split("?", 1)[0]
    token_path = str(token.get("endpoint") or "").split("?", 1)[0]
    if token_path and step_path.rstrip("/") == token_path.rstrip("/"):
        return False
    methods = auth_config.get("protectedMethods")
    if not isinstance(methods, list):
        methods = ["POST", "PUT", "PATCH", "DELETE"]
    return str(step.get("method") or "").upper() in {
        str(method).upper() for method in methods
    }


def _has_authorization_header(step: dict[str, Any]) -> bool:
    return any(
        str(key).lower() == "authorization"
        for key in (step.get("headers") or {})
    )


def _single_use_token(auth_config: dict[str, Any] | None) -> bool:
    if not isinstance(auth_config, dict):
        return False
    usage = auth_config.get("usage")
    rule = usage.get("tokenReuseRule") if isinstance(usage, dict) else ""
    text = str(rule or "").lower()
    return any(
        marker in text
        for marker in ("1次", "1 次", "one write", "single use", "single-use", "每次")
    )


def _fetch_access_token(
    *,
    base_url: str,
    package_header: str,
    package_id: str,
    auth_config: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    token = auth_config.get("token")
    if not isinstance(token, dict):
        return {"error": "token configuration is missing"}
    step = {
        "method": token.get("method") or "POST",
        "path": token.get("endpoint") or "",
        "headers": token.get("headers") or {},
        "body": token.get("body"),
    }
    response = _request(
        base_url=base_url,
        package_header=package_header,
        package_id=package_id,
        step=step,
        timeout=timeout,
    )
    if response.get("request_error"):
        return {"error": response["request_error"]}
    if not 200 <= int(response.get("status") or 0) < 300:
        return {"error": f"token endpoint returned status {response.get('status')}"}
    token_path = str(token.get("responseTokenPath") or "")
    found, access_token = _json_path(response.get("json"), token_path)
    if not found or access_token in (None, ""):
        return {"error": f"token path not found: {token_path}"}
    return {"access_token": access_token}


def _with_authorization(
    step: dict[str, Any],
    auth_config: dict[str, Any],
    access_token: str,
) -> dict[str, Any]:
    token = auth_config.get("token")
    token = token if isinstance(token, dict) else {}
    header_name = str(token.get("authorizationHeader") or "Authorization")
    template = str(
        token.get("authorizationHeaderFormat") or "Bearer ${accessToken}"
    )
    value = template.replace("${accessToken}", access_token)
    updated = dict(step)
    headers = dict(step.get("headers") or {})
    headers[header_name] = value
    updated["headers"] = headers
    return updated


def _validate_plan(plan: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["plan must be an object"]
    base_url = plan.get("base_url")
    parsed = urllib.parse.urlparse(str(base_url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        errors.append("base_url must be an absolute HTTP(S) URL")
    cases = plan.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("cases must be a non-empty array")
        return errors
    for case_index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"case {case_index} must be an object")
            continue
        if not str(case.get("id") or "").strip():
            errors.append(f"case {case_index} requires id")
        steps = case.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append(f"case {case_index} requires at least one step")
            continue
        for step_index, step in enumerate(steps):
            if not isinstance(step, dict):
                errors.append(f"case {case_index} step {step_index} must be an object")
                continue
            method = str(step.get("method") or "").upper()
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                errors.append(
                    f"case {case_index} step {step_index} has invalid method"
                )
            if not str(step.get("url") or step.get("path") or "").strip():
                errors.append(
                    f"case {case_index} step {step_index} requires url or path"
                )
    return errors


def _request(
    *,
    base_url: str,
    package_header: str,
    package_id: str,
    step: dict[str, Any],
    timeout: int,
) -> dict[str, Any]:
    raw_url = str(step.get("url") or step.get("path") or "")
    url = raw_url if urllib.parse.urlparse(raw_url).scheme else f"{base_url}/{raw_url.lstrip('/')}"
    query = step.get("query")
    if isinstance(query, dict) and query:
        separator = "&" if "?" in url else "?"
        url += separator + urllib.parse.urlencode(query, doseq=True)

    headers = {
        str(key): str(value)
        for key, value in (step.get("headers") or {}).items()
    }
    for key in list(headers):
        if key.lower() == package_header.lower():
            del headers[key]
    headers[package_header] = package_id

    body = step.get("body")
    data: bytes | None = None
    if body is not None and str(step.get("method")).upper() in {"POST", "PUT", "PATCH"}:
        if isinstance(body, (dict, list)):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            if not any(key.lower() == "content-type" for key in headers):
                headers["Content-Type"] = "application/json"
        else:
            data = str(body).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=str(step["method"]).upper(),
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw_body = response.read().decode("utf-8", errors="replace")
            return _response_payload(response.status, raw_body)
    except urllib.error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        return _response_payload(exc.code, raw_body)
    except Exception as exc:
        return {
            "status": 0,
            "body": "",
            "json": None,
            "request_error": f"{type(exc).__name__}: {exc}",
        }


def _response_payload(status: int, body: str) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = None
    return {"status": status, "body": body, "json": payload}


def _assert_response(
    response: dict[str, Any],
    assertion: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if "expectedStatus" in assertion:
        expected_status = assertion["expectedStatus"]
        if response.get("status") != expected_status:
            errors.append(
                f"status expected {expected_status!r}, got {response.get('status')!r}"
            )
    payload = response.get("json")
    for path in assertion.get("expectedFields") or []:
        found, _ = _json_path(payload, str(path))
        if not found:
            errors.append(f"missing field: {path}")
    expected_values = assertion.get("expectedValues") or {}
    if isinstance(expected_values, dict):
        for path, expected in expected_values.items():
            found, actual = _json_path(payload, str(path))
            if not found:
                errors.append(f"missing value path: {path}")
            elif actual != expected or type(actual) is not type(expected):
                errors.append(
                    f"value at {path} expected {expected!r}, got {actual!r}"
                )
    return errors


def _json_path(payload: Any, path: str) -> tuple[bool, Any]:
    current = payload
    if path == "":
        return True, current
    for token in path.split("."):
        if isinstance(current, dict) and token in current:
            current = current[token]
            continue
        if isinstance(current, list):
            try:
                index = int(token)
            except ValueError:
                return False, None
            if 0 <= index < len(current):
                current = current[index]
                continue
        return False, None
    return True, current


def _substitute(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _substitute(child, variables) for key, child in value.items()}
    if isinstance(value, list):
        return [_substitute(child, variables) for child in value]
    if not isinstance(value, str):
        return value
    full_match = _VARIABLE.fullmatch(value)
    if full_match and full_match.group(1) in variables:
        return variables[full_match.group(1)]

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return str(variables.get(name, match.group(0)))

    return _VARIABLE.sub(replace, value)
