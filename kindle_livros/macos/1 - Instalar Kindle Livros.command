#!/bin/bash
# Instalador do Kindle Livros para macOS. Dê dois cliques neste arquivo.
# Instala em ~/Library/Application Support/KindleLivros e cria o comando
# "kindle-livros" em ~/.local/bin. Não precisa de senha de administrador.

set -u

APP_DIR="$HOME/Library/Application Support/KindleLivros"
BIN_DIR="$HOME/.local/bin"
ORIGEM="$(cd "$(dirname "$0")/.." && pwd)"   # pasta kindle_livros/ (pai desta pasta)
MARCADOR="# kindle-livros (adicionado pelo instalador)"

pausa() {
  if [ -t 0 ]; then
    echo ""
    read -n 1 -s -r -p "Pressione uma tecla para fechar esta janela..."
    echo ""
  fi
}

falha() {
  echo ""
  echo "ERRO: $1"
  pausa
  exit 1
}

echo "=== Instalando Kindle Livros ==="
echo ""

# 1. Python 3.10 ou superior
PY=""
for candidato in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
  if command -v "$candidato" >/dev/null 2>&1 && "$candidato" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$(command -v "$candidato")"
    break
  fi
done
if [ -z "$PY" ]; then
  falha "Python 3.10 ou superior não encontrado. Instale em https://www.python.org/downloads/ e rode este instalador de novo."
fi
echo "[1/5] Python encontrado: $PY ($("$PY" --version 2>&1))"

# 2. Copia o código para a pasta de instalação
if [ ! -f "$ORIGEM/__init__.py" ] || [ ! -f "$ORIGEM/cli.py" ]; then
  falha "Não encontrei o pacote kindle_livros em $ORIGEM. Mantenha a pasta 'macos' dentro de 'kindle_livros' ao instalar."
fi
mkdir -p "$APP_DIR/src" || falha "Não foi possível criar $APP_DIR"
rm -rf "$APP_DIR/src/kindle_livros"
mkdir -p "$APP_DIR/src/kindle_livros"
cp -R "$ORIGEM/." "$APP_DIR/src/kindle_livros/" || falha "Não foi possível copiar os arquivos."
rm -rf "$APP_DIR/src/kindle_livros/macos" "$APP_DIR/src/kindle_livros/tests" "$APP_DIR/src/kindle_livros/__pycache__"
echo "[2/5] Arquivos copiados para $APP_DIR/src"

# 3. Ambiente Python isolado e dependências
rm -rf "$APP_DIR/venv"
"$PY" -m venv "$APP_DIR/venv" || falha "Não foi possível criar o ambiente Python."
PIP="$APP_DIR/venv/bin/pip"
"$PIP" install --quiet --upgrade pip || falha "Falha ao atualizar o pip (verifique a conexão com a internet)."
echo "[3/5] Instalando dependências (pode levar alguns minutos)..."
"$PIP" install --quiet pypdf reportlab deep-translator yt-dlp || falha "Falha ao instalar dependências (verifique a conexão com a internet)."
if ! "$PIP" install --quiet langdetect; then
  echo "AVISO: langdetect não foi instalado. O idioma será assumido como não português; a tradução continua."
fi
if ! "$PIP" install --quiet faster-whisper; then
  echo "AVISO: faster-whisper não foi instalado. Transcrição de áudio ficará indisponível; o resto funciona."
fi

# 4. Chave da API para tradução por IA (opcional, guardada só neste Mac com permissão restrita)
CHAVE_ARQ="$APP_DIR/chave_api"
if [ -t 0 ] && [ ! -s "$CHAVE_ARQ" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo ""
  echo "Tradução por IA (Claude) usa uma chave da API Anthropic (https://console.anthropic.com)."
  read -r -s -p "Cole a chave (ou Enter para pular e configurar depois): " CHAVE
  echo ""
  if [ -n "$CHAVE" ]; then
    umask 077
    printf '%s' "$CHAVE" > "$CHAVE_ARQ"
    chmod 600 "$CHAVE_ARQ"
    echo "Chave salva em $CHAVE_ARQ"
  fi
  unset CHAVE
fi

# 5. Comando kindle-livros
mkdir -p "$BIN_DIR" || falha "Não foi possível criar $BIN_DIR"
cat > "$BIN_DIR/kindle-livros" <<LAUNCHER
#!/bin/bash
if [ -s "$APP_DIR/chave_api" ] && [ -z "\${ANTHROPIC_API_KEY:-}" ]; then
  export ANTHROPIC_API_KEY="\$(cat "$APP_DIR/chave_api")"
fi
export PYTHONPATH="$APP_DIR/src\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$APP_DIR/venv/bin/python" -m kindle_livros "\$@"
LAUNCHER
chmod +x "$BIN_DIR/kindle-livros"

# Adiciona ~/.local/bin ao PATH do zsh (shell padrão do macOS), uma única vez
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    ZSHRC="$HOME/.zshrc"
    if ! grep -qF "$MARCADOR" "$ZSHRC" 2>/dev/null; then
      printf '\n%s\nexport PATH="$HOME/.local/bin:$PATH"\n' "$MARCADOR" >> "$ZSHRC"
    fi
    ;;
esac

if "$BIN_DIR/kindle-livros" --help >/dev/null 2>&1; then
  echo "[5/5] Comando instalado: $BIN_DIR/kindle-livros"
else
  falha "A instalação terminou, mas o comando não respondeu. Veja a mensagem acima."
fi

echo ""
echo "=== Pronto! ==="
echo "Abra um Terminal NOVO e rode:  kindle-livros detectar"
# Atalho de envio na Área de Trabalho (funciona mesmo depois de apagar a pasta baixada)
ATALHO="$HOME/Desktop/Kindle Livros.command"
if [ -d "$HOME/Desktop" ] && cp "$ORIGEM/macos/Kindle Livros.command" "$ATALHO" 2>/dev/null; then
  chmod +x "$ATALHO"
  echo "Atalho criado na Área de Trabalho: Kindle Livros.command"
fi
echo "Para enviar livros pelo Terminal: kindle-livros enviar ~/Downloads/livro.epub"
pausa
