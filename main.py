"""CLI do compilador da DSL musical — compila e executa em um passo.

    python main.py exemplos/demo.ritmo                  # compila, gera o áudio e toca
    python main.py exemplos/demo.ritmo --mostrar-ast    # imprime a AST
    python main.py exemplos/demo.ritmo --emitir out.py  # salva o Python gerado
    python main.py exemplos/demo.ritmo --sem-tocar      # só gera o .wav
"""

import argparse
import sys
from pathlib import Path

from compilador.ast_nos import formatar_arvore
from compilador.erros import ErroCompilacao, ErrosSemanticos
from compilador.gerador import gerar
from compilador.parser import analisar, arvore_concreta
from compilador.semantico import analisar_semantica


def compilar(fonte: str, nome: str, *, reproduzir=True, arquivo_padrao="saida.wav"):
    """Fonte -> (AST, resultado semântico, código Python). Lança erros de compilação."""
    prog = analisar(fonte)                       # léxico + sintático -> AST
    resultado = analisar_semantica(prog)         # semântico
    codigo = gerar(prog, resultado.tabela, nome_fonte=nome,
                   reproduzir=reproduzir, arquivo_padrao=arquivo_padrao)
    return prog, resultado, codigo


def executar(codigo: str, nome: str):
    escopo = {"__name__": "__main__", "__file__": nome}
    exec(compile(codigo, f"<gerado de {nome}>", "exec"), escopo)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compilador da DSL musical (estilo Strudel/Tidal)")
    ap.add_argument("arquivo", help="programa-fonte .ritmo")
    ap.add_argument("--mostrar-ast", action="store_true", help="imprime a AST")
    ap.add_argument("--mostrar-arvore", action="store_true",
                    help="imprime a árvore de derivação (concreta) do Lark")
    ap.add_argument("--emitir", metavar="SAIDA.py", help="salva o Python gerado")
    ap.add_argument("--sem-tocar", action="store_true", help="não reproduz; só gera o .wav")
    ap.add_argument("--so-compilar", action="store_true",
                    help="para após a compilação (não executa o código gerado)")
    args = ap.parse_args(argv)

    caminho = Path(args.arquivo)
    try:
        fonte = caminho.read_text(encoding="utf-8")
    except OSError as e:
        print(f"erro: não foi possível ler {caminho}: {e.strerror}", file=sys.stderr)
        return 1

    nome = str(caminho)
    try:
        prog, resultado, codigo = compilar(
            fonte, nome, reproduzir=not args.sem_tocar,
            arquivo_padrao=caminho.with_suffix(".wav").name)
    except (ErroCompilacao, ErrosSemanticos) as e:
        print(e.formatar(fonte, nome), file=sys.stderr)
        n = len(e.erros) if isinstance(e, ErrosSemanticos) else 1
        print(f"\ncompilação interrompida: {n} erro(s)", file=sys.stderr)
        return 1

    for aviso in resultado.avisos:
        print(aviso.formatar(fonte, nome), file=sys.stderr)

    if args.mostrar_arvore:
        print(arvore_concreta(fonte))
    if args.mostrar_ast:
        print(formatar_arvore(prog))
    if args.emitir:
        Path(args.emitir).write_text(codigo, encoding="utf-8")
        print(f"código Python salvo em {args.emitir}")

    if args.so_compilar or args.mostrar_ast or args.mostrar_arvore:
        return 0

    executar(codigo, nome)
    return 0


if __name__ == "__main__":
    sys.exit(main())
