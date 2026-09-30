#!/usr/bin/env bash
set -euo pipefail
GPT_BLENDER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${PYTHON:-python3}" "$GPT_BLENDER_DIR/run_pipeline.py" "$@"
