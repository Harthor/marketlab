#!/usr/bin/env bash
set -euo pipefail

is_compatible() {
  local interpreter="$1"
  if "$interpreter" -c 'import sys; print(1 if sys.version_info >= (3, 11) else 0)' | grep -q '^1$'; then
    return 0
  fi
  return 1
}

candidates=()
if [ "$(uname -s)" = "Darwin" ]; then
  candidates+=("/opt/homebrew/bin/python3.11")
fi
candidates+=("python3.11" "python3")

for candidate in "${candidates[@]}"; do
  resolved="$(command -v "$candidate" 2>/dev/null || true)"
  if [ -z "$resolved" ]; then
    continue
  fi

  if [ ! -x "$resolved" ]; then
    continue
  fi

  if is_compatible "$resolved"; then
    echo "$resolved"
    exit 0
  fi

done

printf 'python_select: could not find Python >= 3.11 in allowed candidates. Checked: ' 1>&2
echo "${candidates[*]}" 1>&2
printf 'Hint: install Python 3.11+ or adjust PATH (e.g. brew install python@3.11).
' 1>&2
exit 1
