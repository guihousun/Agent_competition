#!/usr/bin/env bash
set -Eeuo pipefail
trap 'code=$?; echo "start.sh failed at line ${LINENO}: ${BASH_COMMAND}" >&2; exit "$code"' ERR

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

detect_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    echo "$PYTHON_BIN"
    return 0
  fi

  local os_name
  os_name="$(uname -s 2>/dev/null || echo unknown)"
  local candidates=()
  case "$os_name" in
    MINGW*|MSYS*|CYGWIN*)
      candidates=(python py python3)
      ;;
    *)
      candidates=(python3 python py)
      ;;
  esac

  local candidate
  for candidate in "${candidates[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done

  echo "python"
}

detect_venv_python() {
  local unix_python="$ROOT_DIR/.venv/bin/python"
  local windows_python="$ROOT_DIR/.venv/Scripts/python.exe"

  if [[ -x "$unix_python" ]]; then
    echo "$unix_python"
    return 0
  fi
  if [[ -x "$windows_python" ]]; then
    echo "$windows_python"
    return 0
  fi

  echo "Cannot find venv Python under .venv." >&2
  return 1
}

dependencies_available() {
  "$1" -c "import openpyxl, pandas, docx, pptx, pdfplumber, bs4, PIL" \
    >/dev/null 2>&1
}

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: bash start.sh <question_path> <result_path> [package_id]" >&2
  exit 2
fi

PYTHON_CMD="$(detect_python)"
if ! dependencies_available "$PYTHON_CMD"; then
  echo "[DEPENDENCY_SETUP] installing requirements.txt" >&2
  "$PYTHON_CMD" -m venv .venv
  PYTHON_CMD="$(detect_venv_python)"
  "$PYTHON_CMD" -m pip install \
    --disable-pip-version-check \
    --no-input \
    --trusted-host mirrors.tools.huawei.com \
    -i http://mirrors.tools.huawei.com/pypi/simple \
    -r requirements.txt
fi

QUESTION_PATH="$1"
RESULT_PATH="$2"
PACKAGE_ID="${3:-}"

export PACKAGE_ID
export packageId="$PACKAGE_ID"

"$PYTHON_CMD" -u -m source.main \
  --question "$QUESTION_PATH" \
  --output "$RESULT_PATH"
