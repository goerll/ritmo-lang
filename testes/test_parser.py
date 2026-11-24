import pytest

from compilador import ast_nos as A
from compilador.erros import ErroLexico, ErroSintatico
from compilador.parser import analisar


def padrao_da_faixa(src):
    prog = analisar(src)
    faixa = [d for d in prog.declaracoes if isinstance(d, A.Faixa)][0]
    return faixa.fonte.padrao


def test_precedencia_virgula_justaposicao_posfixo():
    # bd sd*2, hh  ==  ( (bd (sd*2)) , hh )
    camadas = padrao_da_faixa("faixa a: [bd sd*2, hh];")
    assert isinstance(camadas, A.Camadas) and len(camadas.sequencias) == 2
    s1, s2 = camadas.sequencias
    assert isinstance(s1.passos[0], A.Som)
    assert isinstance(s1.passos[1], A.Rapido) and s1.passos[1].alvo.nome == "sd"
    assert s2.passos[0].nome == "hh"


def test_modificadores_encadeados_associam_a_esquerda():
    passo = padrao_da_faixa("faixa a: [bd*2/3];").sequencias[0].passos[0]
    assert isinstance(passo, A.Lento) and isinstance(passo.alvo, A.Rapido)


def test_subgrupo_e_alternancia():
    seq = padrao_da_faixa("faixa a: [c4 [g4 a4] <b4 c5>];").sequencias[0]
    assert isinstance(seq.passos[1], A.Camadas)
    assert isinstance(seq.passos[2], A.Alterna) and len(seq.passos[2].passos) == 2


@pytest.mark.parametrize("texto,midi", [("c4", 60), ("a4", 69), ("b3", 59),
                                        ("bb3", 58), ("f#5", 78), ("eb2", 39)])
def test_notas(texto, midi):
    nota = padrao_da_faixa(f"faixa a: [{texto}];").sequencias[0].passos[0]
    assert isinstance(nota, A.Nota) and nota.texto == texto and nota.midi == midi


def test_bd_e_som_nao_nota():
    som = padrao_da_faixa("faixa a: [bd];").sequencias[0].passos[0]
    assert isinstance(som, A.Som)


def test_extras_removidos_sao_erro_sintatico():
    for src in ("faixa a: [bd(3,8)];", "faixa a: [bd!3];"):
        with pytest.raises((ErroSintatico, ErroLexico)):
            analisar(src)


def test_transformacoes_incluindo_volume_reservada():
    prog = analisar("faixa a: [c4] .lento(2) .transpor(-12) .volume(0.6) .reverso();")
    nomes = [t.nome for t in prog.declaracoes[0].transformacoes]
    assert nomes == ["lento", "transpor", "volume", "reverso"]
    assert prog.declaracoes[0].transformacoes[1].argumento.valor == -12


def test_comentarios_ignorados():
    prog = analisar("// cabeçalho\ntempo 90; // fim de linha\n")
    assert len(prog.declaracoes) == 1 and prog.declaracoes[0].bpm.valor == 90


def test_programa_completo():
    from pathlib import Path
    src = (Path(__file__).parent.parent / "exemplos" / "demo.ritmo").read_text()
    prog = analisar(src)
    tipos = [type(d).__name__ for d in prog.declaracoes]
    assert tipos == ["Tempo", "Instrumento", "Instrumento", "DefPadrao",
                     "Faixa", "Faixa", "Faixa", "Tocar"]


def test_erro_lexico_posicao():
    with pytest.raises(ErroLexico) as e:
        analisar("tempo 120;\nfaixa a: [bd $];")
    assert (e.value.linha, e.value.coluna) == (2, 14)


def test_erro_sintatico_ponto_e_virgula():
    with pytest.raises(ErroSintatico) as e:
        analisar("tempo 120\nfaixa a: [bd];")
    assert (e.value.linha, e.value.coluna) == (2, 1)
    assert "';'" in e.value.mensagem


def test_palavra_reservada_nao_e_identificador():
    with pytest.raises(ErroSintatico):
        analisar("padrao tocar = [bd];")


def test_identificador_colado_nao_vira_nota():
    with pytest.raises(ErroSintatico) as e:
        analisar("faixa a: [c4e4];")
    assert "c4e4" in e.value.mensagem


def test_modificador_fora_dos_colchetes_e_erro():
    with pytest.raises(ErroSintatico):
        analisar("faixa a: [bd sd]*2;")


def test_nota_e_bateria_nao_sao_reservadas():
    prog = analisar("padrao nota = [c4];\nfaixa bateria: [bd];")
    assert prog.declaracoes[0].nome == "nota"
    assert prog.declaracoes[1].nome == "bateria"
    assert prog.declaracoes[1].fonte.tipo is None      # preenchido só pelo semântico


def test_palavra_reservada_e_som_continuam_rejeitados_como_id():
    with pytest.raises(ErroSintatico):
        analisar("faixa tocar: [bd];")
    with pytest.raises(ErroSintatico):
        analisar("faixa bd: [bd];")


def test_posicao_da_fonte_e_a_do_conteudo():
    ref = analisar("faixa a: riff;").declaracoes[0].fonte
    assert (ref.pos.linha, ref.pos.coluna) == (1, 10)
    lit = analisar("faixa a: [bd];").declaracoes[0].fonte
    assert lit.pos.linha == 1 and lit.pos.coluna >= 10
