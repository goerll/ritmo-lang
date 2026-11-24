"""Converte um .gp (Guitar Pro 7/8) para a DSL .ritmo: 1 compasso 4/4 = 1 ciclo."""
import sys, zipfile, math, xml.etree.ElementTree as ET
from fractions import Fraction as F

arq, saida = sys.argv[1], sys.argv[2]
root = ET.fromstring(zipfile.ZipFile(arq).read("Content/score.gpif"))
idx = lambda tag: {e.get("id"): e for e in root.find(tag)}
bars, voices, beats, notes, rhythms = idx("Bars"), idx("Voices"), idx("Beats"), idx("Notes"), idx("Rhythms")
tracks = [t.findtext("Name") for t in root.find("Tracks")]
tunings = [[int(x) for x in t.find(".//Property[@name='Tuning']/Pitches").text.split()] for t in root.find("Tracks")]
bpm = float(root.find("MasterTrack/Automations/Automation/Value").text.split()[0])

VAL = {"Whole": F(1), "Half": F(1, 2), "Quarter": F(1, 4), "Eighth": F(1, 8),
       "16th": F(1, 16), "32nd": F(1, 32), "64th": F(1, 64)}
NOMES = ["c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b"]
HARM = {12: 12, 7: 19, 5: 24, 4: 28, 9: 28, 3: 31}

def dur(r):
    d = VAL[r.findtext("NoteValue")]
    dot = r.find("AugmentationDot")
    if dot is not None:
        d *= {1: F(3, 2), 2: F(7, 4)}[int(dot.get("count"))]
    t = r.find("PrimaryTuplet")
    if t is not None:
        d *= F(int(t.get("den")), int(t.get("num")))
    return d

def prop(n, nome, filho):
    p = n.find(f"Properties/Property[@name='{nome}']/{filho}")
    return None if p is None else p.text

def altura(n, trk):
    midi = int(prop(n, "Midi", "Number"))
    if n.find("Properties/Property[@name='Harmonic']") is not None:
        tipo = prop(n, "HarmonicType", "HType") or ""
        hf = prop(n, "HarmonicFret", "HFret")
        if tipo.lower().startswith("natural") and hf is not None:
            corda = int(prop(n, "String", "String"))
            return tunings[trk][corda] + HARM.get(round(float(hf)), 12)
        return midi + 12
    return midi

def nome(m):
    return f"{NOMES[m % 12]}{m // 12 - 1}"

def eventos_compasso(bid, trk):
    """[(onset em compassos, [midis])]"""
    ev = {}
    for vid in bars[bid].findtext("Voices").split():
        if vid == "-1":
            continue
        t = F(0)
        for beid in (voices[vid].findtext("Beats") or "").split():
            b = beats[beid]
            if b.find("GraceNotes") is not None:
                continue
            d = dur(rhythms[b.find("Rhythm").get("ref")])
            for nid in (b.findtext("Notes") or "").split():
                n = notes[nid]
                tie = n.find("Tie")
                if tie is not None and tie.get("destination") == "true":
                    continue
                if n.find("Properties/Property[@name='Muted']") is not None:
                    continue
                ev.setdefault(t, set()).add(altura(n, trk))
            t += d
    return sorted(ev.items())

def slot(ms):
    ms = sorted(ms)
    return nome(ms[0]) if len(ms) == 1 else "[" + ", ".join(nome(m) for m in ms) + "]"

def tempo_batida(evs, k):
    """Mini-notação de uma batida (1/4 de compasso) com a menor grade possível."""
    locais = [((t - F(k, 4)) * 4, ms) for t, ms in evs if F(k, 4) <= t < F(k + 1, 4)]
    if not locais:
        return "~"
    grade = 1
    for t, _ in locais:
        grade = grade * t.denominator // math.gcd(grade, t.denominator)
    slots = ["~"] * grade
    for t, ms in locais:
        i = int(t * grade)
        slots[i] = slot(ms) if slots[i] == "~" else slot(set(ms) | set())
    return slots[0] if grade == 1 else "[" + " ".join(slots) + "]"

def compasso(evs):
    partes = [tempo_batida(evs, k) for k in range(4)]
    if all(p == "~" for p in partes):
        return "~"
    return "[" + " ".join(partes) + "]"

mbs = list(root.find("MasterBars"))
titulo = root.findtext("Score/Title").strip()
artista = root.findtext("Score/Artist").strip()
slug = "".join(c if c.isalnum() else "_" for c in titulo.lower()).strip("_")
linhas = [f"// {titulo.title()} ({artista}) — cover em synth gerado a partir da tablatura .gp",
          "// Uso pessoal/estudo. 1 compasso 4/4 = 1 ciclo. Durações viram a grade de cada batida",
          "// (notas longas soam mais curtas); bends, slides e ligaduras são ignorados.",
          f"tempo {bpm:g};", "",
          "instrumento guitarra1 { onda triangulo; volume 0.6; }",
          "instrumento guitarra2 { onda senoide;   volume 0.5; }", ""]
ids = []
for trk, nomet in enumerate(tracks):
    ident = "g_" + "".join(c for c in nomet.lower() if c.isalnum())
    ids.append(ident)
    linhas.append(f"// guitarra {trk + 1}: {nomet}")
    linhas.append(f"padrao {ident} = [<")
    for i, mb in enumerate(mbs):
        bid = mb.findtext("Bars").split()[trk]
        linhas.append(f"  {compasso(eventos_compasso(bid, trk)):<60} // {i + 1}")
    linhas.append(">];")
    linhas.append("")
for trk, ident in enumerate(ids):
    linhas.append(f"faixa {tracks[trk].lower()}: {ident} com guitarra{trk + 1};")
linhas += ["", f"tocar {len(mbs)} ciclos salvar \"{slug}.wav\";", ""]
open(saida, "w").write("\n".join(linhas))
print("ok", tracks, bpm, len(mbs))
