#!/usr/bin/env bash
set -euo pipefail

SOURCE_PATH="${1:-${QAIRA_SOURCE:-/repo}}"
OUTPUT_PATH="${2:-${QAIRA_OUTPUT:-/output}}"
CONFIG_PATH="${3:-${QAIRA_CONFIG:-/config/config.yaml}}"
CHANGED_FILES="${4:-${QAIRA_CHANGED_FILES:-}}"
LEARNING_PATH="${5:-${QAIRA_LEARNING:-/learning}}"

if [ ! -d "$SOURCE_PATH" ]; then
  echo "ERROR: source folder does not exist: $SOURCE_PATH"
  exit 2
fi

mkdir -p "$OUTPUT_PATH" "$LEARNING_PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARGS=(--source "$SOURCE_PATH" --output "$OUTPUT_PATH" --learning "$LEARNING_PATH")

if [ -f "$CONFIG_PATH" ]; then
  ARGS+=(--config "$CONFIG_PATH")
fi

if [ -n "$CHANGED_FILES" ] && [ -f "$CHANGED_FILES" ]; then
  ARGS+=(--changed-files "$CHANGED_FILES")
fi

export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"
python3 "$SCRIPT_DIR/src/qaira_semantic_compiler/orchestrator_v59.py" "${ARGS[@]}"
