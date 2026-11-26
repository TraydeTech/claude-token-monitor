#!/usr/bin/env python3
"""
Claude Code Stop hook — força atualização do monitor ao fim de cada resposta.
Instale em ~/.claude/settings.json como hook de Stop.
"""

import sys
import json

# Lê stdin (Claude Code passa dados do evento)
try:
    data = json.loads(sys.stdin.read())
except Exception:
    data = {}

# O monitor atualiza automaticamente via polling; este hook apenas
# serve como trigger futuro para push-based updates.
print(json.dumps({"continue": True}))
