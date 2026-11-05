#!/bin/sh
# Executa o ecoibeu mouse com o Python do sistema (que tem PyGObject/GTK3).
cd "$(dirname "$0")" || exit 1
exec /usr/bin/python3 app.py "$@"
