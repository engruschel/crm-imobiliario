"""Interface de linha de comando (subcomandos em português)."""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from kindle_livros.busca import buscar, melhor_formato_para_conversao, nome_arquivo, obter_arquivo
from kindle_livros.config import PAGINAS_POR_CAPITULO
from kindle_livros.conversor import carregar_livro, garantir_saida_distinta, salvar_livro
from kindle_livros.erros import ErroBusca, KindleLivrosError, KindleNaoEncontrado
from kindle_livros.kindle_usb import detectar_kindles, enviar_para_kindle
from kindle_livros.config import MODELO_TRADUCAO_PADRAO
from kindle_livros.tradutor import ClaudeBackend, DeepTranslatorBackend, Tradutor, TradutorComCache, traduzir_livro

AVISO_EJECAO = "Antes de desconectar, ejete o Kindle com segurança pelo sistema operacional."


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kindle_livros", description="Busca, converte, traduz e envia livros ao Kindle.")
    sub = parser.add_subparsers(dest="comando", required=True, metavar="COMANDO")

    sub.add_parser("detectar", help="Mostra os Kindles conectados por USB.").set_defaults(func=_cmd_detectar)

    p = sub.add_parser("buscar", help="Busca livros em fontes legais e pastas locais.")
    p.add_argument("termo")
    _opcoes_busca(p)
    p.set_defaults(func=_cmd_buscar)

    p = sub.add_parser("converter", help="Converte PDF, TXT, EPUB, áudio ou link do YouTube para EPUB/MOBI/AZW3.")
    p.add_argument("entrada", help="Arquivo local ou URL do YouTube.")
    p.add_argument("-s", "--saida", type=Path, help="Arquivo de saída (.epub, .mobi ou .azw3).")
    p.add_argument("--idioma-origem", default="pt", help="Idioma do conteúdo original (padrão: pt).")
    p.add_argument("--paginas-por-capitulo", type=int, default=PAGINAS_POR_CAPITULO)
    p.set_defaults(func=_cmd_converter)

    p = sub.add_parser("traduzir", help="Traduz um livro para outro idioma.")
    p.add_argument("entrada", help="Arquivo local ou URL do YouTube.")
    p.add_argument("--idioma", required=True, help="Idioma de destino, ex.: pt, en, es.")
    p.add_argument("--idioma-origem", default="pt")
    p.add_argument("-s", "--saida", type=Path, help="Arquivo EPUB de saída.")
    p.add_argument("--cache", type=Path, help="Arquivo JSON para guardar as traduções.")
    _opcoes_traducao(p)
    p.set_defaults(func=_cmd_traduzir)

    p = sub.add_parser("enviar", help="Copia arquivos para a pasta documents/ do Kindle.")
    p.add_argument("arquivos", nargs="+", type=Path)
    _opcoes_envio(p)
    p.set_defaults(func=_cmd_enviar)

    p = sub.add_parser("pipeline", help="Busca, converte, traduz e envia o primeiro resultado em um comando.")
    p.add_argument("termo")
    _opcoes_busca(p)
    p.add_argument("--indice", type=int, default=1, help="Qual resultado usar (padrão: 1).")
    p.add_argument("--idioma-origem", default="pt")
    p.add_argument("--idioma", help="Idioma de destino da tradução (opcional).")
    p.add_argument("--cache", type=Path, help="Arquivo JSON de cache das traduções.")
    _opcoes_traducao(p)
    p.add_argument("--saida", type=Path, default=Path("kindle_saida"), help="Pasta de trabalho (padrão: kindle_saida).")
    _opcoes_envio(p)
    p.set_defaults(func=_cmd_pipeline)
    return parser


def _opcoes_busca(p: argparse.ArgumentParser) -> None:
    p.add_argument("--fonte", nargs="+", choices=["gutenberg", "internet_archive", "local"],
                   default=["gutenberg", "internet_archive"], help="Fontes a consultar.")
    p.add_argument("--pasta-local", type=Path, help="Pasta com seus arquivos (usada com --fonte local).")
    p.add_argument("--limite", type=int, default=10, help="Máximo de resultados por fonte.")


def _opcoes_envio(p: argparse.ArgumentParser) -> None:
    p.add_argument("--destino", type=Path, help="Caminho do Kindle (padrão: detecção automática).")
    p.add_argument("--forcar", action="store_true", help="Sobrescreve arquivos já existentes no Kindle.")
    p.add_argument("--confirmar-destino", action="store_true",
                   help="Aceita um --destino que não parece um Kindle (sem documents/ nem system/).")


def _cmd_detectar(_args: argparse.Namespace) -> None:
    kindles = detectar_kindles()
    if not kindles:
        print("Nenhum Kindle encontrado. Conecte o dispositivo por USB e tente novamente.")
        return
    for kindle in kindles:
        print(f"Kindle encontrado em: {kindle}")


def _cmd_buscar(args: argparse.Namespace) -> None:
    resultados, avisos = buscar(args.termo, args.fonte, args.limite, args.pasta_local)
    _mostrar_avisos(avisos)
    if not resultados:
        print("Nenhum livro encontrado.")
        return
    for numero, resultado in enumerate(resultados, start=1):
        print(f"{numero}. {resultado.titulo} — {resultado.autor} [{resultado.fonte}]")
        for formato, link in resultado.links.items():
            print(f"     {formato}: {link}")


def _cmd_converter(args: argparse.Namespace) -> None:
    livro = carregar_livro(args.entrada, args.idioma_origem, args.paginas_por_capitulo)
    saida = args.saida or Path(nome_arquivo(livro.titulo, "epub"))
    garantir_saida_distinta(args.entrada, saida)
    caminho = salvar_livro(livro, saida)
    print(f"Livro convertido: {caminho.resolve()}")


def _cmd_traduzir(args: argparse.Namespace) -> None:
    livro = carregar_livro(args.entrada, args.idioma_origem)
    saida = args.saida or Path(nome_arquivo(livro.titulo, "epub"))
    garantir_saida_distinta(args.entrada, saida)  # antes da tradução, para não gastar o serviço à toa
    traduzido = traduzir_livro(livro, _tradutor(args), args.idioma)
    print(f"Livro traduzido ({args.idioma}): {salvar_livro(traduzido, saida).resolve()}")


def _cmd_enviar(args: argparse.Namespace) -> None:
    _enviar(args.arquivos, args.destino, args.forcar, args.confirmar_destino)


def _cmd_pipeline(args: argparse.Namespace) -> None:
    resultados, avisos = buscar(args.termo, args.fonte, args.limite, args.pasta_local)
    _mostrar_avisos(avisos)
    if not resultados:
        raise ErroBusca("nenhum livro encontrado para o termo informado.")
    if not 1 <= args.indice <= len(resultados):
        raise ErroBusca(f"índice inválido: escolha entre 1 e {len(resultados)}.")
    escolhido = resultados[args.indice - 1]
    print(f"Usando: {escolhido.titulo} — {escolhido.autor} [{escolhido.fonte}]")

    formato_link = melhor_formato_para_conversao(escolhido.links)
    if formato_link is None:
        raise ErroBusca("o resultado não tem formato que o conversor saiba ler (EPUB, PDF ou TXT).")
    formato, link = formato_link
    origem = obter_arquivo(link, args.saida, nome_arquivo(escolhido.titulo, formato))
    print(f"Arquivo obtido: {origem}")

    livro = carregar_livro(str(origem), args.idioma_origem)
    epub = args.saida / nome_arquivo(livro.titulo, "epub")
    garantir_saida_distinta(str(origem), epub)  # antes da tradução
    if args.idioma:
        print(f"Traduzindo para '{args.idioma}'...")
        livro = traduzir_livro(livro, _tradutor(args), args.idioma)
    salvar_livro(livro, epub)
    print(f"EPUB gerado: {epub.resolve()}")

    if args.destino or detectar_kindles():
        _enviar([epub], args.destino, args.forcar, args.confirmar_destino)
    else:
        print("Nenhum Kindle conectado; o EPUB ficou na pasta de trabalho. Use 'enviar' quando conectar.")


def _enviar(arquivos: list[Path], destino: Path | None, forcar: bool, confirmar_destino: bool = False) -> None:
    if destino is None:
        kindles = detectar_kindles()
        if not kindles:
            raise KindleNaoEncontrado("Nenhum Kindle encontrado. Conecte por USB ou informe --destino.")
        destino = kindles[0]
    resultado = enviar_para_kindle(arquivos, destino, forcar, confirmar_destino)
    for copiado in resultado.copiados:
        print(f"Copiado: {copiado.name}")
    for ignorado in resultado.ignorados:
        print(f"Já existe no Kindle (use --forcar para substituir): {ignorado.name}")
    print(f"Destino: {resultado.pasta_documentos}")
    print(AVISO_EJECAO)


def _opcoes_traducao(p: argparse.ArgumentParser) -> None:
    p.add_argument("--tradutor", choices=["claude", "google"], default="claude",
                   help="claude: tradução por IA (padrão, precisa de ANTHROPIC_API_KEY); "
                        "google: Google Tradutor (sem IA).")
    p.add_argument("--modelo", default=MODELO_TRADUCAO_PADRAO,
                   help=f"Modelo de IA para --tradutor claude (padrão: {MODELO_TRADUCAO_PADRAO}).")


def _tradutor(args: argparse.Namespace) -> Tradutor:
    if args.tradutor == "google":
        base: Tradutor = DeepTranslatorBackend()
    else:
        base = ClaudeBackend(modelo=args.modelo)
    cache = args.cache
    return TradutorComCache(base, cache) if cache else base


def _mostrar_avisos(avisos: list[str]) -> None:
    for aviso in avisos:
        print(f"Aviso — {aviso}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    funcao: Callable[[argparse.Namespace], None] = args.func
    try:
        funcao(args)
    except KindleLivrosError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Operação cancelada.", file=sys.stderr)
        return 130
    return 0
