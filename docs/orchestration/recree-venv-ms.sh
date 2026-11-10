#!/bin/bash
# Recree le venv de mesure de MoodleSync s'il a ete purge par le cache.
# Usage : bash /opt/data/cache/scratch/recree-venv-ms.sh
set -e
VENV=/opt/data/cache/scratch/venv-ms
if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c "import webview, PIL, pypdf, pypdfium2" 2>/dev/null; then
  echo "venv deja complet : $VENV"
  exit 0
fi
echo "creation du venv dans $VENV"
/opt/hermes/.venv/bin/python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q pywebview==6.2.1 pillow==13.0.0 pypdf==6.21.4 pypdfium2
"$VENV/bin/python" -c "import webview, PIL, pypdf, pypdfium2; print('venv pret')"
