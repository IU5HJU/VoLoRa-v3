#!/usr/bin/env python3
"""Genera il documento "I modi radio di VoLoRa V3" dai numeri del progetto (tools/protocollo_immagini.py): docs/modi-radio-v3.md e la pagina del sito site/modi.html.
Le tabelle NON si scrivono a mano: escono dalle stesse funzioni che usa il protocollo (stima della sensibilita', frame, tempo in aria, tempo di trasferimento).
Il test tests/sim/test_doc_modi.py controlla che i due file siano aggiornati: dopo ogni modifica ai numeri o al testo rilanciare questo script.
Uso:  python3 tools/gen_doc_modi.py            (scrive i due file)    python3 tools/gen_doc_modi.py --stdout-md   (stampa il Markdown)"""
import html
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import protocollo_immagini as p  # noqa: E402

BUDGET_S = 600.0         # tempo massimo del protocollo per un oggetto
F_MHZ = 433.7
R5 = 5                   # gradino di confronto per la portata (come lo Standard della v2)


def it(x, d=0):
    s = ("%.*f" % (d, x)).replace(".", ",")
    return s


def tempo(s):
    if s < 90:
        return it(s) + " s"
    if s < 5400:
        return it(s / 60.0) + " min"
    if s < 172800:
        return it(s / 3600.0, 1) + " h"
    return it(s / 86400.0, 1) + " giorni"


def kb(n):
    if n < 1000:
        return it(n) + " B"
    if n < 10000:
        return it(n / 1000.0, 1) + " kB"
    if n < 1e6:
        return it(n / 1000.0) + " kB"
    return it(n / 1e6, 1) + " MB"


def bps(x):
    return it(x) + " bit/s" if x < 1000 else it(x / 1000.0, 1 if x < 10000 else 0) + " kbit/s"


def bytes_in(rid, seconds, chip="SX1278"):
    lo, hi = 0, 100_000_000
    while lo < hi:                                  # il piu' grande oggetto che sta nel tempo (bisezione)
        m = (lo + hi + 1) // 2
        if p.estimate_seconds(m, rid, chip) <= seconds:
            lo = m
        else:
            hi = m - 1
    return lo


def nominal_bps(rid):
    _, kind, par, _ = p.RUNGS[rid]
    if kind == "FSK":
        return par[0] * 1000.0
    bw, sf = par
    return sf * bw * 1000.0 / 2 ** sf * 4.0 / 5.0


def lora_rows():
    rows = [r for r in p.RUNGS if r[1] == "LORA"]
    return sorted(rows, key=lambda r: (r[2][0], -r[2][1]))     # dal piu' stretto al piu' largo, a parita' di banda dal piu' lento al piu' veloce


def rung_table_md():
    out = ["| Gradino | Modo | Velocità nominale | Sensibilità | Portata rispetto a R5 | Dati per frame (byte) | Frame in aria | Velocità utile | 5 kB | 20 kB | Byte in 10 minuti |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    r5 = p.sensitivity_dbm(R5)
    for rid, kind, par, name in lora_rows() + [r for r in p.RUNGS if r[1] == "FSK"][::-1]:
        c = p.chunk_size(rid)
        fr = c + p.DATA_HEADER
        at = p.frame_airtime_s(rid, fr)
        sens = p.sensitivity_dbm(rid)
        fac = 10 ** ((r5 - sens) / 20.0)
        mark = " (incontro)" if rid == p.RENDEZVOUS else ""
        out.append("| **R%d**%s | %s | %s | %s dBm | %s | %d | %s s | %s | %s | %s | %s |" % (
            rid, mark, name.replace("/SF", " / SF").replace("LoRa ", "LoRa ").replace(",", ","), bps(nominal_bps(rid)), it(sens, 1), "×" + it(fac, 1) if fac >= 1.05 or fac <= 0.95 else "= (riferimento)",
            c, it(at, 2), bps(c * 8 / at), tempo(p.estimate_seconds(5000, rid)), tempo(p.estimate_seconds(20000, rid)), kb(bytes_in(rid, BUDGET_S))))
    return "\n".join(out)


def fits_table_md():
    out = ["| Cosa si manda | Dimensione | Gradino più lento che ci sta in 10 minuti | Con quel gradino |",
           "|---|---|---|---|"]
    items = [("un messaggio di testo", 1024), ("una miniatura", 2000), ("un'immagine piccola", 5000), ("un'immagine media", 10000), ("un'immagine grande", 20000), ("il massimo del protocollo", 65536)]
    order = [r[0] for r in lora_rows()] + [2, 1, 0]       # dal piu' lento al piu' veloce (FSK in fondo)
    for label, n in items:
        best = None
        for rid in order:
            if p.estimate_seconds(n, rid) <= BUDGET_S:
                best = rid
                break
        if best is None:
            out.append("| %s | %s | **nessuno** | oltre i 10 minuti anche a R3 |" % (label, kb(n)))
        else:
            out.append("| %s | %s | **R%d** (%s) | %s |" % (label, kb(n), best, p.RUNGS[best][3], tempo(p.estimate_seconds(n, best))))
    return "\n".join(out)


def fsk_table_md():
    out = ["| Gradino | Modo | Banda occupata | Sensibilità | SX1278: dati per frame | SX1278: velocità utile | SX1262: dati per frame | SX1262: velocità utile |", "|---|---|---|---|---|---|---|---|"]
    for rid, kind, par, name in p.RUNGS[:3]:
        br, dev = par
        row = []
        for chip in ("SX1278", "SX1262"):
            c = p.chunk_size(rid, chip)
            at = p.frame_airtime_s(rid, c + p.DATA_HEADER)
            row.append((c, c * 8 / at))
        out.append("| **R%d** | FSK %s kbit/s, deviazione %s kHz | %s kHz | %s dBm | %d B | %s | %d B | %s |" % (
            rid, it(br), it(dev), it(br + 2 * dev), it(p.sensitivity_dbm(rid), 1), row[0][0], bps(row[0][1]), row[1][0], bps(row[1][1])))
    return "\n".join(out)


def distance_table_md():
    out = ["| Gradino | Sensibilità | Margine con +17 dBm | Spazio libero ideale | Con le antenne a 10 m (orizzonte radio 26 km) |", "|---|---|---|---|---|"]
    for rid in (14, 10, 5, 3):
        sens = p.sensitivity_dbm(rid)
        budget = 17.0 - sens
        d = 10 ** ((budget - 32.44 - 20 * math.log10(F_MHZ)) / 20.0)
        out.append("| R%d (%s) | %s dBm | %s dB | %s km |" % (rid, p.RUNGS[rid][3], it(sens, 1), it(budget, 1), it(d)))
    return "\n".join(out)


def build_md():
    r5s = p.sensitivity_dbm(R5)
    s10 = p.sensitivity_dbm(p.RENDEZVOUS)
    md = f"""# I modi radio di VoLoRa V3: guida per tutti

> **Stato (28/11/2026): sono stime di studio, non misure.** Le sensibilità sono calcolate con le formule Semtech e confrontate con i datasheet (scarto entro 2 dB, [confronto-datasheet.md](confronto-datasheet.md)); i tempi sono calcolati da `tools/protocollo_immagini.py`. Su una scheda vera finora si sono provati il gradino di incontro e lo scambio di testi e di qualche immagine, senza registrare i gradini: **le misure vere sono la fase 1 dello studio**. Questo documento è generato da `tools/gen_doc_modi.py`: non si modificano le tabelle a mano.

## In breve
- Il protocollo V3 ha **15 modi radio, chiamati gradini (R0 … R14)**: 12 LoRa (R3 … R14) e 3 FSK (R0 … R2).
- **Più stretta è la banda e più alto è il fattore SF, più lontano arriva il segnale ma meno dati passano.** I due estremi sono lontanissimi: R14 manda circa 8 bit al secondo, R3 circa 34 000.
- Le due stazioni si incontrano sempre sul **gradino di incontro R10** (LoRa 125 kHz / SF12) e poi **salgono al gradino più veloce che il collegamento regge**, o scendono se peggiora.
- Con **10 minuti** per oggetto, i gradini lenti portano solo cose piccolissime; i veloci portano immagini intere in pochi secondi.

## 1. Che cos'è un "modo"
Un modo è il **modo di modulare il segnale**: quanto è larga la banda occupata, quanto lentamente si trasmettono i simboli, quanta correzione d'errore c'è. In VoLoRa i modi sono di due famiglie.

- **LoRa** (spettro espanso): robusto, riceve segnali molto deboli, anche sotto il rumore. Ha tre manopole:
  - **Banda (BW):** 7,8 … 500 kHz. Dimezzare la banda dimezza la velocità e guadagna circa **3 dB** di sensibilità (cioè circa il 41% di portata in più in spazio libero).
  - **Fattore di espansione (SF):** 6 … 12. Un SF in più dimezza la velocità e guadagna circa **2,5 dB**.
  - **Codifica (CR):** fissa a 4/5 in tutti i gradini.
- **FSK** (frequenza a due toni): più semplice e molto più veloce, ma **riceve segnali molto più forti**: serve per i collegamenti forti, per esempio due schede vicine o in vista.

Il guadagno di sensibilità si paga in **tempo in aria**: un frame che a R3 dura 0,06 secondi a R14 dura 32 secondi.

## 2. La scala dei 15 gradini
Ordinati **dal più stretto di banda al più largo** (prima i LoRa, poi i FSK). "Velocità nominale" è quella della modulazione; "velocità utile" è quella dei byte di dati dell'oggetto, senza risposte né ritrasmissioni; "5 kB" e "20 kB" sono i tempi stimati **con** ritrasmissioni (5% di perdita), le risposte STATUS e le pause; "byte in 10 minuti" è il più grande oggetto che sta nel tempo massimo del protocollo.

{rung_table_md()}

**Come leggere la tabella**
- **R5** (LoRa 250 kHz / SF7) è come il profilo **Standard** della v2 e **R6** come il **Range**; **R10** (125 kHz / SF12) è come il profilo **Messaggio** della v2: il gradino di incontro.
- **La portata** è relativa a R5: ×{it(10 ** ((r5s - s10) / 20.0), 1)} per R10 significa che, a parità di potenza, R10 arriva {it(10 ** ((r5s - s10) / 20.0), 1)} volte più lontano in spazio libero. È un **confronto**, non una distanza (vedi sotto).
- **I frame dei gradini lenti sono piccoli** (32 o 64 byte di dati, più 6 di intestazione): il protocollo non fa durare un frame in aria più di circa 3 secondi, per non perdere troppo se un frame va male.

### I tre gradini FSK, per chip
L'SX1278 (T3, T-Beam con modulo SX1278) ha un FIFO FSK di 64 byte, e l'SX1262 (T-Beam con modulo SX1262) di 255:

{fsk_table_md()}

## 3. La portata
**Quanto lontano arriva un modo** dipende da due cose: la **sensibilità** del ricevitore (il segnale più debole che sa decodificare) e la **potenza** trasmessa. La differenza è il **margine di collegamento**. A +17 dBm (la potenza normale delle schede) il margine va da {it(17 - p.sensitivity_dbm(3), 0)} dB a R3 a {it(17 - p.sensitivity_dbm(14), 0)} dB a R14.

Ogni **6 dB** in più di margine raddoppiano la distanza in spazio libero, ma lo spazio libero esiste solo in teoria. Esempi con +17 dBm e antenne ideali a 0 dBi, a 433,7 MHz:

{distance_table_md()}

- In **spazio libero** le distanze vengono migliaia di chilometri: non sono realistiche, **la Terra è curva**. Due antenne a 10 m si vedono fino a circa 26 km, a 100 m fino a circa 82 km.
- Perciò il vantaggio dei gradini lenti **non** è "arrivare più lontano di quello che permette l'orizzonte", ma **passare attraverso ostacoli**, alberi, edifici, colline e zone deboli: ogni dB di margine in più è un ostacolo in più che il segnale sopporta. R10 ha circa **{it(r5s - s10, 0).replace('-', '')} dB** in più di R5, R14 circa **{it(r5s - p.sensitivity_dbm(14), 0).replace('-', '')} dB**.
- **Lo stesso vale al contrario:** con due schede vicine un modo lento non serve a niente, è solo lento. Il protocollo sale da solo al gradino più veloce.

## 4. Cosa si può scambiare in ogni modo
Con il tempo massimo di **10 minuti** per oggetto (budget del protocollo), il gradino più lento che ci sta è:

{fits_table_md()}

- Il protocollo manda le immagini **a livelli** (JPEG progressivo, tre livelli): il primo livello è circa un terzo dei byte ed è già un'immagine intera, ma sfocata. Se il tempo non basta, **arriva solo il primo livello** invece di niente.
- **Il testo** (fino a 1 kB) passa in pochi secondi anche ai gradini più lenti, a parte i tempi di incontro.
- **Un'immagine da 10 kB** richiede un gradino da 125 kHz / SF10 (R9) o più veloce; sotto, si consegnano solo i primi livelli.
- I tempi **non** includono il tempo per trovare l'altra stazione (l'HELLO a R10) né i cambi di gradino.

## 5. Come il protocollo sceglie il gradino
1. Le due stazioni si incontrano a **R10** (LoRa 125 kHz / SF12), il gradino che "arriva dappertutto" fra quelli senza problemi di quarzo. Chi vuole inviare manda un **HELLO**; l'altra risponde con il livello che ha sentito (RSSI e SNR).
2. Dalla misura si sceglie il **gradino più veloce con almeno 6 dB di margine** fra quelli che entrambe le stazioni sanno fare.
3. Durante il trasferimento, a ogni finestra di 16 frame il ricevitore risponde con quanto ha sentito: se **più del 20%** dei frame va perso si **scende** di un gradino; se **meno del 2%** si va avanti per tre finestre di fila e c'è margine, si **sale**.
4. Se il collegamento si perde, **si torna a R10** e lo si ritrova lì.

## 6. Limiti e condizioni
- **R12, R13, R14** (banda 31,25 kHz o meno) richiedono un **TCXO**: la deriva di un quarzo normale (circa 10 ppm per scheda) può superare la banda. Senza TCXO non sono annunciati e non si usano. Il TCXO oggi non si legge dalla scheda.
- **R3** (SF6) richiede, sull'SX1278, l'intestazione implicita: il driver non la fa, quindi **R3 non si usa sull'SX1278**. L'SF6 dell'SX1278 e quello dell'SX1262 non sono comunque compatibili fra loro.
- **R0** (FSK 150 kbit/s) è realizzabile solo sull'SX1278; sull'SX1262 il bit rate massimo scala con la frequenza (circa 142 kbit/s a 433,7 MHz), quindi R0 **non è garantito** sull'SX1262 (la tabella FSK dà la cifra teorica a 150 kbit/s).
- **Potenza:** normale +17 dBm (il massimo in continuo dell'SX1278); `POWER` la abbassa per le prove con attenuatori; **BOOST** a +20 dBm e **IOF MODE** a +22 dBm (solo SX1262) sono modalità estreme con rischio tecnico (calore, corrente, saturazione dei ricevitori vicini, spurie). Non ci sono limiti di potenza "legali" nel progetto.
- **Saturazione:** con le schede vicine il ricevitore si satura; per le prove servono attenuatori (60-100 dB in tutto, [prove-laboratorio-v3.md](prove-laboratorio-v3.md)).
- **Le cifre sono stime:** i tempi veri saranno più alti, perché mancano le commutazioni trasmissione/ricezione di ogni frame, i tempi del FIFO e le pause di ascolto.

## 7. Glossario
- **Gradino (rung):** uno dei 15 modi della scala, R0 … R14.
- **BW:** banda occupata dal segnale (kHz). **SF:** fattore di espansione LoRa (6-12). **CR:** codifica di correzione d'errore (qui sempre 4/5).
- **FSK:** modulazione di frequenza a due toni.
- **Sensibilità:** il segnale più debole (in dBm) che il ricevitore decodifica. Più è negativa, meglio è.
- **dBm / dB:** potenza assoluta / rapporto di potenza. +3 dB = il doppio della potenza; +6 dB = il doppio della distanza in spazio libero.
- **RSSI / SNR:** livello e rapporto segnale-rumore misurati dal ricevitore.
- **Tempo in aria:** quanto dura la trasmissione di un frame.
- **TCXO:** quarzo compensato in temperatura, molto più stabile.
- **STATUS:** la risposta del ricevitore ogni 16 frame con la mappa di quello che ha ricevuto: si ritrasmette solo il mancante.

## Fonti nel progetto
[scala-modi.md](scala-modi.md) (scala e sensibilità), [protocollo-immagini.md](protocollo-immagini.md) (protocollo e gradini), [confronto-datasheet.md](confronto-datasheet.md) (limiti dei chip), [prove-laboratorio-v3.md](prove-laboratorio-v3.md) (come provare), `tools/protocollo_immagini.py` (i numeri).
"""
    return md


# ---------------- Markdown -> HTML (solo il sottoinsieme usato qui) ----------------
def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: '<a href="%s">%s</a>' % (link(m.group(2)), m.group(1)), t)
    return t


def link(u):
    if u.endswith(".md") and "/" not in u:
        return "https://github.com/IU5HJU/VoLoRa-v3/blob/main/docs/" + u
    return u


def md_to_html(md):
    lines = md.split("\n")
    out, i, title = [], 0, ""
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
        elif ln.startswith("# "):
            title = ln[2:]
            i += 1
        elif ln.startswith("## "):
            out.append("<h2>%s</h2>" % inline(ln[3:])); i += 1
        elif ln.startswith("### "):
            out.append("<h3>%s</h3>" % inline(ln[4:])); i += 1
        elif ln.startswith("> "):
            buf = []
            while i < len(lines) and lines[i].startswith("> "):
                buf.append(lines[i][2:]); i += 1
            out.append('<div class="warn">%s</div>' % inline(" ".join(buf)))
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
            head, body = rows[0], rows[2:]
            t = ["<div class=\"tw\"><table><thead><tr>%s</tr></thead><tbody>" % "".join("<th>%s</th>" % inline(c) for c in head)]
            for r in body:
                t.append("<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c) for c in r))
            t.append("</tbody></table></div>")
            out.append("".join(t))
        elif ln.startswith("- ") or re.match(r"^\s+- ", ln):
            buf = []
            while i < len(lines) and (lines[i].startswith("- ") or re.match(r"^\s+- ", lines[i])):
                buf.append(lines[i]); i += 1
            ul, depth = [], 0
            for b in buf:
                d = 1 if b.startswith("  ") else 0
                text = inline(b.strip()[2:])
                if d > depth: ul.append("<ul>"); depth = d
                if d < depth: ul.append("</ul></li>"); depth = d
                ul.append("<li>%s" % text if True else "")
                ul.append("</li>" if d == depth and False else "")
            # chiusura semplice: ogni voce chiusa subito (annidamento a un livello)
            html_list = []
            depth = 0
            for b in buf:
                d = 1 if b.startswith("  ") else 0
                text = inline(b.strip()[2:])
                if d > depth: html_list.append("<ul>"); depth = 1
                if d < depth: html_list.append("</ul>"); depth = 0
                html_list.append("<li>%s</li>" % text)
            if depth: html_list.append("</ul>")
            out.append("<ul>%s</ul>" % "".join(html_list))
        elif re.match(r"^\d+\. ", ln):
            buf = []
            while i < len(lines) and re.match(r"^\d+\. ", lines[i]):
                buf.append(re.sub(r"^\d+\. ", "", lines[i])); i += 1
            out.append("<ol>%s</ol>" % "".join("<li>%s</li>" % inline(b) for b in buf))
        else:
            buf = [ln]
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "|", "- ", "> ")) and not re.match(r"^\d+\. ", lines[i]):
                buf.append(lines[i]); i += 1
            out.append("<p>%s</p>" % inline(" ".join(buf)))
    return title, "\n".join(out)


PAGE = """<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>I modi radio di VoLoRa V3</title>
<style>
  :root { --bg:#f6f7f9; --fg:#1b1f24; --muted:#5b6570; --card:#fff; --line:#d5dae0; --accent:#0b5fc2; --warn-bg:#fff4d6; --warn-line:#e0b400; --code-bg:#eef1f4; }
  @media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#12161b; --fg:#e6eaee; --muted:#9aa5b1; --card:#1a2028; --line:#2d3641; --accent:#5aa2ff; --warn-bg:#3a3116; --warn-line:#b38f00; --code-bg:#232b35; } }
  :root[data-theme="dark"] { --bg:#12161b; --fg:#e6eaee; --muted:#9aa5b1; --card:#1a2028; --line:#2d3641; --accent:#5aa2ff; --warn-bg:#3a3116; --warn-line:#b38f00; --code-bg:#232b35; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.55 system-ui, sans-serif; }
  main { max-width:980px; margin:0 auto; padding:16px; }
  h1 { font-size:1.6rem; margin:.5em 0 .3em; }
  h2 { font-size:1.2rem; margin:1.6em 0 .4em; padding-top:.4em; border-top:1px solid var(--line); }
  h3 { font-size:1.02rem; margin:1.2em 0 .3em; }
  p, li { max-width:70ch; }
  a { color:var(--accent); }
  code { background:var(--code-bg); border-radius:4px; padding:1px 5px; font-size:.9em; }
  .warn { background:var(--warn-bg); border:1px solid var(--warn-line); border-radius:10px; padding:10px 14px; margin:14px 0; }
  .tw { overflow-x:auto; border:1px solid var(--line); border-radius:8px; background:var(--card); margin:12px 0; -webkit-overflow-scrolling:touch; }
  table { border-collapse:collapse; width:100%; font-size:.86rem; }
  th, td { padding:6px 9px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }
  th { background:var(--code-bg); position:sticky; top:0; font-weight:600; }
  td:first-child, th:first-child { white-space:nowrap; }
  .muted { color:var(--muted); font-size:.9rem; }
  nav a { margin-right:1em; }
</style>
</head>
<body>
<main>
<p class="muted"><nav><a href="index.html">Firmware di misura</a><a href="firmware-v3.html">Firmware V3</a><a href="telefono.html">Pagina del telefono</a></nav></p>
<h1>@@TITLE@@</h1>
@@BODY@@
<p class="muted">Pagina generata da <code>tools/gen_doc_modi.py</code> (stesso contenuto di <a href="https://github.com/IU5HJU/VoLoRa-v3/blob/main/docs/modi-radio-v3.md">docs/modi-radio-v3.md</a>). Progetto software libero (GPL-3): <a href="https://github.com/IU5HJU/VoLoRa-v3">repository</a>.</p>
</main>
</body>
</html>
"""


def main():
    md = build_md()
    if "--stdout-md" in sys.argv:
        print(md)
        return
    title, body = md_to_html(md)
    root = os.path.join(HERE, "..")
    open(os.path.join(root, "docs", "modi-radio-v3.md"), "w", encoding="utf-8").write(md)
    open(os.path.join(root, "site", "modi.html"), "w", encoding="utf-8").write(PAGE.replace("@@TITLE@@", html.escape(title)).replace("@@BODY@@", body))
    print("scritti docs/modi-radio-v3.md e site/modi.html (%d righe di Markdown)" % (md.count("\n") + 1))


if __name__ == "__main__":
    main()
