from fractions import Fraction as F
from pathlib import Path

import numpy as np

from compilador.gerador import gerar, gerar_programa
from compilador.parser import analisar
from compilador.semantico import analisar_semantica

EXEMPLOS = Path(__file__).parent.parent / "exemplos"


def traduzir(src):
    prog = analisar(src)
    r = analisar_semantica(prog)
    return "\n".join(gerar_programa(prog, r.tabela))


def test_codigo_espelha_a_estrutura():
    codigo = traduzir((EXEMPLOS / "demo.ritmo").read_text())
    assert ('f_baixo = lento(2, seq(nota("c2"), silencio(), nota("c2"), '
            'alterna(nota("eb2"), nota("g2"))))') in codigo
    assert 'faixas.append(Faixa("baixo", f_baixo, i_grave))' in codigo
    assert 'p_groove = stack(seq(som("bd"), silencio(), som("sd"), silencio()), rapido(8, som("hh")))' in codigo


def test_transformacoes_aplicadas_em_ordem():
    codigo = traduzir("faixa a: nota [c4] .transpor(12) .volume(0.6);\ntocar 1 ciclos;")
    assert 'f_a = volume(0.6, transpor(12, nota("c4")))' in codigo


def test_modificadores_aninhados():
    codigo = traduzir("faixa a: bateria [bd [sd hh]*2/3];\ntocar 1 ciclos;")
    assert 'seq(som("bd"), lento(3, rapido(2, seq(som("sd"), som("hh")))))' in codigo


def test_script_autocontido_executa(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    src = "tempo 240;\ninstrumento x { onda serra; volume 0.5; }\n" \
          "faixa a: nota [c4 e4] com x;\nfaixa b: bateria [bd sd];\ntocar 2 ciclos salvar \"t.wav\";"
    prog = analisar(src)
    r = analisar_semantica(prog)
    codigo = gerar(prog, r.tabela, reproduzir=False)
    escopo = {"__name__": "__main__"}
    exec(compile(codigo, "<teste>", "exec"), escopo)

    assert (tmp_path / "t.wav").exists()
    eventos = escopo["f_a"].query(0, 2)
    assert [(e.inicio, e.valor.nome) for e in eventos] == \
        [(0, "c4"), (F(1, 2), "e4"), (1, "c4"), (F(3, 2), "e4")]

    import wave
    with wave.open(str(tmp_path / "t.wav")) as w:
        assert w.getframerate() == 44100 and w.getnchannels() == 1
        dados = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    assert np.abs(dados).max() > 1000                 # tem som
    assert np.abs(dados).max() <= 32767 * 0.9 + 1     # normalizado, sem clipping
