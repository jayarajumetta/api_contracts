#!/usr/bin/env bash
set -euo pipefail

SOURCE_PATH="${1:-${QAIRA_SOURCE:-/repo}}"
OUTPUT_PATH="${2:-${QAIRA_OUTPUT:-/output}}"
CONFIG_PATH="${3:-${QAIRA_CONFIG:-/config/config.yaml}}"
LEARNING_PATH="${4:-${QAIRA_LEARNING:-/learning}}"

mkdir -p "$OUTPUT_PATH" "$LEARNING_PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR/src:${PYTHONPATH:-}"
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"

ARGS=(--source "$SOURCE_PATH" --output "$OUTPUT_PATH" --learning "$LEARNING_PATH")
if [ -f "$CONFIG_PATH" ]; then
  ARGS+=(--config "$CONFIG_PATH")
fi

python3 -m qaira_semantic_compiler.orchestrator "${ARGS[@]}"
