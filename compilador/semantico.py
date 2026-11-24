"""Análise semântica: tabela de símbolos + verificações de tipo e de valores.

Todos os erros são coletados (não só o primeiro) e lançados juntos em
`ErrosSemanticos`. Avisos não interrompem a compilação.

Os espaços de nomes são separados por categoria (instrumentos, padrões e
faixas), já que cada um é usado num contexto sintático diferente.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import ast_nos as A
from .erros import Aviso, ErroSemantico, ErrosSemanticos

BPM_PADRAO = 120
ONDA_PADRAO = "senoide"
VOLUME_PADRAO = 0.8

# nome -> número de argumentos
TRANSFORMACOES = {"rapido": 1, "lento": 1, "reverso": 0, "transpor": 1, "volume": 1}


@dataclass
class InfoInstrumento:
    no: A.Instrumento
    onda: str = ONDA_PADRAO
    volume: float = VOLUME_PADRAO
    usado: bool = False


@dataclass
class InfoPadrao:
    no: A.DefPadrao
    tipo: Optional[str]          # "nota", "bateria" ou None (só pausas)
    usado: bool = False


@dataclass
class TabelaSimbolos:
    bpm: float = BPM_PADRAO
    instrumentos: Dict[str, InfoInstrumento] = field(default_factory=dict)
    padroes: Dict[str, InfoPadrao] = field(default_factory=dict)
    faixas: Dict[str, A.Faixa] = field(default_factory=dict)
    tocar: Optional[A.Tocar] = None


@dataclass
class Resultado:
    tabela: TabelaSimbolos
    avisos: List[Aviso]


def _erro(msg, pos: A.Pos, dica=None) -> ErroSemantico:
    return ErroSemantico(msg, pos.linha, pos.coluna, pos.comprimento, dica)


def _aviso(msg, pos: A.Pos) -> Aviso:
    return Aviso(msg, pos.linha, pos.coluna, pos.comprimento)


class Analisador:
    def __init__(self):
        self.erros: List[ErroSemantico] = []
        self.avisos: List[Aviso] = []
        self.tab = TabelaSimbolos()

    # ------------------------------------------------------------------
    def analisar(self, prog: A.Programa) -> Resultado:
        tempos = [d for d in prog.declaracoes if isinstance(d, A.Tempo)]
        tocares = [d for d in prog.declaracoes if isinstance(d, A.Tocar)]

        # 1ª passada: declarações (permite usar antes de declarar)
        for d in prog.declaracoes:
            if isinstance(d, A.Instrumento):
                self._declarar_instrumento(d)
            elif isinstance(d, A.DefPadrao):
                self._declarar_padrao(d)

        # tempo
        if not tempos:
            self.avisos.append(Aviso(f"'tempo' ausente; usando {BPM_PADRAO} BPM"))
        for t in tempos[1:]:
            self.erros.append(_erro("'tempo' declarado mais de uma vez", t.pos,
                                    f"a primeira declaração está na linha {tempos[0].pos.linha}"))
        if tempos:
            bpm = tempos[0].bpm
            if bpm.valor <= 0:
                self.erros.append(_erro(f"tempo deve ser > 0 (recebido {bpm.texto})", bpm.pos))
            else:
                self.tab.bpm = bpm.valor

        # 2ª passada: faixas
        for d in prog.declaracoes:
            if isinstance(d, A.Faixa):
                self._verificar_faixa(d)

        if not self.tab.faixas:
            self.erros.append(ErroSemantico("nenhuma faixa declarada",
                                            dica="declare ao menos uma: faixa x: [bd sd];"))

        # tocar
        if not tocares:
            self.erros.append(ErroSemantico("comando 'tocar' ausente",
                                            dica="termine o programa com: tocar 4 ciclos;"))
        for t in tocares[1:]:
            self.erros.append(_erro("mais de um comando 'tocar'", t.pos,
                                    f"o primeiro está na linha {tocares[0].pos.linha}"))
        if tocares:
            self._verificar_tocar(tocares[0])

        # avisos de símbolos não usados
        for nome, info in self.tab.instrumentos.items():
            if not info.usado:
                self.avisos.append(_aviso(f"instrumento '{nome}' declarado e nunca usado", info.no.pos))
        for nome, info in self.tab.padroes.items():
            if not info.usado:
                self.avisos.append(_aviso(f"padrão '{nome}' declarado e nunca usado", info.no.pos))

        if self.erros:
            raise ErrosSemanticos(self.erros)
        self.avisos.sort(key=lambda a: (a.linha, a.coluna))
        return Resultado(self.tab, self.avisos)

    # ------------------------------------------------------------------
    def _declarar_instrumento(self, d: A.Instrumento):
        if d.nome in self.tab.instrumentos:
            ant = self.tab.instrumentos[d.nome].no
            self.erros.append(_erro(f"instrumento '{d.nome}' declarado em duplicidade", d.pos,
                                    f"declarado antes na linha {ant.pos.linha}"))
            return
        info = InfoInstrumento(d)
        vistos = {}
        for p in d.propriedades:
            if p.nome in vistos:
                self.erros.append(_erro(f"propriedade '{p.nome}' repetida no instrumento '{d.nome}'",
                                        p.pos, f"já definida na linha {vistos[p.nome].pos.linha}"))
                continue
            vistos[p.nome] = p
            if p.nome == "onda":
                info.onda = p.valor
            elif p.nome == "volume":
                if not 0 <= p.numero.valor <= 1:
                    self.erros.append(_erro(f"volume deve estar em [0, 1] (recebido {p.valor})",
                                            p.numero.pos))
                info.volume = p.numero.valor
        if "onda" not in vistos:
            self.avisos.append(_aviso(f"instrumento '{d.nome}' sem 'onda'; usando {ONDA_PADRAO}", d.pos))
        self.tab.instrumentos[d.nome] = info

    def _declarar_padrao(self, d: A.DefPadrao):
        if d.nome in self.tab.padroes:
            ant = self.tab.padroes[d.nome].no
            self.erros.append(_erro(f"padrão '{d.nome}' declarado em duplicidade", d.pos,
                                    f"declarado antes na linha {ant.pos.linha}"))
            return
        tipo = self._tipo_padrao(d.padrao)
        self.tab.padroes[d.nome] = InfoPadrao(d, tipo)

    # ------------------------------------------------------------------
    def _tipo_padrao(self, raiz: A.No) -> Optional[str]:
        """Infere o tipo do padrão ("nota"/"bateria"/None) e valida os modificadores.

        Um padrão não pode misturar notas e sons de bateria.
        """
        folhas = []
        self._percorrer(raiz, folhas)
        tipo, primeira = None, None
        for f in folhas:
            t = "nota" if isinstance(f, A.Nota) else "bateria"
            if tipo is None:
                tipo, primeira = t, f
            elif t != tipo:
                nome = f.texto if isinstance(f, A.Nota) else f.nome
                desc = {"nota": "notas", "bateria": "sons de bateria"}
                ini = primeira.texto if isinstance(primeira, A.Nota) else primeira.nome
                self.erros.append(_erro(
                    f"padrão mistura {desc[tipo]} e {desc[t]}: '{nome}'", f.pos,
                    f"o padrão começou com '{ini}' (linha {primeira.pos.linha}, coluna {primeira.pos.coluna})"))
                break
        return tipo

    def _percorrer(self, no: A.No, folhas: list):
        if isinstance(no, (A.Nota, A.Som)):
            folhas.append(no)
            return
        if isinstance(no, (A.Rapido, A.Lento)):
            simb = "*" if isinstance(no, A.Rapido) else "/"
            if no.fator.valor <= 0:
                self.erros.append(_erro(f"'{simb}{no.fator.texto}': o fator deve ser > 0",
                                        no.fator.pos))
        for filho in no.filhos():
            self._percorrer(filho, folhas)

    # ------------------------------------------------------------------
    def _verificar_faixa(self, f: A.Faixa):
        if f.nome in self.tab.faixas:
            ant = self.tab.faixas[f.nome]
            self.erros.append(_erro(f"faixa '{f.nome}' declarada em duplicidade", f.pos,
                                    f"declarada antes na linha {ant.pos.linha}"))
        else:
            self.tab.faixas[f.nome] = f

        fonte = f.fonte
        # conteúdo: padrão literal ou referência
        if fonte.ref is not None:
            info = self.tab.padroes.get(fonte.ref.nome)
            if info is None:
                self.erros.append(_erro(f"padrão '{fonte.ref.nome}' não declarado", fonte.ref.pos))
                tipo = None
            else:
                info.usado = True
                tipo = info.tipo
        else:
            tipo = self._tipo_padrao(fonte.padrao)

        # o tipo da faixa é sempre o inferido do conteúdo (None = só pausas)
        fonte.tipo = tipo

        # instrumento
        if fonte.instrumento is not None:
            if tipo == "bateria":
                self.erros.append(_erro("'com instrumento' não pode ser usado: o padrão da faixa "
                                        f"'{f.nome}' contém sons de bateria",
                                        fonte.instrumento.pos,
                                        "a bateria é sintetizada; instrumentos só valem para notas"))
            info_i = self.tab.instrumentos.get(fonte.instrumento.nome)
            if info_i is None:
                self.erros.append(_erro(f"instrumento '{fonte.instrumento.nome}' não declarado",
                                        fonte.instrumento.pos))
            else:
                info_i.usado = True
        elif tipo == "nota":
            self.avisos.append(_aviso(
                f"faixa '{f.nome}' sem 'com'; usando instrumento padrão "
                f"({ONDA_PADRAO}, volume {VOLUME_PADRAO})", f.pos))

        for t in f.transformacoes:
            self._verificar_transformacao(t, f.nome, tipo)

    def _verificar_transformacao(self, t: A.Transformacao, nome_faixa: str,
                                 tipo_faixa: Optional[str]):
        if t.nome not in TRANSFORMACOES:
            self.erros.append(_erro(f"transformação desconhecida '.{t.nome}'", t.pos,
                                    "disponíveis: " + ", ".join(f".{n}" for n in TRANSFORMACOES)))
            return
        aridade = TRANSFORMACOES[t.nome]
        recebidos = 0 if t.argumento is None else 1
        if aridade != recebidos:
            esperado = "não recebe argumento" if aridade == 0 else "recebe exatamente 1 argumento"
            self.erros.append(_erro(f"'.{t.nome}' {esperado}", t.pos))
            return
        arg = t.argumento
        if t.nome in ("rapido", "lento") and arg.valor <= 0:
            self.erros.append(_erro(f"'.{t.nome}' exige valor > 0 (recebido {arg.texto})", arg.pos))
        elif t.nome == "volume" and not 0 <= arg.valor <= 1:
            self.erros.append(_erro(f"'.volume' exige valor em [0, 1] (recebido {arg.texto})", arg.pos))
        elif t.nome == "transpor":
            if not arg.inteiro or "." in arg.texto:
                self.erros.append(_erro(f"'.transpor' exige número inteiro de semitons "
                                        f"(recebido {arg.texto})", arg.pos))
            elif tipo_faixa == "bateria":
                self.erros.append(_erro("'.transpor' não se aplica: o padrão da faixa "
                                        f"'{nome_faixa}' contém sons de bateria", t.pos))

    def _verificar_tocar(self, t: A.Tocar):
        self.tab.tocar = t
        c = t.ciclos
        if c.valor <= 0:
            self.erros.append(_erro(f"número de ciclos deve ser > 0 (recebido {c.texto})", c.pos))
        elif not c.inteiro or "." in c.texto:
            self.erros.append(_erro(f"número de ciclos deve ser inteiro (recebido {c.texto})", c.pos))
        if t.arquivo is not None and not t.arquivo.lower().endswith(".wav"):
            self.avisos.append(_aviso(f"arquivo '{t.arquivo}' não termina em .wav; "
                                      "o formato gravado é WAV", t.pos))


def analisar_semantica(prog: A.Programa) -> Resultado:
    return Analisador().analisar(prog)
