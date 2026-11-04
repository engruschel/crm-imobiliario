# kindle_livros

Ferramenta de linha de comando para:

- **enviar livros ao Kindle por USB** (detecção automática ou caminho manual);
- **buscar livros** em fontes legais: Project Gutenberg, Internet Archive e suas próprias pastas;
- **converter** PDF, TXT, EPUB, áudio e legendas do YouTube para EPUB (ou MOBI/AZW3, com o Calibre);
- **traduzir** o livro para outro idioma;
- rodar tudo de uma vez com o comando `pipeline`.

O núcleo usa apenas a biblioteca padrão do Python 3.10+. Pypdf, deep-translator, faster-whisper e yt-dlp são opcionais.

## Instalação

```bash
# núcleo (envio ao Kindle, EPUB, busca): nada a instalar
python3 -m kindle_livros detectar

# recursos opcionais, conforme a necessidade
pip install -r kindle_livros/requirements.txt
```

Para MOBI/AZW3, instale o [Calibre](https://calibre-ebook.com/) (o comando `ebook-convert` precisa estar no PATH).

## Uso

Execute a partir da pasta que contém `kindle_livros/`, com `python3 -m kindle_livros COMANDO`.

| Comando | Para que serve |
|---|---|
| `detectar` | Mostra os Kindles conectados por USB. |
| `buscar TERMO` | Lista resultados com formatos e links. Fontes: `--fonte gutenberg internet_archive local`. |
| `converter ENTRADA` | Gera EPUB (ou `.mobi`/`.azw3` com `-s`). ENTRADA: arquivo ou URL do YouTube. |
| `traduzir ENTRADA --idioma pt` | Traduz e grava um EPUB. `--cache arquivo.json` evita repetir traduções. |
| `enviar ARQUIVO...` | Copia para `documents/` do Kindle. `--destino` informa o caminho manualmente. |
| `pipeline TERMO` | Busca, baixa, converte, traduz (se `--idioma`) e envia o primeiro resultado (ou `--indice N`). |

### Exemplos

```bash
# Ver quais livros existem sobre um tema nas fontes legais
python3 -m kindle_livros buscar "dom casmurro" --fonte gutenberg internet_archive

# Buscar nos seus próprios arquivos
python3 -m kindle_livros buscar "relatorio" --fonte local --pasta-local ~/Documentos/livros

# Converter um PDF e gerar um EPUB
python3 -m kindle_livros converter meu_livro.pdf -s meu_livro.epub --idioma-origem pt

# Gerar um EPUB a partir das legendas automáticas em inglês de um vídeo
python3 -m kindle_livros converter "https://www.youtube.com/watch?v=ID" --idioma-origem en

# Traduzir um EPUB para inglês, guardando o cache
python3 -m kindle_livros traduzir livro.epub --idioma en --cache cache_en.json

# Enviar dois arquivos ao Kindle conectado (sem sobrescrever existentes)
python3 -m kindle_livros enviar livro.epub notas.pdf

# Substituir um arquivo que já está no Kindle
python3 -m kindle_livros enviar livro.epub --forcar

# Tudo em um comando: busca, baixa, traduz para português e envia
python3 -m kindle_livros pipeline "pride and prejudice" --idioma pt
```

### Envio ao Kindle

- Pontos de montagem reconhecidos: `/media/*/Kindle`, `/run/media/*/Kindle`, `/mnt/Kindle` (Linux), `/Volumes/Kindle` (macOS) e unidades com rótulo "Kindle" (Windows).
- Formatos aceitos: EPUB, PDF, MOBI, AZW3, TXT, DOCX.
- Arquivos já existentes não são sobrescritos sem `--forcar`.
- O espaço livre é verificado antes da cópia.
- `--destino` aceita a raiz do Kindle ou a pasta `documents/`. Uma pasta só é aceita como Kindle se tiver `documents/` e `system/` juntas; caso contrário o envio é recusado, e `--confirmar-destino` força.
- A cópia vai para um arquivo temporário e só substitui o destino ao concluir.
- Ejete o Kindle pelo sistema operacional antes de desconectar. O programa apenas avisa.

### Saída e idiomas

- Sem `-s`, a saída vai para o diretório atual com o nome do título original (também em `traduzir` e `pipeline`). A verificação de saída acontece antes da tradução. Se esse caminho for o próprio arquivo de entrada, o comando é recusado e o arquivo original não é alterado.
- Para EPUB de entrada, o idioma declarado nos metadados do arquivo tem precedência sobre `--idioma-origem`. `--idioma-origem` vale para TXT, PDF, áudio e legendas do YouTube.

### Tradução

A tradução usa a interface `Tradutor` (`kindle_livros/tradutor.py`), que recebe uma lista de textos e devolve a lista traduzida. A implementação padrão usa `deep-translator` (Google Tradutor). Para usar outro serviço, crie uma classe com `traduzir(textos, destino)` e passe-a a `traduzir_livro`. O envio é feito em blocos de até 4500 caracteres, com novas tentativas e espera exponencial.

## Testes

```bash
python3 -m pytest kindle_livros/tests -q
```

Os testes usam mocks e não acessam a internet.

## Aviso legal e direitos autorais

Este projeto não baixa nem distribui conteúdo protegido. As fontes de busca são:

- **Project Gutenberg** e **Internet Archive**: obras de domínio público ou com licença aberta. Confira a licença de cada item.
- **Arquivos locais**: somente os que você já possui.

Ao converter ou traduzir um livro, você é responsável por ter o direito de usá-lo. Não use a ferramenta com obras protegidas por direitos autorais sem autorização do titular. Traduções automáticas podem conter erros e devem ser revisadas antes do uso.

## Limitações conhecidas

- A divisão de capítulos de PDF é por grupos de páginas (padrão: 20). Títulos de capítulo não são detectados no PDF.
- PDFs digitalizados (sem texto extraível) não são suportados; não há OCR.
- A divisão de parágrafos de PDF depende de linhas em branco no texto extraído.
- Áudio é transcrito no idioma informado com `--idioma-origem`; o padrão `small` do Whisper roda na CPU e pode ser lento em áudios longos.
- Legendas do YouTube dependem da disponibilidade de legendas no idioma pedido (incluindo legendas automáticas).
- MOBI e AZW3 exigem o Calibre; sem ele, use EPUB (aceito pelos Kindles atuais). A conversão com o Calibre tem limite de 10 minutos.
- A busca local ignora arquivos que estão dentro de um Kindle (pastas `documents/` e `system/` juntas, abaixo da pasta pesquisada), para não devolver cópias já enviadas. A própria pasta pesquisada nunca é excluída.
