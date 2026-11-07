#!/bin/bash
# Instalação em uma linha, no Terminal do Mac:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/engruschel/crm-imobiliario/claude/kindle-custom-books-system-dbj73e/kindle_livros/macos/instalar.sh)"
# Baixa o projeto do GitHub, roda o instalador e apaga os arquivos temporários.

URL="${KINDLE_ZIP_URL:-https://codeload.github.com/engruschel/crm-imobiliario/zip/refs/heads/claude/kindle-custom-books-system-dbj73e}"
TMP="$(mktemp -d)" || exit 1
trap 'rm -rf "$TMP"' EXIT

echo "Baixando o Kindle Livros..."
if ! curl -fsSL "$URL" -o "$TMP/projeto.zip"; then
  echo "ERRO: não consegui baixar o projeto. Verifique a conexão com a internet."
  exit 1
fi
unzip -q "$TMP/projeto.zip" -d "$TMP" || { echo "ERRO: arquivo baixado inválido."; exit 1; }

PASTA="$(ls -d "$TMP"/crm-imobiliario-*/kindle_livros/macos 2>/dev/null | head -n 1)"
if [ -z "$PASTA" ]; then
  echo "ERRO: pasta do instalador não encontrada no download."
  exit 1
fi
bash "$PASTA/1 - Instalar Kindle Livros.command"
