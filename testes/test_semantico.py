from pathlib import Path

import pytest

from compilador.erros import ErroLexico, ErroSintatico, ErrosSemanticos
from compilador.parser import analisar
from compilador.semantico import analisar_semantica

EXEMPLOS = Path(__file__).parent.parent / "exemplos"


def compilar(src):
    return analisar_semantica(analisar(src))


def mensagens_erro(src):
    with pytest.raises(ErrosSemanticos) as e:
        compilar(src)
    return [x.mensagem for x in e.value.erros]


# Cada arquivo de exemplos/erros deve falhar com a mensagem esperada.
ESPERADO = {
    "lexico_caractere": (ErroLexico, "caractere inesperado"),
    "lexico_string": (ErroLexico, "string não terminada"),
    "sintatico_ponto_virgula": (ErroSintatico, "token inesperado 'tocar'"),
    "sintatico_colchete": (ErroSintatico, "token inesperado ';'"),
    "sintatico_sem_espaco": (ErroSintatico, "c4e4"),
    "sem_instrumento_nao_declarado": (ErrosSemanticos, "instrumento 'piano' não declarado"),
    "sem_padrao_nao_declarado": (ErrosSemanticos, "padrão 'groove' não declarado"),
    "sem_duplicidade": (ErrosSemanticos, "declarado em duplicidade"),
    "sem_padrao_misto": (ErrosSemanticos, "mistura notas e sons"),
    "sem_com_em_bateria": (ErrosSemanticos, "'com instrumento' não pode"),
    "sem_transformacao_desconhecida": (ErrosSemanticos, "transformação desconhecida"),
    "sem_aridade": (ErrosSemanticos, "não recebe argumento"),
    "sem_argumento_invalido": (ErrosSemanticos, "'*0'"),
    "sem_transpor_nao_inteiro": (ErrosSemanticos, "inteiro de semitons"),
    "sem_propriedade_repetida": (ErrosSemanticos, "propriedade 'volume' repetida"),
    "sem_tempo_duplicado": (ErrosSemanticos, "mais de uma vez"),
    "sem_tempo_e_ciclos_invalidos": (ErrosSemanticos, "tempo deve ser > 0"),
    "sem_sem_tocar": (ErrosSemanticos, "'tocar' ausente"),
    "sem_dois_tocar": (ErrosSemanticos, "mais de um comando 'tocar'"),
    "sem_sem_faixa": (ErrosSemanticos, "nenhuma faixa"),
}


def test_todo_arquivo_de_erro_tem_expectativa():
    arquivos = {p.stem for p in (EXEMPLOS / "erros").glob("*.ritmo")}
    assert arquivos == set(ESPERADO)


@pytest.mark.parametrize("nome", sorted(ESPERADO))
def test_exemplos_de_erro(nome):
    classe, trecho = ESPERADO[nome]
    src = (EXEMPLOS / "erros" / f"{nome}.ritmo").read_text()
    with pytest.raises(classe) as e:
        compilar(src)
    texto = e.value.formatar(src, nome)
    assert trecho in texto


@pytest.mark.parametrize("nome", ["demo", "bateria", "polifonia"])
def test_exemplos_validos(nome):
    compilar((EXEMPLOS / f"{nome}.ritmo").read_text())


def test_erros_tem_linha_e_coluna():
    with pytest.raises(ErrosSemanticos) as e:
        compilar("tempo 120;\nfaixa a: [c4] com xpto;\ntocar 1 ciclos;")
    err = e.value.erros[0]
    assert (err.linha, err.coluna, err.comprimento) == (2, 19, 4)


def test_coleta_varios_erros():
    msgs = mensagens_erro("tempo -1;\nfaixa a: [bd*0] .rapido(0) .volume(2);\ntocar 1.5 ciclos;")
    assert len(msgs) == 5


def test_padrao_nomeado_define_o_tipo_da_faixa():
    prog = analisar("padrao m = [c4 e4];\nfaixa a: m;\ntocar 1 ciclos;")
    analisar_semantica(prog)
    assert prog.declaracoes[1].fonte.tipo == "nota"


def test_padrao_so_de_pausas_vale_para_ambos():
    compilar("padrao p = [~ ~];\nfaixa a: p;\nfaixa b: p;\ntocar 1 ciclos;")


def test_transpor_em_som_e_erro():
    msgs = mensagens_erro("faixa a: [bd] .transpor(2);\ntocar 1 ciclos;")
    assert any("não se aplica" in m for m in msgs)


# ---- tipo da faixa inferido do conteúdo ----

def tipo_inferido(src, indice=0):
    prog = analisar(src)
    analisar_semantica(prog)
    faixas = [d for d in prog.declaracoes if type(d).__name__ == "Faixa"]
    return faixas[indice].fonte.tipo


def test_tipo_inferido_bateria():
    assert tipo_inferido("faixa a: [bd ~ sd ~];\ntocar 1 ciclos;") == "bateria"


def test_tipo_inferido_nota():
    src = "instrumento lead { onda serra; }\nfaixa m: [c4 e4] com lead;\ntocar 1 ciclos;"
    assert tipo_inferido(src) == "nota"


def test_tipo_inferido_de_padrao_declarado_depois():
    src = "faixa r: riff;\npadrao riff = [bd sd];\ntocar 1 ciclos;"
    assert tipo_inferido(src) == "bateria"


def test_faixa_so_de_pausas_e_aceita():
    assert tipo_inferido("faixa s: [~ ~];\ntocar 1 ciclos;") is None


def test_pausas_aceitam_com_e_transpor():
    compilar("instrumento lead { onda serra; }\nfaixa s: [~ ~] com lead .transpor(12);\ntocar 1 ciclos;")


def test_com_em_padrao_de_bateria_e_erro():
    msgs = mensagens_erro("instrumento lead { onda serra; }\nfaixa b: [bd sd] com lead;\ntocar 1 ciclos;")
    assert "'com instrumento' não pode ser usado: o padrão da faixa 'b' contém sons de bateria" in msgs


def test_transpor_em_padrao_de_bateria_e_erro():
    msgs = mensagens_erro("faixa t: [bd sd] .transpor(12);\ntocar 1 ciclos;")
    assert "'.transpor' não se aplica: o padrão da faixa 't' contém sons de bateria" in msgs


def test_padrao_misto_na_faixa_e_erro():
    msgs = mensagens_erro("faixa a: [c4 bd];\ntocar 1 ciclos;")
    assert any("mistura notas e sons de bateria" in m for m in msgs)


def test_referencia_nao_declarada_so_da_erro_de_declaracao():
    msgs = mensagens_erro("faixa a: groove com lead;\ninstrumento lead { onda serra; }\ntocar 1 ciclos;")
    assert msgs == ["padrão 'groove' não declarado"]


def test_nota_e_bateria_nao_sao_mais_reservadas():
    r = compilar("padrao nota = [c4];\npadrao bateria = [bd];\n"
                 "faixa a: nota;\nfaixa b: bateria;\ntocar 1 ciclos;")
    assert r.tabela.padroes["nota"].tipo == "nota"
    assert r.tabela.padroes["bateria"].tipo == "bateria"


def test_uso_antes_da_declaracao_e_permitido():
    compilar("faixa a: m com x;\ninstrumento x { onda serra; }\npadrao m = [c4];\ntocar 1 ciclos;")


def test_avisos():
    r = compilar("instrumento nao_usado { onda serra; }\nfaixa a: [c4];\ntocar 1 ciclos;")
    textos = [a.mensagem for a in r.avisos]
    assert any("'tempo' ausente" in t for t in textos)
    assert any("nunca usado" in t for t in textos)
    assert any("sem 'com'" in t for t in textos)
    assert r.tabela.bpm == 120
