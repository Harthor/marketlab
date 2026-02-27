#!/usr/bin/env bash
set -euo pipefail
PYTHONNOUSERSITE=1 /opt/homebrew/bin/python3.11 -S "$(cd "$(dirname "$0")" && pwd)/marketlab_status.py"
