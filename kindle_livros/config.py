"""Constantes e valores padrão do sistema."""

EXTENSOES_KINDLE = frozenset({".epub", ".pdf", ".mobi", ".azw3", ".txt", ".docx"})
EXTENSOES_AUDIO = frozenset({".mp3", ".m4a", ".wav", ".ogg"})

LIMITE_BLOCO_TRADUCAO = 4500
TENTATIVAS_TRADUCAO = 3
ESPERA_BASE_TRADUCAO = 2.0
MODELO_TRADUCAO_PADRAO = "claude-sonnet-5-5"
URL_ANTHROPIC_PADRAO = "https://api.anthropic.com"
VERSAO_API_ANTHROPIC = "2023-06-01"
TIMEOUT_TRADUCAO = 120
MAX_TOKENS_TRADUCAO = 8192

PAGINAS_POR_CAPITULO = 20
PARAGRAFOS_POR_CAPITULO = 40
TAMANHO_PARAGRAFO_TRANSCRICAO = 800
MODELO_WHISPER = "small"

MARGEM_ESPACO_BYTES = 1024 * 1024
TIMEOUT_HTTP = 30
USER_AGENT = "kindle-livros/1.0 (uso pessoal)"

URL_GUTENDEX = "https://gutendex.com/books"
URL_IA_BUSCA = "https://archive.org/advancedsearch.php"
URL_IA_METADADOS = "https://archive.org/metadata"
URL_IA_DOWNLOAD = "https://archive.org/download"
