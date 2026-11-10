#!/bin/zsh
cd "$(dirname "$0")" || exit 1
if [[ -x .venv/bin/python ]]; then
  runner=.venv/bin/python
else
  runner=python3
fi
if ! "$runner" -c 'import numpy, soundfile, PIL, edge_tts' 2>/dev/null; then
  echo 'Install the dependencies first. See README.md, Setup.'
  read '?Press Return to close.'
  exit 1
fi
"$runner" -u run.py serve --open-browser
read '?Server stopped. Press Return to close.'
