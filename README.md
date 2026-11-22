# DSL Musical — compilador `.ritmo` → Python

Trabalho AV3 de Compiladores (IFC Blumenau). É um compilador para uma DSL de padrões musicais
no estilo Strudel/TidalCycles. Ele lê um arquivo `.ritmo`, traduz o programa para Python e
**executa na hora** (*one-step pipeline*): sintetiza o áudio, grava um `.wav` e toca.

```
// demo.ritmo
tempo 120;

instrumento lead  { onda quadrada; volume 0.5; }
instrumento grave { onda serra;    volume 0.7; }

padrao groove = [bd ~ sd ~, hh*8];

faixa percussao: bateria groove;
faixa baixo:   nota [c2 ~ c2 <eb2 g2>] com grave .lento(2);
faixa melodia: nota [c4 e4 [g4 a4] <b4 c5>] com lead .transpor(12) .volume(0.6);

tocar 8 ciclos salvar "demo.wav";
```

## Instalação e uso

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

```bash
python main.py exemplos/demo.ritmo                  # compila, gera o áudio e toca
python main.py exemplos/demo.ritmo --sem-tocar      # só gera o .wav
python main.py exemplos/demo.ritmo --mostrar-ast    # imprime a AST (e não executa)
python main.py exemplos/demo.ritmo --mostrar-arvore # árvore de derivação do Lark
python main.py exemplos/demo.ritmo --emitir out.py  # salva também o Python gerado
python -m pytest testes                             # testes
```

Sem `salvar`, o áudio só é tocado. Se o `sounddevice` não estiver disponível (ou com
`--sem-tocar`), ele é gravado em `<nome-do-fonte>.wav`.

## Arquitetura

```
fonte .ritmo ──► Lexer + Parser (Lark, LALR) ──► AST ──► Análise semântica ──► Gerador ──► script Python ──► exec
                 compilador/parser.py           ast_nos.py  semantico.py         gerador.py   (runtime embutido)
```

| Arquivo | Papel |
|---|---|
| [gramatica.lark](gramatica.lark) | Gramática formal (entregável); terminais e regras |
| [compilador/parser.py](compilador/parser.py) | Lark → AST (`Transformer`); traduz erros do Lark para PT com linha:coluna |
| [compilador/ast_nos.py](compilador/ast_nos.py) | Dataclasses dos nós e impressão da árvore |
| [compilador/semantico.py](compilador/semantico.py) | Tabela de símbolos, inferência de tipo dos padrões, validações |
| [compilador/gerador.py](compilador/gerador.py) | AST → chamadas aos combinadores do runtime |
| [compilador/erros.py](compilador/erros.py) | Exceções com posição e formatação com trecho do código |
| [runtime/padroes.py](runtime/padroes.py) | Modelo de padrões (`Fraction`, `Evento`, `seq`, `stack`, `alterna`…) |
| [runtime/sintese.py](runtime/sintese.py) | Osciladores, envelope, bateria sintetizada, mixagem, `.wav`, reprodução |
| [main.py](main.py) | CLI |

O **gerador não pré-calcula eventos**. Cada nó da AST vira uma chamada de combinador, então
o código gerado espelha a estrutura do programa. Por exemplo, `faixa baixo` vira:

```python
# linha 17: faixa baixo
f_baixo = lento(2, seq(nota("c2"), silencio(), nota("c2"), alterna(nota("eb2"), nota("g2"))))
faixas.append(Faixa("baixo", f_baixo, i_grave))
```

O script gerado é autocontido: tem o runtime embutido (cópia de `runtime/*.py`), seguido do
programa traduzido. Os nomes recebem prefixos (`i_`, `p_`, `f_`) para não colidir com o runtime.

## Gramática (EBNF)

```ebnf
programa        ::= { declaracao }
declaracao      ::= cfg_tempo | def_instrumento | def_padrao | faixa | tocar

cfg_tempo       ::= "tempo" NUMERO ";"
def_instrumento ::= "instrumento" ID "{" { propriedade ";" } "}"
propriedade     ::= "onda" ONDA | "volume" NUMERO
def_padrao      ::= "padrao" ID "=" padrao ";"
faixa           ::= "faixa" ID ":" fonte { transformacao } ";"
fonte           ::= ("nota" | "bateria") (padrao | ID) [ "com" ID ]
transformacao   ::= "." (ID | "volume") "(" [ NUMERO ] ")"
tocar           ::= "tocar" NUMERO "ciclos" [ "salvar" STRING ] ";"

(* mini-notação: da MENOR para a MAIOR precedência *)
padrao          ::= "[" camadas "]"
camadas         ::= sequencia { "," sequencia }              (* polifonia *)
sequencia       ::= passo { passo }                          (* justaposição *)
passo           ::= atomo { modificador }                    (* pós-fixos *)
modificador     ::= "*" NUMERO
                  | "/" NUMERO
atomo           ::= NOTA | SOM | "~" | "[" camadas "]" | "<" sequencia ">"
```

### Léxico

| Token | Definição |
|---|---|
| `NOTA` | `[a-g](#\|b)?[0-9]`, sem letra/dígito colado depois (`c4`, `f#3`, `eb2`, `b3`, `bb3`) |
| `SOM` | `bd` \| `sd` \| `hh` \| `oh` \| `cp` |
| `ONDA` | `senoide` \| `quadrada` \| `serra` \| `triangulo` |
| `NUMERO` | `-?[0-9]+(\.[0-9]+)?` |
| `STRING` | `"[^"\n]*"` |
| `ID` | `[a-zA-Z_][a-zA-Z0-9_]*`, exceto reservadas, notas e sons |
| Reservadas | `tempo instrumento onda volume padrao faixa nota bateria com tocar ciclos salvar` |
| Comentário | `//` até o fim da linha |

Conflitos léxicos:

- `NOTA`, `SOM` e `ONDA` têm prioridade 3 sobre `ID`.
- Um *lookahead* negativo impede casar só o prefixo de um nome maior: `c4e4` é um ID (e dá erro),
  não `c4` seguido de `e4`.
- `bd` não é nota, porque a nota exige o dígito da oitava.
- O lexer contextual do Lark aceitaria `tocar` ou `bd` onde se espera um ID. Por isso o parser
  rejeita explicitamente reservadas, notas e sons usados como identificador.

### Precedência e associatividade

1. **Pós-fixos** (`*n`, `/n`) ligam mais forte e se encadeiam à esquerda:
   `bd*2/3` = `(bd*2)/3`.
2. **Justaposição** (sequência) divide o ciclo igualmente.
3. **Vírgula** (camadas/polifonia) liga mais fraco.
4. **Transformações `.x()`** são associativas à esquerda e aplicadas em ordem:
   `.transpor(12).volume(0.6)` → `volume(0.6, transpor(12, p))`.

Exemplo: `[bd sd*2, hh]` ≡ `[ ( bd (sd*2) ) , ( hh ) ]`.

Modificadores só valem dentro de colchetes: `[bd sd]*2` é erro sintático; escreva `[[bd sd]*2]`
ou use `.rapido(2)`.

### Tipos de dados

Número (inteiro ou real), nota, som de bateria, pausa `~`, string (nome de arquivo),
identificador (instrumento, padrão ou faixa) e **padrão** (tipo composto). O padrão tem
um "tipo de conteúdo": `nota`, `bateria` ou neutro (só pausas). O tipo é inferido pelo semântico.

## Análise semântica

Todos os erros são coletados e mostrados juntos, com `arquivo:linha:coluna`, o trecho marcado
e, quando cabe, uma dica:

```
exemplos/erros/sem_instrumento_nao_declarado.ritmo:2:27: erro semântico: instrumento 'piano' não declarado
 2 | faixa a: nota [c4 e4] com piano;
   |                           ^^^^^
```

**Erros:**

- instrumento ou padrão não declarado
- duplicidade de instrumento, padrão ou faixa (cada categoria tem seu espaço de nomes)
- `bateria` com notas, ou `nota` com sons de bateria (padrão nomeado é verificado onde é usado)
- padrão que mistura notas e bateria
- `com` em faixa de `bateria`
- transformação desconhecida ou com aridade errada
- `*0`, `/0`, `rapido`/`lento` ≤ 0, `volume` fora de [0, 1], `tempo` ≤ 0, ciclos ≤ 0 ou não inteiros,
  `transpor` não inteiro ou aplicado a `bateria`
- propriedade de instrumento repetida, `tempo` duplicado
- `tocar` ausente ou repetido, nenhuma faixa

**Avisos:**

- `tempo` ausente (usa 120)
- instrumento ou padrão nunca usado
- faixa de `nota` sem `com` (usa senoide, volume 0.8)
- instrumento sem `onda`
- arquivo de saída sem `.wav`

Instrumentos e padrões podem ser usados antes de declarados: a análise faz duas passadas e o
gerador emite as definições antes das faixas.

## Semântica de execução

Segue o modelo do Tidal. Um padrão é uma função `consulta(inicio, fim) -> [Evento]`, com o
tempo em ciclos (`fractions.Fraction`, sem erro de arredondamento). Uma consulta devolve os
eventos cujo **início** está no intervalo.

| Construção | Combinador | Comportamento |
|---|---|---|
| `x` | `pure(x)` | um evento por ciclo |
| `~` | `silencio()` | nenhum evento |
| `a b c` | `seq(a,b,c)` | `rapido(n, alterna(a,b,c))` (fastcat) |
| `a, b` | `stack(a,b)` | sobrepõe |
| `<a b c>` | `alterna(a,b,c)` | no ciclo k toca o filho `k mod n`; cada filho conta os próprios ciclos (`<a <b c>>` → a b a c) |
| `x*n` / `.rapido(n)` | `rapido(n,p)` | consulta `[a·n, b·n)` e divide os tempos por n |
| `x/n` / `.lento(n)` | `lento(n,p)` | `rapido(1/n, p)` |
| `.reverso()` | `reverso(p)` | espelha cada ciclo: `t ↦ 2c+1−t` |
| `.transpor(n)` | `transpor(n,p)` | soma n semitons |
| `.volume(x)` | `volume(x,p)` | multiplica o ganho |

Renderização: 1 ciclo = 4 tempos = `240/bpm` s. Para cada faixa, o runtime consulta
`query(0, N)` e sintetiza cada evento a 44,1 kHz, em mono. As notas usam
`440·2^((midi−69)/12)` com envelope (5 ms de ataque, 50 ms de release). A bateria é sintetizada:

- `bd`: varredura de 150 → 50 Hz
- `sd`: ruído + 180 Hz
- `hh`/`oh`: ruído passa-alta
- `cp`: 3 rajadas

As faixas são somadas e normalizadas para pico 0,9 só se passarem disso. O `.wav` é gravado
com `wave` (16 bits).

## Exemplos

- [exemplos/demo.ritmo](exemplos/demo.ritmo): o exemplo da especificação
- [exemplos/bateria.ritmo](exemplos/bateria.ritmo): só percussão, com subgrupos, alternância e polifonia
- [exemplos/polifonia.ritmo](exemplos/polifonia.ritmo): acordes com `,` e progressão com `< >`
- [exemplos/erros/](exemplos/erros/): um erro por arquivo (prefixos `lexico_`, `sintatico_`, `sem_`)

## Roteiro da apresentação

1. Mostrar [gramatica.lark](gramatica.lark) e explicar a precedência com `[bd sd*2, hh]`.
2. `python main.py exemplos/demo.ritmo --mostrar-ast`
3. `python main.py exemplos/demo.ritmo --emitir out.py`: comparar os nós da AST com as chamadas em `out.py`.
4. Erros: `exemplos/erros/lexico_caractere.ritmo`, `sintatico_ponto_virgula.ritmo`,
   `sem_padrao_misto.ritmo`, `sem_argumento_invalido.ritmo` (vários erros de uma vez).
5. Tocar `exemplos/demo.ritmo` e `exemplos/bateria.ritmo`. 🎵
