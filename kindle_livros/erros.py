"""Exceções próprias do pacote kindle_livros."""


class KindleLivrosError(Exception):
    """Erro base do pacote; as mensagens são exibidas ao usuário em português."""


class KindleNaoEncontrado(KindleLivrosError):
    """Nenhum Kindle conectado ou caminho de destino inválido."""


class EspacoInsuficiente(KindleLivrosError):
    """Espaço livre no dispositivo insuficiente para a cópia."""


class FormatoNaoSuportado(KindleLivrosError):
    """Formato de arquivo não aceito para leitura, conversão ou envio."""


class ErroBusca(KindleLivrosError):
    """Falha ao consultar uma fonte de livros ou baixar um arquivo."""


class ErroConversao(KindleLivrosError):
    """Falha ao ler ou gerar um livro."""


class ErroTraducao(KindleLivrosError):
    """Falha na tradução de um texto."""


class DependenciaAusente(KindleLivrosError):
    """Biblioteca opcional necessária não está instalada."""
