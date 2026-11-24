"""Nós da AST (árvore sintática abstrata).

Cada nó guarda a posição (linha, coluna) do trecho de código que o originou,
usada pelas mensagens de erro semântico. Os métodos `rotulo()` e `filhos()`
servem apenas para imprimir a árvore (`--mostrar-ast`).
"""

from dataclasses import dataclass, field
from typing import List, Optional, Union


@dataclass
class No:
    def rotulo(self) -> str:
        return type(self).__name__

    def filhos(self) -> list:
        return []


@dataclass
class Pos:
    linha: int = 0
    coluna: int = 0
    comprimento: int = 1


# ---------------------------------------------------------------------------
# Valores simples
# ---------------------------------------------------------------------------

@dataclass
class Numero(No):
    texto: str
    pos: Pos = field(default_factory=Pos)

    @property
    def valor(self) -> Union[int, float]:
        return float(self.texto) if "." in self.texto else int(self.texto)

    @property
    def inteiro(self) -> bool:
        return float(self.texto) == int(float(self.texto))

    def rotulo(self):
        return self.texto


@dataclass
class Ref(No):
    """Uso de um identificador (instrumento ou padrão)."""
    nome: str
    pos: Pos = field(default_factory=Pos)

    def rotulo(self):
        return f"Ref {self.nome}"


# ---------------------------------------------------------------------------
# Mini-notação
# ---------------------------------------------------------------------------

_SEMITOM = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}


def nota_para_midi(texto: str) -> int:
    letra, resto = texto[0], texto[1:]
    semitom = _SEMITOM[letra]
    if resto[0] == "#":
        semitom += 1
        resto = resto[1:]
    elif resto[0] == "b":
        semitom -= 1
        resto = resto[1:]
    return 12 * (int(resto) + 1) + semitom


@dataclass
class Nota(No):
    texto: str
    pos: Pos = field(default_factory=Pos)

    @property
    def midi(self) -> int:
        return nota_para_midi(self.texto)

    def rotulo(self):
        return f"Nota {self.texto} (midi {self.midi})"


@dataclass
class Som(No):
    nome: str
    pos: Pos = field(default_factory=Pos)

    def rotulo(self):
        return f"Som {self.nome}"


@dataclass
class Pausa(No):
    pos: Pos = field(default_factory=Pos)

    def rotulo(self):
        return "Pausa ~"


@dataclass
class Sequencia(No):
    passos: List[No]
    pos: Pos = field(default_factory=Pos)

    def filhos(self):
        return self.passos


@dataclass
class Camadas(No):
    sequencias: List[Sequencia]
    pos: Pos = field(default_factory=Pos)

    def filhos(self):
        return self.sequencias


@dataclass
class Alterna(No):
    passos: List[No]
    pos: Pos = field(default_factory=Pos)

    def rotulo(self):
        return "Alterna < >"

    def filhos(self):
        return self.passos


@dataclass
class Rapido(No):
    fator: Numero
    alvo: No
    pos: Pos = field(default_factory=Pos)

    def rotulo(self):
        return f"Rapido *{self.fator.texto}"

    def filhos(self):
        return [self.alvo]


@dataclass
class Lento(No):
    fator: Numero
    alvo: No
    pos: Pos = field(default_factory=Pos)

    def rotulo(self):
        return f"Lento /{self.fator.texto}"

    def filhos(self):
        return [self.alvo]


# ---------------------------------------------------------------------------
# Declarações
# ---------------------------------------------------------------------------

@dataclass
class Tempo(No):
    bpm: Numero
    pos: Pos = field(default_factory=Pos)

    def rotulo(self):
        return f"Tempo {self.bpm.texto} BPM"


@dataclass
class Propriedade(No):
    nome: str            # "onda" | "volume"
    valor: str           # nome da onda ou texto do número
    numero: Optional[Numero] = None
    pos: Pos = field(default_factory=Pos)

    def rotulo(self):
        return f"{self.nome} = {self.valor}"


@dataclass
class Instrumento(No):
    nome: str
    propriedades: List[Propriedade]
    pos: Pos = field(default_factory=Pos)

    def rotulo(self):
        return f"Instrumento {self.nome}"

    def filhos(self):
        return self.propriedades


@dataclass
class DefPadrao(No):
    nome: str
    padrao: Camadas
    pos: Pos = field(default_factory=Pos)

    def rotulo(self):
        return f"Padrao {self.nome}"

    def filhos(self):
        return [self.padrao]


@dataclass
class Transformacao(No):
    nome: str
    argumento: Optional[Numero]
    pos: Pos = field(default_factory=Pos)

    def rotulo(self):
        arg = self.argumento.texto if self.argumento else ""
        return f".{self.nome}({arg})"


@dataclass
class Fonte(No):
    padrao: Optional[Camadas]    # padrão literal ...
    ref: Optional[Ref]           # ... ou referência a um padrão nomeado
    instrumento: Optional[Ref]
    pos: Pos = field(default_factory=Pos)
    # tipo inferido do conteúdo pelo semântico: "nota", "bateria" ou None (só pausas)
    tipo: Optional[str] = None

    def rotulo(self):
        com = f" com {self.instrumento.nome}" if self.instrumento else ""
        tipo = self.tipo if self.tipo is not None else "pausas"
        return f"Fonte {tipo}{com}"

    def filhos(self):
        return [self.padrao if self.padrao is not None else self.ref]


@dataclass
class Faixa(No):
    nome: str
    fonte: Fonte
    transformacoes: List[Transformacao]
    pos: Pos = field(default_factory=Pos)

    def rotulo(self):
        return f"Faixa {self.nome}"

    def filhos(self):
        return [self.fonte] + self.transformacoes


@dataclass
class Tocar(No):
    ciclos: Numero
    arquivo: Optional[str]
    pos: Pos = field(default_factory=Pos)

    def rotulo(self):
        salvar = f' salvar "{self.arquivo}"' if self.arquivo else ""
        return f"Tocar {self.ciclos.texto} ciclos{salvar}"


@dataclass
class Programa(No):
    declaracoes: List[No]
    pos: Pos = field(default_factory=Pos)

    def filhos(self):
        return self.declaracoes


# ---------------------------------------------------------------------------
# Impressão da árvore
# ---------------------------------------------------------------------------

def formatar_arvore(no: No) -> str:
    linhas = [no.rotulo()]

    def visitar(n: No, prefixo: str):
        filhos = n.filhos()
        for i, filho in enumerate(filhos):
            ultimo = i == len(filhos) - 1
            linhas.append(prefixo + ("└── " if ultimo else "├── ") + filho.rotulo())
            visitar(filho, prefixo + ("    " if ultimo else "│   "))

    visitar(no, "")
    return "\n".join(linhas)
