"""Runtime — modelo de padrões (inspirado no TidalCycles).

Um *padrão* é uma função  consulta(inicio, fim) -> [Evento]  com o tempo
medido em ciclos (Fraction, para não acumular erro de arredondamento).

Simplificação em relação ao Tidal: uma consulta devolve os eventos cujo
INÍCIO (onset) está em [inicio, fim). Cada evento carrega a duração inteira,
então não é preciso lidar com fragmentos de eventos.

Este arquivo é embutido, tal como está, no script Python gerado.
"""

import math
from fractions import Fraction
from typing import Any, Callable, List, NamedTuple, Optional


def _frac(x) -> Fraction:
    if isinstance(x, Fraction):
        return x
    if isinstance(x, int):
        return Fraction(x)
    return Fraction(str(x))


class Valor(NamedTuple):
    tipo: str                    # "nota" | "som"
    nome: str                    # "c4", "bd", ...
    midi: Optional[int] = None   # só para notas
    ganho: float = 1.0           # multiplicador de amplitude (.volume)

    def transpor(self, semitons: int) -> "Valor":
        if self.tipo != "nota":
            return self
        return self._replace(midi=self.midi + semitons)

    def com_ganho(self, fator: float) -> "Valor":
        return self._replace(ganho=self.ganho * fator)


class Evento(NamedTuple):
    inicio: Fraction
    fim: Fraction
    valor: Any


class Padrao:
    def __init__(self, consulta: Callable[[Fraction, Fraction], List[Evento]]):
        self.consulta = consulta

    def query(self, inicio, fim) -> List[Evento]:
        a, b = _frac(inicio), _frac(fim)
        if a >= b:
            return []
        return sorted(self.consulta(a, b), key=lambda e: (e.inicio, e.fim))

    def __repr__(self):
        return f"<Padrao {self.query(0, 1)}>"


def _ciclos(a: Fraction, b: Fraction):
    """Índices dos ciclos que intersectam [a, b)."""
    return range(math.floor(a), math.ceil(b))


# ---------------------------------------------------------------------------
# Átomos
# ---------------------------------------------------------------------------

def pure(valor) -> Padrao:
    """Um evento ocupando cada ciclo inteiro."""
    def consulta(a, b):
        return [Evento(Fraction(c), Fraction(c + 1), valor)
                for c in _ciclos(a, b) if a <= c < b]
    return Padrao(consulta)


def silencio() -> Padrao:
    return Padrao(lambda a, b: [])


_SEMITOM = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}


def nome_para_midi(nome: str) -> int:
    semitom = _SEMITOM[nome[0]]
    resto = nome[1:]
    if resto[0] == "#":
        semitom, resto = semitom + 1, resto[1:]
    elif resto[0] == "b":
        semitom, resto = semitom - 1, resto[1:]
    return 12 * (int(resto) + 1) + semitom


def nota(nome: str) -> Padrao:
    return pure(Valor("nota", nome, nome_para_midi(nome)))


def som(nome: str) -> Padrao:
    return pure(Valor("som", nome))


# ---------------------------------------------------------------------------
# Combinadores de tempo
# ---------------------------------------------------------------------------

def rapido(fator, p: Padrao) -> Padrao:
    """Comprime o tempo por `fator` (x*n, .rapido(n))."""
    n = _frac(fator)
    if n <= 0:
        raise ValueError("rapido: fator deve ser > 0")

    def consulta(a, b):
        return [Evento(e.inicio / n, e.fim / n, e.valor) for e in p.consulta(a * n, b * n)]
    return Padrao(consulta)


def lento(fator, p: Padrao) -> Padrao:
    """Expande o tempo por `fator` (x/n, .lento(n))."""
    n = _frac(fator)
    if n <= 0:
        raise ValueError("lento: fator deve ser > 0")
    return rapido(1 / n, p)


def alterna(*ps: Padrao) -> Padrao:
    """<a b c>: no ciclo k toca o filho k mod n (slowcat).

    Cada filho "vê" apenas os ciclos em que está ativo, numerados 0, 1, 2...
    Assim <a <b c>> produz a b a c.
    """
    n = len(ps)

    def consulta(a, b):
        saida = []
        for c in _ciclos(a, b):
            filho = ps[c % n]
            desloc = c - c // n          # ciclo c do pai = ciclo c//n do filho
            ini = max(a, Fraction(c))
            fim = min(b, Fraction(c + 1))
            for e in filho.consulta(ini - desloc, fim - desloc):
                saida.append(Evento(e.inicio + desloc, e.fim + desloc, e.valor))
        return saida
    return Padrao(consulta)


def seq(*ps: Padrao) -> Padrao:
    """a b c: cada filho ocupa 1/n do ciclo (fastcat = rapido(n, alterna(...)))."""
    return rapido(len(ps), alterna(*ps))


def stack(*ps: Padrao) -> Padrao:
    """a, b: sobrepõe os eventos (polifonia)."""
    def consulta(a, b):
        saida = []
        for p in ps:
            saida.extend(p.consulta(a, b))
        return saida
    return Padrao(consulta)


def reverso(p: Padrao) -> Padrao:
    """Espelha os eventos dentro de cada ciclo."""
    def consulta(a, b):
        saida = []
        for c in _ciclos(a, b):
            eixo = 2 * c + 1                       # t -> (c+1) - (t-c)
            for e in p.consulta(Fraction(c), Fraction(c + 1)):
                fim = min(e.fim, Fraction(c + 1))  # eventos longos são cortados no ciclo
                novo = Evento(eixo - fim, eixo - e.inicio, e.valor)
                if a <= novo.inicio < b:
                    saida.append(novo)
        return saida
    return Padrao(consulta)


# ---------------------------------------------------------------------------
# Combinadores de valor
# ---------------------------------------------------------------------------

def fmap(f, p: Padrao) -> Padrao:
    return Padrao(lambda a, b: [e._replace(valor=f(e.valor)) for e in p.consulta(a, b)])


def transpor(semitons, p: Padrao) -> Padrao:
    n = int(semitons)
    return fmap(lambda v: v.transpor(n), p)


def volume(fator, p: Padrao) -> Padrao:
    x = float(fator)
    return fmap(lambda v: v.com_ganho(x), p)
