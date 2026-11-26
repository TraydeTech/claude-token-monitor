#!/usr/bin/env bash
set -e

INSTALL_DIR="$HOME/projects/claude-token-monitor"
BIN="$HOME/.local/bin/claude-monitor"
DESKTOP="$HOME/.local/share/applications/claude-token-monitor.desktop"

echo "→ Instalando Claude Token Monitor..."

# Cria launcher
mkdir -p "$HOME/.local/bin"
cat > "$BIN" <<EOF
#!/usr/bin/env bash
exec python3 "$INSTALL_DIR/main.py" "\$@"
EOF
chmod +x "$BIN"

# Cria .desktop entry
mkdir -p "$HOME/.local/share/applications"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Name=Claude Token Monitor
Comment=Monitora uso de tokens do Claude em tempo real
Exec=$BIN
Icon=utilities-system-monitor
Terminal=false
Type=Application
Categories=Utility;Monitor;
Keywords=claude;token;monitor;ai;
StartupNotify=true
EOF

# Atualiza banco de aplicativos
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo ""
echo "✓ Instalado com sucesso!"
echo ""
echo "  Executar agora:        claude-monitor"
echo "  Com limite custom:     claude-monitor --limit 150000"
echo "  Ou pelo menu de apps:  pesquise 'Claude Token Monitor'"
echo ""
