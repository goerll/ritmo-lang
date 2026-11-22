from fractions import Fraction as F

from runtime.padroes import (alterna, lento, nota, rapido, reverso,
                             seq, silencio, som, stack, transpor, volume)


def spans(p, a=0, b=1):
    return [(e.inicio, e.fim, e.valor.nome) for e in p.query(a, b)]


def test_pure_ocupa_ciclo_inteiro():
    assert spans(som("bd"), 0, 3) == [(0, 1, "bd"), (1, 2, "bd"), (2, 3, "bd")]


def test_consulta_por_onset():
    # evento do ciclo 0 começa em 0, fora de [0.5, 1.5); o do ciclo 1 começa em 1
    assert spans(som("bd"), F(1, 2), F(3, 2)) == [(1, 2, "bd")]


def test_silencio():
    assert silencio().query(0, 4) == []


def test_seq_divide_o_ciclo():
    p = seq(som("bd"), silencio(), som("sd"), silencio())
    assert spans(p) == [(0, F(1, 4), "bd"), (F(1, 2), F(3, 4), "sd")]


def test_seq_aninhada():
    p = seq(nota("c4"), seq(nota("g4"), nota("a4")))
    assert spans(p) == [(0, F(1, 2), "c4"), (F(1, 2), F(3, 4), "g4"), (F(3, 4), 1, "a4")]


def test_stack_sobrepoe():
    p = stack(som("bd"), seq(som("hh"), som("hh")))
    assert sorted(spans(p)) == [(0, F(1, 2), "hh"), (0, 1, "bd"), (F(1, 2), 1, "hh")]


def test_alterna_um_filho_por_ciclo():
    p = alterna(nota("b4"), nota("c5"))
    assert [v for _, _, v in spans(p, 0, 4)] == ["b4", "c5", "b4", "c5"]


def test_alterna_aninhada():
    p = alterna(som("bd"), alterna(som("sd"), som("cp")))
    assert [v for _, _, v in spans(p, 0, 4)] == ["bd", "sd", "bd", "cp"]


def test_alterna_dentro_de_seq():
    p = seq(nota("c4"), alterna(nota("b4"), nota("c5")))
    assert spans(p, 0, 2) == [(0, F(1, 2), "c4"), (F(1, 2), 1, "b4"),
                              (1, F(3, 2), "c4"), (F(3, 2), 2, "c5")]


def test_rapido():
    assert spans(rapido(4, som("hh"))) == [(F(i, 4), F(i + 1, 4), "hh") for i in range(4)]


def test_rapido_fracionario():
    assert len(rapido(1.5, som("hh")).query(0, 2)) == 3


def test_lento():
    p = lento(2, seq(som("bd"), som("sd")))
    assert spans(p, 0, 2) == [(0, 1, "bd"), (1, 2, "sd")]


def test_reverso():
    p = reverso(seq(nota("c4"), nota("e4"), nota("g4")))
    assert [v for _, _, v in spans(p)] == ["g4", "e4", "c4"]
    assert spans(p)[0][:2] == (0, F(1, 3))


def test_reverso_no_segundo_ciclo():
    p = reverso(seq(som("bd"), silencio(), silencio(), silencio()))
    assert spans(p, 1, 2) == [(F(7, 4), 2, "bd")]


def test_transpor_e_volume():
    p = volume(0.5, transpor(12, nota("c4")))
    e = p.query(0, 1)[0]
    assert e.valor.midi == 72 and e.valor.ganho == 0.5


def test_transpor_ignora_bateria():
    assert transpor(5, som("bd")).query(0, 1)[0].valor.midi is None

