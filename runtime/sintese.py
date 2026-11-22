"""Runtime — síntese de áudio (numpy), mixagem, gravação .wav e reprodução.

Recebe as faixas (padrões já montados pelo código gerado), consulta os eventos
de cada uma e os transforma em amostras. Também é embutido no script gerado.
"""

import sys
import wave

import numpy as np

TAXA = 44100          # amostras por segundo (mono)
ATAQUE = 0.005        # s
RELEASE = 0.05        # s
CAUDA = 1.0           # s extras no fim para o som "morrer"


class Instrumento:
    def __init__(self, onda: str = "senoide", volume: float = 0.8):
        self.onda = onda
        self.volume = volume

    def __repr__(self):
        return f"Instrumento({self.onda!r}, {self.volume})"


class Faixa:
    def __init__(self, nome: str, padrao, instrumento=None):
        self.nome = nome
        self.padrao = padrao
        self.instrumento = instrumento


# ---------------------------------------------------------------------------
# Osciladores
# ---------------------------------------------------------------------------

def frequencia(midi: int) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def oscilador(onda: str, freq: float, n: int) -> np.ndarray:
    t = np.arange(n) / TAXA
    fase = freq * t                          # em ciclos da onda
    if onda == "senoide":
        return np.sin(2 * np.pi * fase)
    if onda == "quadrada":
        return np.sign(np.sin(2 * np.pi * fase))
    if onda == "serra":
        return 2 * (fase - np.floor(fase + 0.5))
    if onda == "triangulo":
        return 2 * np.abs(2 * (fase - np.floor(fase + 0.5))) - 1
    raise ValueError(f"onda desconhecida: {onda}")


def envelope(n: int) -> np.ndarray:
    """Ataque linear de ~5 ms e release de ~50 ms (evita estalos)."""
    env = np.ones(n)
    a = min(int(ATAQUE * TAXA), n // 2)
    r = min(int(RELEASE * TAXA), n - a)
    if a > 0:
        env[:a] = np.linspace(0, 1, a, endpoint=False)
    if r > 0:
        env[n - r:] = np.linspace(1, 0, r)
    return env


def sintetizar_nota(midi: int, duracao: float, onda: str, amplitude: float) -> np.ndarray:
    n = max(1, int(duracao * TAXA))
    return amplitude * oscilador(onda, frequencia(midi), n) * envelope(n)


# ---------------------------------------------------------------------------
# Bateria sintetizada
# ---------------------------------------------------------------------------

_cache_bateria = {}


def _ruido(n: int, semente: int) -> np.ndarray:
    return np.random.default_rng(semente).uniform(-1, 1, n)


def _t(segundos: float) -> np.ndarray:
    return np.arange(int(segundos * TAXA)) / TAXA


def sintetizar_bateria(nome: str) -> np.ndarray:
    if nome in _cache_bateria:
        return _cache_bateria[nome]

    if nome == "bd":        # bumbo: senoide com varredura 150 -> 50 Hz
        t = _t(0.4)
        freq = 50 + 100 * np.exp(-t * 25)
        fase = 2 * np.pi * np.cumsum(freq) / TAXA
        s = np.sin(fase) * np.exp(-t * 7)
    elif nome == "sd":      # caixa: ruído + tom de ~180 Hz
        t = _t(0.22)
        s = 0.6 * _ruido(len(t), 1) * np.exp(-t * 18) + \
            0.5 * np.sin(2 * np.pi * 180 * t) * np.exp(-t * 25)
    elif nome in ("hh", "oh"):  # chimbal: ruído passa-alta (diferença de amostras)
        dur, decai = (0.06, 70) if nome == "hh" else (0.35, 9)
        t = _t(dur)
        r = _ruido(len(t) + 1, 2)
        s = 0.5 * np.diff(r) * np.exp(-t * decai)
    elif nome == "cp":      # palma: 3 rajadas curtas de ruído + cauda
        t = _t(0.25)
        r = _ruido(len(t), 3)
        env = np.zeros(len(t))
        for atraso in (0.0, 0.011, 0.022):
            ta = t - atraso
            env += np.where(ta >= 0, np.exp(-np.clip(ta, 0, None) * 180), 0)
        env += np.where(t >= 0.022, 0.6 * np.exp(-np.clip(t - 0.022, 0, None) * 22), 0)
        s = 0.5 * r * env
    else:
        raise ValueError(f"som de bateria desconhecido: {nome}")

    s = s * envelope(len(s))
    _cache_bateria[nome] = s
    return s


# ---------------------------------------------------------------------------
# Renderização
# ---------------------------------------------------------------------------

INSTRUMENTO_PADRAO = Instrumento("senoide", 0.8)


def _somar(buffer: np.ndarray, inicio: int, amostras: np.ndarray):
    if inicio >= len(buffer):
        return
    fim = min(len(buffer), inicio + len(amostras))
    buffer[inicio:fim] += amostras[: fim - inicio]


def renderizar_faixa(faixa: Faixa, bpm: float, ciclos: int, buffer: np.ndarray) -> int:
    dur_ciclo = 240.0 / bpm                  # 1 ciclo = 4 tempos
    instr = faixa.instrumento or INSTRUMENTO_PADRAO
    eventos = faixa.padrao.query(0, ciclos)
    for ev in eventos:
        v = ev.valor
        inicio = int(round(float(ev.inicio) * dur_ciclo * TAXA))
        if v.tipo == "nota":
            duracao = float(ev.fim - ev.inicio) * dur_ciclo
            _somar(buffer, inicio, sintetizar_nota(v.midi, duracao, instr.onda,
                                                   instr.volume * v.ganho))
        else:
            _somar(buffer, inicio, v.ganho * sintetizar_bateria(v.nome))
    return len(eventos)


def renderizar(faixas, bpm: float, ciclos: int, verboso: bool = True) -> np.ndarray:
    total = int((ciclos * 240.0 / bpm + CAUDA) * TAXA)
    mix = np.zeros(total)
    for faixa in faixas:
        buffer = np.zeros(total)
        n = renderizar_faixa(faixa, bpm, ciclos, buffer)
        mix += buffer
        if verboso:
            print(f"  faixa {faixa.nome:<12} {n:4d} eventos")
    return normalizar(mix)


def normalizar(amostras: np.ndarray, pico: float = 0.9) -> np.ndarray:
    """Reduz o volume só se a mixagem passar do pico (evita clipping)."""
    maximo = float(np.max(np.abs(amostras))) if len(amostras) else 0.0
    if maximo > pico:
        amostras = amostras * (pico / maximo)
    return amostras


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------

def salvar_wav(amostras: np.ndarray, caminho: str):
    dados = (np.clip(amostras, -1, 1) * 32767).astype("<i2")
    with wave.open(caminho, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes(dados.tobytes())


def reproduzir_audio(amostras: np.ndarray) -> bool:
    try:
        import sounddevice as sd
    except Exception:                         # módulo ausente ou PortAudio indisponível
        return False
    try:
        sd.play(amostras.astype(np.float32), TAXA)
        sd.wait()
    except KeyboardInterrupt:
        sd.stop()
    except Exception as e:
        print(f"aviso: falha ao reproduzir o áudio ({e})", file=sys.stderr)
        return False
    return True


def tocar(faixas, bpm: float, ciclos: int, arquivo=None, reproduzir: bool = True,
          arquivo_padrao: str = "saida.wav"):
    duracao = ciclos * 240.0 / bpm
    print(f"♪ renderizando {ciclos} ciclos a {bpm:g} BPM ({duracao:.1f} s)")
    amostras = renderizar(faixas, bpm, ciclos)

    if arquivo:
        salvar_wav(amostras, arquivo)
        print(f"♪ áudio salvo em {arquivo}")

    if reproduzir:
        print("♪ tocando... (Ctrl+C para parar)")
        if reproduzir_audio(amostras):
            return amostras
        print("aviso: 'sounddevice' indisponível; o áudio não será tocado", file=sys.stderr)

    if not arquivo:
        salvar_wav(amostras, arquivo_padrao)
        print(f"♪ áudio salvo em {arquivo_padrao}")
    return amostras
