#!/usr/bin/env bash
# One command, no arguments. Same as: python3 bootstrap.py
set -e
cd "$(dirname "$0")"
command -v python3 >/dev/null 2>&1 || { echo "Python 3.11+ is required."; exit 1; }
python3 bootstrap.py
