"""Geração de código: AST -> script Python autocontido.

Cada nó da mini-notação vira uma chamada a um combinador do runtime
(seq, stack, alterna, rapido, ...). O compilador NÃO pré-calcula eventos:
o código gerado espelha a estrutura do programa-fonte.

Nomes gerados recebem prefixos para não colidir com o runtime:
    i_<nome>  instrumentos      p_<nome>  padrões      f_<nome>  faixas
"""

from pathlib import Path
from typing import List

from . import ast_nos as A
from .semantico import TabelaSimbolos

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVOS_RUNTIME = [RAIZ / "runtime" / "padroes.py", RAIZ / "runtime" / "sintese.py"]


# ---------------------------------------------------------------------------
# Mini-notação -> expressão Python
# ---------------------------------------------------------------------------

def expr_padrao(no: A.No) -> str:
    if isinstance(no, A.Nota):
        return f'nota("{no.texto}")'
    if isinstance(no, A.Som):
        return f'som("{no.nome}")'
    if isinstance(no, A.Pausa):
        return "silencio()"
    if isinstance(no, A.Sequencia):
        partes = [expr_padrao(p) for p in no.passos]
        return partes[0] if len(partes) == 1 else f"seq({', '.join(partes)})"
    if isinstance(no, A.Camadas):
        partes = [expr_padrao(s) for s in no.sequencias]
        return partes[0] if len(partes) == 1 else f"stack({', '.join(partes)})"
    if isinstance(no, A.Alterna):
        return f"alterna({', '.join(expr_padrao(p) for p in no.passos)})"
    if isinstance(no, A.Rapido):
        return f"rapido({no.fator.texto}, {expr_padrao(no.alvo)})"
    if isinstance(no, A.Lento):
        return f"lento({no.fator.texto}, {expr_padrao(no.alvo)})"
    raise TypeError(f"nó inesperado na mini-notação: {type(no).__name__}")


def expr_transformacao(t: A.Transformacao, interna: str) -> str:
    if t.argumento is None:
        return f"{t.nome}({interna})"
    return f"{t.nome}({t.argumento.texto}, {interna})"


# ---------------------------------------------------------------------------
# Programa -> script
# ---------------------------------------------------------------------------

def _runtime_embutido() -> str:
    partes = []
    for caminho in ARQUIVOS_RUNTIME:
        partes.append(f"# {'=' * 70}\n# runtime/{caminho.name}\n# {'=' * 70}\n")
        partes.append(caminho.read_text(encoding="utf-8"))
    return "\n".join(partes)


def gerar_programa(prog: A.Programa, tab: TabelaSimbolos, nome_fonte: str = "<entrada>") -> List[str]:
    """Só o código traduzido (sem o runtime)."""
    L = [f"# {'=' * 70}",
         f"# Código gerado a partir de {nome_fonte}",
         f"# {'=' * 70}",
         "",
         f"BPM = {tab.bpm}"]
    t = tab.tocar
    L.append(f"CICLOS = {int(t.ciclos.valor)}")

    decls = prog.declaracoes
    instrumentos = [d for d in decls if isinstance(d, A.Instrumento)]
    padroes = [d for d in decls if isinstance(d, A.DefPadrao)]
    faixas = [d for d in decls if isinstance(d, A.Faixa)]

    if instrumentos:
        L += ["", "# --- instrumentos ---"]
        for d in instrumentos:
            info = tab.instrumentos[d.nome]
            L.append(f"# linha {d.pos.linha}: instrumento {d.nome}")
            L.append(f'i_{d.nome} = Instrumento("{info.onda}", {info.volume})')

    if padroes:
        L += ["", "# --- padrões ---"]
        for d in padroes:
            L.append(f"# linha {d.pos.linha}: padrao {d.nome}")
            L.append(f"p_{d.nome} = {expr_padrao(d.padrao)}")

    L += ["", "# --- faixas ---", "faixas = []"]
    for f in faixas:
        fonte = f.fonte
        expr = f"p_{fonte.ref.nome}" if fonte.ref is not None else expr_padrao(fonte.padrao)
        for tr in f.transformacoes:          # associativas à esquerda
            expr = expr_transformacao(tr, expr)
        instr = f"i_{fonte.instrumento.nome}" if fonte.instrumento is not None else "None"
        L.append(f"# linha {f.pos.linha}: faixa {f.nome}")
        L.append(f"f_{f.nome} = {expr}")
        L.append(f'faixas.append(Faixa("{f.nome}", f_{f.nome}, {instr}))')
    return L


def gerar(prog: A.Programa, tab: TabelaSimbolos, *, nome_fonte: str = "<entrada>",
          reproduzir: bool = True, arquivo_padrao: str = "saida.wav",
          embutir_runtime: bool = True) -> str:
    t = tab.tocar
    arquivo = repr(t.arquivo) if t.arquivo else "None"
    L = []
    if embutir_runtime:
        L += ["# Script gerado pelo compilador da DSL musical — não edite à mão.",
              "# Contém o runtime embutido, seguido do programa traduzido.", "",
              _runtime_embutido(), ""]
    L += gerar_programa(prog, tab, nome_fonte)
    L += ["", f"# linha {t.pos.linha}: tocar",
          f"tocar(faixas, bpm=BPM, ciclos=CICLOS, arquivo={arquivo}, "
          f"reproduzir={reproduzir}, arquivo_padrao={arquivo_padrao!r})", ""]
    return "\n".join(L)
