#!/bin/bash
# Dê dois cliques para escolher livros e enviá-los ao Kindle conectado por USB.

LAUNCHER="$HOME/.local/bin/kindle-livros"

pausa() {
  if [ -t 0 ]; then
    echo ""
    read -n 1 -s -r -p "Pressione uma tecla para fechar esta janela..."
    echo ""
  fi
}

if [ ! -x "$LAUNCHER" ]; then
  echo "O Kindle Livros não está instalado. Dê dois cliques em '1 - Instalar Kindle Livros.command' primeiro."
  pausa
  exit 1
fi

if ! command -v osascript >/dev/null 2>&1; then
  echo "Este Mac não tem o AppleScript (osascript). Use o Terminal: kindle-livros enviar ARQUIVO..."
  pausa
  exit 1
fi

ERRO_ARQ="$(mktemp)"
ESCOLHA=$(osascript \
  -e 'set arquivos to (choose file with prompt "Escolha os livros para enviar ao Kindle (EPUB, PDF, MOBI, AZW3, TXT ou DOCX)" with multiple selections allowed)' \
  -e 'set saida to ""' \
  -e 'repeat with arquivo in arquivos' \
  -e 'set saida to saida & POSIX path of arquivo & linefeed' \
  -e 'end repeat' \
  -e 'return saida' 2>"$ERRO_ARQ")
STATUS_OSA=$?
if [ $STATUS_OSA -ne 0 ]; then
  if grep -q -- "-128" "$ERRO_ARQ"; then
    echo "Nenhum arquivo escolhido."
    rm -f "$ERRO_ARQ"
    pausa
    exit 0
  fi
  echo "Não foi possível abrir a janela de escolha de arquivos:"
  cat "$ERRO_ARQ"
  rm -f "$ERRO_ARQ"
  pausa
  exit 1
fi
rm -f "$ERRO_ARQ"

if [ -z "$ESCOLHA" ]; then
  echo "Nenhum arquivo escolhido."
  pausa
  exit 0
fi

ARQUIVOS=()
while IFS= read -r linha; do
  [ -n "$linha" ] && ARQUIVOS+=("$linha")
done <<< "$ESCOLHA"

echo "Enviando ${#ARQUIVOS[@]} arquivo(s) ao Kindle..."
echo ""
"$LAUNCHER" enviar "${ARQUIVOS[@]}"
STATUS=$?
echo ""
if [ $STATUS -eq 0 ]; then
  echo "Concluído. Ejete o Kindle pelo Finder antes de desconectar."
else
  echo "Não foi possível enviar. Veja a mensagem acima."
  echo "Dica: conecte o Kindle, desbloqueie o aparelho e tente de novo."
fi
pausa
exit $STATUS
