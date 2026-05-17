#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <package-spec>..." >&2
  exit 1
fi

uv add "$@"
uv export --format requirements.txt -o requirements.txt --no-header --no-annotate --no-hashes --no-dev