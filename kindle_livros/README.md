# kindle_livros

Ferramenta de linha de comando para:

- **enviar livros ao Kindle por USB** (detecção automática ou caminho manual);
- **buscar livros** em fontes legais: Project Gutenberg, Internet Archive e suas próprias pastas;
- **converter** PDF, TXT, EPUB, áudio e legendas do YouTube para EPUB (ou MOBI/AZW3, com o Calibre);
- **traduzir** o livro para outro idioma;
- rodar tudo de uma vez com o comando `pipeline`.

O núcleo usa apenas a biblioteca padrão do Python 3.10+. Pypdf, deep-translator, faster-whisper e yt-dlp são opcionais. A tradução por IA usa a API da Anthropic (chave em `ANTHROPIC_API_KEY`).

## Instalação

```bash
# núcleo (envio ao Kindle, EPUB, busca): nada a instalar
python3 -m kindle_livros detectar

# recursos opcionais, conforme a necessidade
pip install -r kindle_livros/requirements.txt
```

Para MOBI/AZW3, instale o [Calibre](https://calibre-ebook.com/) (o comando `ebook-convert` precisa estar no PATH).

## Passo a passo no Mac

**Forma mais simples:** dentro de `kindle_livros/macos/`, dê dois cliques em `1 - Instalar Kindle Livros.command`. Depois, para enviar livros, dê dois cliques em `2 - Enviar livros ao Kindle.command`. Para remover, use `3 - Desinstalar Kindle Livros.command`. Os passos abaixo explicam o mesmo processo manualmente.

Testado apenas em Linux. Estes passos seguem a mesma lógica no macOS, mas o envio ao Kindle em Mac ainda não foi verificado com um aparelho real.

### 1. Conferir o Python

Abra o aplicativo **Terminal** (Cmd + Espaço, digite "Terminal") e rode:

```bash
python3 --version
```

Precisa ser **3.10 ou superior**. Se aparecer uma versão menor, ou se o Mac pedir para instalar as "ferramentas de desenvolvedor", instale o Python em https://www.python.org/downloads/ e abra um Terminal novo.

### 2. Baixar o projeto

```bash
cd ~/Documents
git clone https://github.com/engruschel/crm-imobiliario.git
cd crm-imobiliario
git checkout claude/kindle-custom-books-system-dbj73e
```

Se o Mac pedir para instalar as ferramentas de desenvolvedor do Xcode, aceite; isso instala o `git`.

### 3. Criar um ambiente isolado e instalar as dependências opcionais

No macOS recente, o Python do sistema não aceita `pip install` direto. Crie um ambiente virtual:

```bash
python3 -m venv ~/kindle-env
source ~/kindle-env/bin/activate
pip install -r kindle_livros/requirements.txt
```

Sempre que abrir um Terminal novo, rode `source ~/kindle-env/bin/activate` antes de usar o programa. O núcleo funciona sem esse passo, mas a tradução, a transcrição e as legendas do YouTube precisam dele.

### 4. Conectar o Kindle e verificar

1. Conecte o Kindle ao Mac pelo cabo USB e desbloqueie o aparelho, se pedir.
2. No Finder, o Kindle deve aparecer na barra lateral com o nome **Kindle**.
3. No Terminal, rode:

```bash
python3 -m kindle_livros detectar
```

A saída deve mostrar o caminho `/Volumes/Kindle`. Se aparecer "Nenhum Kindle encontrado":
- confira se o volume aparece em `/Volumes` (rode `ls /Volumes`);
- se o nome do volume for diferente de "Kindle", use `--destino /Volumes/NOME_DO_VOLUME` nos comandos de envio;
- o Kindle precisa mostrar as pastas `documents/` e `system/` na raiz.

### 5. Enviar um livro

```bash
python3 -m kindle_livros enviar ~/Downloads/meu_livro.epub
```

Use arquivos EPUB, PDF, MOBI, AZW3, TXT ou DOCX. Para substituir um livro que já está no Kindle, acrescente `--forcar`.

### 6. Desconectar com segurança

Antes de tirar o cabo, clique com o botão direito no ícone **Kindle** no Finder e escolha **Ejetar**. Só depois desconecte.

### 7. Exemplo completo: buscar, converter, traduzir e enviar

```bash
python3 -m kindle_livros buscar "dom casmurro" --fonte gutenberg internet_archive
python3 -m kindle_livros pipeline "dom casmurro" --fonte gutenberg --idioma en
```

O comando `pipeline` baixa o primeiro resultado, converte para EPUB, traduz para o idioma de `--idioma` e envia ao Kindle conectado. Sem Kindle, o EPUB fica na pasta `kindle_saida` dentro do diretório atual. Para escolher outro resultado, use `--indice 2`.

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

A tradução padrão é feita por IA (Claude, pela API oficial da Anthropic). Ela entende o contexto do livro, mantém nomes e tom, e traduz em blocos de até 4500 caracteres.

- Precisa de uma chave da API: crie em https://console.anthropic.com e defina `ANTHROPIC_API_KEY`. No instalador para Mac, a chave é pedida na instalação e guardada só nesse computador, com permissão restrita.
- Custo: a API é paga por uso. Livros grandes gastam mais; use `--cache` para não pagar duas vezes pelo mesmo trecho.
- Modelo: `--modelo` escolhe o modelo (padrão `claude-sonnet-5-5`; `claude-haiku-5-5` é mais barato e mais rápido, com menos qualidade literária).
- Sem IA: `--tradutor google` usa o Google Tradutor (biblioteca `deep-translator`). Qualidade menor, sem custo e sem chave.

Exemplos:

```bash
export ANTHROPIC_API_KEY="sua-chave"
python3 -m kindle_livros traduzir livro.epub --idioma en --cache cache_en.json
python3 -m kindle_livros traduzir livro.epub --idioma en --modelo claude-haiku-5-5
python3 -m kindle_livros traduzir livro.epub --idioma en --tradutor google
```

Para outro serviço de tradução, crie uma classe com `traduzir(textos, destino)` (ver `kindle_livros/tradutor.py`).

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
