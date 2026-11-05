#!/bin/bash
# Remove o Kindle Livros do Mac (não apaga seus livros nem o Kindle).

APP_DIR="$HOME/Library/Application Support/KindleLivros"
LAUNCHER="$HOME/.local/bin/kindle-livros"
BIN_DIR="$HOME/.local/bin"
MARCADOR="# kindle-livros (adicionado pelo instalador)"

echo "Isto remove o programa Kindle Livros deste Mac."
if [ -t 0 ]; then
  read -r -p "Continuar? (s/N) " RESP
else
  RESP="n"
fi
case "$RESP" in
  s|S|sim|SIM) ;;
  *) echo "Cancelado."; exit 0 ;;
esac

rm -rf "$APP_DIR" "$LAUNCHER"
if [ -f "$HOME/.zshrc" ] && grep -qF "$MARCADOR" "$HOME/.zshrc"; then
  # Remove o marcador e a linha de PATH que o instalador acrescentou
  grep -vF -e "$MARCADOR" -e 'export PATH="$HOME/.local/bin:$PATH"' "$HOME/.zshrc" > "$HOME/.zshrc.kl.tmp" \
    && mv "$HOME/.zshrc.kl.tmp" "$HOME/.zshrc"
fi
rmdir "$BIN_DIR" 2>/dev/null   # remove ~/.local/bin só se estiver vazio
echo "Kindle Livros removido."
if [ -t 0 ]; then read -n 1 -s -r -p "Pressione uma tecla para fechar..."; echo ""; fi
