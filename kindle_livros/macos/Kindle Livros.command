#!/bin/bash
# Abre o Kindle Livros no navegador. Deixe esta janela aberta enquanto usa o app.
LAUNCHER="$HOME/.local/bin/kindle-livros"
if [ ! -x "$LAUNCHER" ]; then
  echo "O Kindle Livros não está instalado. Rode o comando de instalação primeiro."
  read -n 1 -s -r -p "Pressione uma tecla para fechar..."
  exit 1
fi
exec "$LAUNCHER" app
