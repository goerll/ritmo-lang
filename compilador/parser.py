"""Análise léxica + sintática (Lark, LALR(1)) e construção da AST."""

import re
from pathlib import Path

from lark import Lark, Token, Transformer, v_args
from lark.exceptions import UnexpectedCharacters, UnexpectedEOF, UnexpectedToken, VisitError
from lark.lexer import PatternStr

from . import ast_nos as A
from .erros import ErroCompilacao, ErroLexico, ErroSintatico

CAMINHO_GRAMATICA = Path(__file__).resolve().parent.parent / "gramatica.lark"

_lark = None


def obter_lark() -> Lark:
    global _lark
    if _lark is None:
        _lark = Lark(
            CAMINHO_GRAMATICA.read_text(encoding="utf-8"),
            start="programa",
            parser="lalr",
            lexer="contextual",
            propagate_positions=True,
            maybe_placeholders=True,
        )
    return _lark


# ---------------------------------------------------------------------------
# Lark (árvore concreta) -> AST
# ---------------------------------------------------------------------------

def _pos_tok(tok: Token) -> A.Pos:
    return A.Pos(tok.line, tok.column, len(tok))


def _pos_meta(meta) -> A.Pos:
    if getattr(meta, "empty", True):
        return A.Pos(0, 0, 1)
    if meta.line == meta.end_line:
        comprimento = meta.end_column - meta.column
    else:
        comprimento = 1
    return A.Pos(meta.line, meta.column, comprimento)


def _num(tok: Token) -> A.Numero:
    return A.Numero(str(tok), _pos_tok(tok))


RESERVADAS = {"tempo", "instrumento", "onda", "volume", "padrao", "faixa",
              "com", "tocar", "ciclos", "salvar"}
_RE_NOTA = re.compile(r"[a-g](#|b)?[0-9]")
_SONS = {"bd", "sd", "hh", "oh", "cp"}


def _id(tok: Token) -> str:
    """Garante a regra léxica "reservadas, NOTA e SOM têm prioridade sobre ID".

    O lexer contextual do Lark só considera os terminais válidos no estado atual,
    então onde a gramática espera um ID ele aceitaria 'tocar' ou 'bd' como nome.
    """
    nome = str(tok)
    if nome in RESERVADAS:
        motivo = "é palavra reservada"
    elif nome in _SONS:
        motivo = "é um som de bateria"
    elif _RE_NOTA.fullmatch(nome):
        motivo = "é uma nota"
    else:
        return nome
    raise ErroSintatico(f"'{nome}' {motivo} e não pode ser usado como identificador",
                        tok.line, tok.column, len(tok))


@v_args(meta=True)
class ConstrutorAST(Transformer):
    # ---- programa e declarações ----
    def programa(self, meta, filhos):
        return A.Programa(list(filhos), _pos_meta(meta))

    def cfg_tempo(self, meta, filhos):
        return A.Tempo(_num(filhos[0]), _pos_meta(meta))

    def def_instrumento(self, meta, filhos):
        nome, *props = filhos
        return A.Instrumento(_id(nome), props, _pos_tok(nome))

    def prop_onda(self, meta, filhos):
        return A.Propriedade("onda", str(filhos[0]), None, _pos_meta(meta))

    def prop_volume(self, meta, filhos):
        _, num = filhos
        return A.Propriedade("volume", str(num), _num(num), _pos_meta(meta))

    def def_padrao(self, meta, filhos):
        nome, camadas = filhos
        return A.DefPadrao(_id(nome), camadas, _pos_tok(nome))

    def faixa(self, meta, filhos):
        nome, fonte, *transf = filhos
        return A.Faixa(_id(nome), fonte, transf, _pos_tok(nome))

    def fonte(self, meta, filhos):
        conteudo, instr = filhos
        padrao = ref = None
        if isinstance(conteudo, Token):
            ref = A.Ref(_id(conteudo), _pos_tok(conteudo))
            pos = ref.pos
        else:
            padrao = conteudo
            pos = conteudo.pos
        instrumento = A.Ref(_id(instr), _pos_tok(instr)) if instr is not None else None
        return A.Fonte(padrao, ref, instrumento, pos)

    def nome_transf(self, meta, filhos):
        return filhos[0]

    def transformacao(self, meta, filhos):
        nome, arg = filhos
        argumento = _num(arg) if arg is not None else None
        return A.Transformacao(str(nome), argumento, _pos_tok(nome))

    def tocar(self, meta, filhos):
        num, arquivo = filhos
        caminho = str(arquivo)[1:-1] if arquivo is not None else None
        return A.Tocar(_num(num), caminho, _pos_meta(meta))

    # ---- mini-notação ----
    def padrao(self, meta, filhos):
        return filhos[0]

    def camadas(self, meta, filhos):
        return A.Camadas(list(filhos), _pos_meta(meta))

    def sequencia(self, meta, filhos):
        return A.Sequencia(list(filhos), _pos_meta(meta))

    def passo(self, meta, filhos):
        no, *mods = filhos
        for tipo, args, pos in mods:
            if tipo == "rapido":
                no = A.Rapido(args[0], no, pos)
            elif tipo == "lento":
                no = A.Lento(args[0], no, pos)
        return no

    def mod_rapido(self, meta, filhos):
        return ("rapido", [_num(filhos[0])], _pos_meta(meta))

    def mod_lento(self, meta, filhos):
        return ("lento", [_num(filhos[0])], _pos_meta(meta))

    def nota(self, meta, filhos):
        return A.Nota(str(filhos[0]), _pos_tok(filhos[0]))

    def som(self, meta, filhos):
        return A.Som(str(filhos[0]), _pos_tok(filhos[0]))

    def pausa(self, meta, filhos):
        return A.Pausa(_pos_meta(meta))

    def grupo(self, meta, filhos):
        return filhos[0]

    def alterna(self, meta, filhos):
        return A.Alterna(filhos[0].passos, _pos_meta(meta))


# ---------------------------------------------------------------------------
# Mensagens de erro amigáveis
# ---------------------------------------------------------------------------

_NOMES_TERMINAIS = {
    "NOTA": "nota (ex.: c4)",
    "SOM": "som de bateria (bd sd hh oh cp)",
    "ONDA": "onda (senoide quadrada serra triangulo)",
    "NUMERO": "número",
    "STRING": "string",
    "ID": "identificador",
    "VOLUME": "'volume'",
    "$END": "fim do arquivo",
}


def _nome_terminal(nome: str) -> str:
    if nome in _NOMES_TERMINAIS:
        return _NOMES_TERMINAIS[nome]
    try:
        term = obter_lark().get_terminal(nome)
        if isinstance(term.pattern, PatternStr):
            return f"'{term.pattern.value}'"
    except KeyError:
        pass
    return nome


def _descrever_token(tok: Token) -> str:
    if tok.type == "$END":
        return "fim do arquivo"
    tipo = _NOMES_TERMINAIS.get(tok.type)
    if tipo and not tipo.startswith("'"):
        return f"'{tok}' ({tipo.split(' (')[0]})"
    return f"'{tok}'"


def _posicao_fim(fonte: str):
    linhas = fonte.splitlines() or [""]
    return len(linhas), len(linhas[-1]) + 1


def _converter_erro_lark(e, fonte: str) -> ErroCompilacao:
    if isinstance(e, UnexpectedCharacters):
        ch = fonte[e.pos_in_stream] if e.pos_in_stream < len(fonte) else "?"
        if ch == '"':
            return ErroLexico("string não terminada (falta o '\"' de fechamento)",
                              e.line, e.column)
        return ErroLexico(f"caractere inesperado {ch!r}", e.line, e.column)

    if isinstance(e, (UnexpectedToken, UnexpectedEOF)):
        tok = getattr(e, "token", None)
        terminais = set(e.expected)
        ip = getattr(e, "interactive_parser", None)
        if ip is not None:
            try:  # conjunto exato (o LALR pode reduzir por padrão e "esperar" demais)
                terminais = ip.accepts() or terminais
            except Exception:
                pass
        esperados = sorted({_nome_terminal(t) for t in terminais})
        esperado = ", ".join(esperados)
        if tok is None or tok.type == "$END":
            linha, coluna = _posicao_fim(fonte)
            return ErroSintatico(f"fim inesperado do arquivo; esperado: {esperado}",
                                 linha, coluna)
        dica = None
        if "SEMICOLON" in terminais and tok.column == 1:
            dica = "faltou ';' no fim da linha anterior?"
        elif tok.type == "ID" and "NOTA" in terminais:
            dica = ("dentro da mini-notação só valem notas, sons, '~', '[ ]' e '< >'; "
                    "separe os passos com espaços")
        elif tok.type == "ID" and "ONDA" in terminais:
            dica = "ondas válidas: senoide, quadrada, serra, triangulo"
        return ErroSintatico(f"token inesperado {_descrever_token(tok)}; esperado: {esperado}",
                             tok.line, tok.column, len(tok), dica)

    return ErroSintatico(str(e))


def analisar(fonte: str) -> A.Programa:
    """Fonte (texto) -> AST. Lança ErroLexico/ErroSintatico."""
    try:
        arvore = obter_lark().parse(fonte)
    except (UnexpectedCharacters, UnexpectedToken, UnexpectedEOF) as e:
        raise _converter_erro_lark(e, fonte) from None
    try:
        return ConstrutorAST().transform(arvore)
    except VisitError as e:
        raise e.orig_exc from None


def arvore_concreta(fonte: str) -> str:
    """Árvore de derivação do Lark (útil para comparar com a AST)."""
    return obter_lark().parse(fonte).pretty()
