"""Exceções do compilador com posição (linha:coluna) e trecho do código."""

from typing import List, Optional


class ErroCompilacao(Exception):
    tipo = "erro"

    def __init__(self, mensagem: str, linha: int = 0, coluna: int = 0,
                 comprimento: int = 1, dica: Optional[str] = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.linha = linha
        self.coluna = coluna
        self.comprimento = max(1, comprimento)
        self.dica = dica

    def formatar(self, fonte: str = "", arquivo: str = "<entrada>") -> str:
        return formatar_mensagem(self.tipo, self.mensagem, self.linha, self.coluna,
                                 self.comprimento, fonte, arquivo, self.dica)

    def __str__(self):
        return f"{self.tipo} [{self.linha}:{self.coluna}]: {self.mensagem}"


class ErroLexico(ErroCompilacao):
    tipo = "erro léxico"


class ErroSintatico(ErroCompilacao):
    tipo = "erro sintático"


class ErroSemantico(ErroCompilacao):
    tipo = "erro semântico"


class ErrosSemanticos(Exception):
    """Agrupa todos os erros semânticos encontrados numa compilação."""

    def __init__(self, erros: List[ErroSemantico]):
        super().__init__(f"{len(erros)} erro(s) semântico(s)")
        self.erros = sorted(erros, key=lambda e: (e.linha, e.coluna))

    def formatar(self, fonte: str = "", arquivo: str = "<entrada>") -> str:
        return "\n\n".join(e.formatar(fonte, arquivo) for e in self.erros)


class Aviso:
    tipo = "aviso"

    def __init__(self, mensagem: str, linha: int = 0, coluna: int = 0, comprimento: int = 1):
        self.mensagem = mensagem
        self.linha = linha
        self.coluna = coluna
        self.comprimento = max(1, comprimento)

    def formatar(self, fonte: str = "", arquivo: str = "<entrada>") -> str:
        return formatar_mensagem(self.tipo, self.mensagem, self.linha, self.coluna,
                                 self.comprimento, fonte, arquivo)

    def __str__(self):
        return f"aviso [{self.linha}:{self.coluna}]: {self.mensagem}"


def formatar_mensagem(tipo, mensagem, linha, coluna, comprimento, fonte, arquivo, dica=None) -> str:
    """Formata no estilo:

        demo.ritmo:3:24: erro semântico: instrumento 'xpto' não declarado
           3 | faixa a: [c4] com xpto;
             |                        ^^^^
    """
    if linha <= 0:
        cab = f"{arquivo}: {tipo}: {mensagem}"
        return cab + (f"\n  dica: {dica}" if dica else "")

    cab = f"{arquivo}:{linha}:{coluna}: {tipo}: {mensagem}"
    linhas = fonte.splitlines()
    if not (1 <= linha <= len(linhas)):
        return cab + (f"\n  dica: {dica}" if dica else "")

    texto = linhas[linha - 1].expandtabs(4)
    num = str(linha)
    margem = " " * len(num)
    disponivel = max(1, len(texto) - (coluna - 1))
    marca = "^" * min(comprimento, disponivel)
    saida = [
        cab,
        f" {num} | {texto}",
        f" {margem} | {' ' * (coluna - 1)}{marca}",
    ]
    if dica:
        saida.append(f" {margem} = dica: {dica}")
    return "\n".join(saida)
