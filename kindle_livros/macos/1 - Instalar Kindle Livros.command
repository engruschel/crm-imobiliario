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
echo "[1/4] Python encontrado: $PY ($("$PY" --version 2>&1))"

# 2. Copia o código para a pasta de instalação
if [ ! -f "$ORIGEM/__init__.py" ] || [ ! -f "$ORIGEM/cli.py" ]; then
  falha "Não encontrei o pacote kindle_livros em $ORIGEM. Mantenha a pasta 'macos' dentro de 'kindle_livros' ao instalar."
fi
mkdir -p "$APP_DIR/src" || falha "Não foi possível criar $APP_DIR"
rm -rf "$APP_DIR/src/kindle_livros"
mkdir -p "$APP_DIR/src/kindle_livros"
cp -R "$ORIGEM/." "$APP_DIR/src/kindle_livros/" || falha "Não foi possível copiar os arquivos."
rm -rf "$APP_DIR/src/kindle_livros/macos" "$APP_DIR/src/kindle_livros/tests" "$APP_DIR/src/kindle_livros/__pycache__"
echo "[2/4] Arquivos copiados para $APP_DIR/src"

# 3. Ambiente Python isolado e dependências
rm -rf "$APP_DIR/venv"
"$PY" -m venv "$APP_DIR/venv" || falha "Não foi possível criar o ambiente Python."
PIP="$APP_DIR/venv/bin/pip"
"$PIP" install --quiet --upgrade pip || falha "Falha ao atualizar o pip (verifique a conexão com a internet)."
echo "[3/4] Instalando dependências (pode levar alguns minutos)..."
"$PIP" install --quiet pypdf deep-translator yt-dlp || falha "Falha ao instalar dependências (verifique a conexão com a internet)."
if ! "$PIP" install --quiet faster-whisper; then
  echo "AVISO: faster-whisper não foi instalado. Transcrição de áudio ficará indisponível; o resto funciona."
fi

# 4. Comando kindle-livros
mkdir -p "$BIN_DIR" || falha "Não foi possível criar $BIN_DIR"
cat > "$BIN_DIR/kindle-livros" <<LAUNCHER
#!/bin/bash
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
  echo "[4/4] Comando instalado: $BIN_DIR/kindle-livros"
else
  falha "A instalação terminou, mas o comando não respondeu. Veja a mensagem acima."
fi

echo ""
echo "=== Pronto! ==="
echo "Abra um Terminal NOVO e rode:  kindle-livros detectar"
echo "Para enviar livros, use também o arquivo '2 - Enviar livros ao Kindle.command'."
pausa
