#!/usr/bin/env python3
"""Genera il PDF "I modi radio e la negoziazione fra le schede nel protocollo VoLoRa V3": docs/pdf/modi-e-negoziazione-v3.pdf.
I numeri (sensibilita', tempi, frame) escono da tools/protocollo_immagini.py come per docs/modi-radio-v3.md; le soglie della negoziazione
sono quelle del firmware (firmware/v3/src/img_proto.h) e il test tests/sim/test_pdf_modi.py le confronta con il sorgente.
Uso: python3 tools/gen_pdf_modi.py"""
import math
import os
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, Flowable, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import protocollo_immagini as p      # noqa: E402
import gen_doc_modi as g             # noqa: E402

OUT = os.path.join(HERE, "..", "docs", "pdf", "modi-e-negoziazione-v3.pdf")
FD = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("DV", FD + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DV-B", FD + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("DV-I", FD + "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DVM", FD + "DejaVuSansMono.ttf"))
pdfmetrics.registerFontFamily("DV", normal="DV", bold="DV-B", italic="DV-I", boldItalic="DV-B")

INK = colors.HexColor("#1b1f24")
ACC = colors.HexColor("#0b5fc2")
SOFT = colors.HexColor("#eef2f7")
WARN = colors.HexColor("#fff4d6")
WARNL = colors.HexColor("#e0b400")
LINE = colors.HexColor("#b8c0cc")

S = {
    "body": ParagraphStyle("body", fontName="DV", fontSize=9.2, leading=13.2, textColor=INK, alignment=TA_LEFT, spaceAfter=4),
    "h1": ParagraphStyle("h1", fontName="DV-B", fontSize=15, leading=19, textColor=ACC, spaceBefore=10, spaceAfter=6),
    "h2": ParagraphStyle("h2", fontName="DV-B", fontSize=11.2, leading=15, textColor=INK, spaceBefore=8, spaceAfter=3),
    "li": ParagraphStyle("li", fontName="DV", fontSize=9.2, leading=13, textColor=INK, leftIndent=12, bulletIndent=2, spaceAfter=2),
    "cell": ParagraphStyle("cell", fontName="DV", fontSize=7.4, leading=9.4, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="DV-B", fontSize=7.4, leading=9.4, textColor=INK),
    "note": ParagraphStyle("note", fontName="DV", fontSize=8.6, leading=12, textColor=INK),
    "title": ParagraphStyle("title", fontName="DV-B", fontSize=24, leading=29, textColor=ACC, spaceAfter=6),
    "sub": ParagraphStyle("sub", fontName="DV", fontSize=12, leading=17, textColor=INK, spaceAfter=10),
    "mono": ParagraphStyle("mono", fontName="DVM", fontSize=8, leading=11, textColor=INK),
}
def P(t, st="body"): return Paragraph(t, S[st])
def H1(t): return P(t, "h1")
def H2(t): return P(t, "h2")
def LI(items): return [Paragraph(t, S["li"], bulletText="•") for t in items]
def box(text, bg=SOFT, line=LINE):
    t = Table([[Paragraph(text, S["note"])]], colWidths=[174 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("BOX", (0, 0), (-1, -1), 0.7, line), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t
def table(rows, widths, head=True, zebra=True, fs=None):
    data = [[Paragraph(str(c), S["cellb"] if (head and i == 0) else S["cell"]) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if head else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    if head: st.append(("BACKGROUND", (0, 0), (-1, 0), SOFT))
    t.setStyle(TableStyle(st))
    return t


# ---------------------------------------------------------------- diagrammi
class Sequence(Flowable):
    """Diagramma a sequenza fra Mittente e Ricevitore."""
    def __init__(self, steps, width=174 * mm, rowh=17):
        super().__init__()
        self.steps, self.w, self.rowh = steps, width, rowh
        self.h = rowh * (len(steps) + 2) + 6
    def wrap(self, aw, ah): return self.w, self.h
    def draw(self):
        c = self.canv
        xa, xb = 62 * mm, self.w - 62 * mm
        top = self.h - 4
        c.setFont("DV-B", 9)
        for x, t in ((xa, "Mittente"), (xb, "Ricevitore")):
            c.setFillColor(ACC); c.roundRect(x - 22 * mm, top - 13, 44 * mm, 14, 3, fill=1, stroke=0)
            c.setFillColor(colors.white); c.drawCentredString(x, top - 9.5, t)
        c.setStrokeColor(LINE); c.setDash(2, 2)
        c.line(xa, top - 14, xa, 2); c.line(xb, top - 14, xb, 2); c.setDash()
        y = top - 14 - self.rowh * 0.7
        for kind, text, note in self.steps:
            if kind in ("->", "<-"):
                x0, x1 = (xa, xb) if kind == "->" else (xb, xa)
                c.setStrokeColor(INK); c.setFillColor(INK); c.setLineWidth(1)
                c.line(x0, y, x1, y)
                d = 4 if x1 > x0 else -4
                c.line(x1, y, x1 - d, y + 2.4); c.line(x1, y, x1 - d, y - 2.4)
                c.setFont("DV-B", 7.6); c.drawCentredString((xa + xb) / 2, y + 3.8, text)
                if note:
                    c.setFont("DV", 6.8); c.setFillColor(colors.HexColor("#5b6570"))
                    c.drawString(xb + 6 * mm if kind == "->" else 2, y - 1, note) if kind == "->" else c.drawRightString(xa - 6 * mm, y - 1, note)
            else:                                    # riga di fase
                c.setFillColor(SOFT); c.rect(0, y - 6, self.w, 12, fill=1, stroke=0)
                c.setFillColor(ACC); c.setFont("DV-B", 7.8); c.drawString(4, y - 2.6, text)
            y -= self.rowh


class Ladder(Flowable):
    """La scala dei 15 gradini come barra: velocita' utile (scala logaritmica) e sensibilita'."""
    def __init__(self, width=174 * mm): super().__init__(); self.w = width; self.h = 56 * mm
    def wrap(self, aw, ah): return self.w, self.h
    def draw(self):
        c = self.canv
        order = [r[0] for r in g.lora_rows()] + [2, 1, 0]
        n = len(order); bw = self.w / n
        rates = {rid: p.net_rate_bps(rid) for rid in order}
        lo, hi = math.log10(min(rates.values())), math.log10(max(rates.values()))
        base = 10 * mm; maxh = self.h - 27 * mm
        for i, rid in enumerate(order):
            r = (math.log10(rates[rid]) - lo) / (hi - lo)
            hh = 2 + r * (maxh - 2)
            col = ACC if rid != p.RENDEZVOUS else colors.HexColor("#d9480f")
            if rid <= 2: col = colors.HexColor("#6f42c1")
            c.setFillColor(col); c.rect(i * bw + 1.5, base, bw - 3, hh, fill=1, stroke=0)
            c.setFillColor(INK); c.setFont("DV-B", 7); c.drawCentredString(i * bw + bw / 2, base - 8, "R%d" % rid)
            c.setFont("DV", 5.6); c.drawCentredString(i * bw + bw / 2, base - 15, "%+.0f" % p.sensitivity_dbm(rid))
            c.setFont("DV", 5.6); c.drawCentredString(i * bw + bw / 2, base + hh + 3, g.bps(rates[rid]).replace(" bit/s", "").replace(" kbit/s", "k"))
        c.setFont("DV-I", 6.4); c.setFillColor(colors.HexColor("#5b6570"))
        c.drawString(0, self.h - 5, "Altezza = velocità utile (scala logaritmica); sotto: gradino e sensibilità stimata in dBm")
        c.drawString(0, self.h - 13, "viola = FSK, blu = LoRa, arancio = R10 (incontro)")
        c.drawRightString(self.w, self.h - 5, "← più portata, meno dati        più dati, meno portata →")


# ---------------------------------------------------------------- contenuto
def build():
    st = []
    # ---- copertina
    st += [Spacer(1, 40 * mm), P("I modi radio e la negoziazione fra le schede", "title"),
           P("Guida al protocollo VoLoRa V3: i 15 gradini, come le schede si incontrano, come scelgono la velocità e che cosa fanno quando il collegamento peggiora", "sub"),
           Spacer(1, 6 * mm),
           box("<b>Stato: studio di progetto.</b> Le sensibilità sono stime calcolate con le formule Semtech e confrontate con i datasheet (scarto entro 2 dB); i tempi sono calcolati da <font name='DVM'>tools/protocollo_immagini.py</font>; il comportamento della negoziazione è provato sul <b>simulatore</b> e sul nucleo C++ del firmware, <b>non misurato sul campo</b>. Su schede vere sono stati provati l'incontro a R10, la scelta del gradino e l'invio di testi e di un'immagine (video del 28/11/2026): i gradini effettivamente raggiunti non sono ancora registrati. Le misure vere sono la fase 1 dello studio.", WARN, WARNL),
           Spacer(1, 8 * mm),
           P("<b>Autore del progetto:</b> IU5HJU &nbsp;·&nbsp; <b>Data:</b> 28/11/2026 &nbsp;·&nbsp; <b>Repository:</b> github.com/IU5HJU/VoLoRa-v3"),
           P("<b>Documenti collegati:</b> docs/modi-radio-v3.md, docs/scala-modi.md, docs/protocollo-immagini.md, docs/confronto-datasheet.md, docs/simulatore-immagini.md"),
           PageBreak()]

    # ---- in breve
    st += [H1("1. In breve"),
           *LI(["Il protocollo ha <b>15 modi radio, chiamati gradini (R0 … R14)</b>: R0-R2 in FSK, R3-R14 in LoRa.",
                "Più la banda è stretta e più alto è il fattore SF, <b>più debole è il segnale che si riesce a ricevere, ma meno dati passano</b>: da circa 8 bit/s (R14) a circa 34 000 bit/s (R3) in LoRa, fino a oltre 100 000 bit/s in FSK.",
                "Due schede <b>si incontrano sempre su R10</b> (LoRa 125 kHz / SF12), poi <b>misurano il collegamento e salgono</b> al gradino più veloce che ha almeno 6 dB di margine. Se il collegamento peggiora scendono, se lo perdono lo cercano tutte e due con lo <b>stesso calendario</b> basato sull'orologio.",
                "Ogni oggetto ha un <b>budget di 10 minuti</b>: se il tempo non basta, arriva solo il primo livello dell'immagine (JPEG progressivo) invece di niente.",
                "L'infrastruttura v2 non viene toccata: i frame V3 hanno versione 3 e le stazioni v2 li scartano."]),
           H1("2. Che cos'è un modo (gradino)"),
           P("Un modo è il <b>modo di modulare il segnale</b>: quanto è larga la banda occupata, quanto lentamente si trasmettono i simboli e quanta correzione d'errore si aggiunge. Il protocollo ne usa due famiglie."),
           *LI(["<b>LoRa</b> (spettro espanso). Robusto, riceve segnali molto deboli, anche sotto il rumore. Ha tre manopole: la <b>banda BW</b> (7,8 … 500 kHz: dimezzarla dimezza la velocità e guadagna circa 3 dB di sensibilità), il <b>fattore di espansione SF</b> (6 … 12: un SF in più dimezza la velocità e guadagna circa 2,5 dB) e la codifica <b>CR</b> (fissa a 4/5).",
                "<b>FSK</b> (frequenza a due toni). Molto più veloce, ma riceve solo segnali molto più forti: serve per collegamenti forti, per esempio due schede vicine o in vista."]),
           P("Il guadagno di sensibilità si paga in <b>tempo in aria</b>: un frame che a R3 dura 0,06 s, a R14 dura circa 32 s. Per questo il protocollo non usa mai il gradino più robusto \"per sicurezza\": usa il <b>più veloce che regge</b>."),
           Spacer(1, 3 * mm), Ladder(), PageBreak()]

    # ---- tabella della scala
    st += [H1("3. La scala dei 15 gradini")]
    st.append(P("Ordinati dal più stretto di banda al più largo (prima i LoRa, poi i FSK). <b>Velocità utile</b> = byte di dati dell'oggetto per secondo di trasmissione, senza risposte né ritrasmissioni. <b>5 kB / 20 kB</b> = tempo stimato con il 5% di perdita, una risposta STATUS ogni finestra e 0,15 s di pausa. Chip: SX1278 (T3, T-Beam 1278)."))
    rows = [["Gradino", "Modo", "Sensibilità stimata", "Portata vs R5", "Dati per frame", "Frame in aria", "Velocità utile", "5 kB", "20 kB", "Byte in 10 min"]]
    r5 = p.sensitivity_dbm(5)
    for rid, kind, par, name in g.lora_rows() + [r for r in p.RUNGS if r[1] == "FSK"][::-1]:
        c = p.chunk_size(rid); at = p.frame_airtime_s(rid, c + p.DATA_HEADER); sens = p.sensitivity_dbm(rid)
        fac = 10 ** ((r5 - sens) / 20.0)
        rows.append(["R%d%s" % (rid, " (incontro)" if rid == p.RENDEZVOUS else ""), name, "%s dBm" % g.it(sens, 1), "×" + g.it(fac, 1) if abs(fac - 1) > .05 else "= (rif.)", "%d B" % c, "%s s" % g.it(at, 2), g.bps(c * 8 / at), g.tempo(p.estimate_seconds(5000, rid)), g.tempo(p.estimate_seconds(20000, rid)), g.kb(g.bytes_in(rid, g.BUDGET_S))])
    st.append(table(rows, [20, 27, 19, 14, 14, 14, 17, 14, 14, 21]))
    st += [Spacer(1, 3 * mm),
           *LI(["<b>R5</b> (250 kHz / SF7) corrisponde al profilo <i>Standard</i> della v2, <b>R6</b> al <i>Range</i>, <b>R10</b> (125 kHz / SF12) al <i>Messaggio</i>.",
                "<b>La portata</b> è un confronto fra gradini a parità di potenza (6 dB = distanza doppia in spazio libero). In pratica il limite è l'<b>orizzonte radio</b> (circa 26 km con antenne a 10 m): il vantaggio dei gradini lenti è <b>attraversare ostacoli</b>, non superare la curvatura della Terra.",
                "I frame dei gradini lenti sono piccoli (32 o 64 byte di dati, più 6 di intestazione): il protocollo cerca di non superare circa <b>3 s di tempo in aria per frame</b>, per non perdere troppo quando un frame va male.",
                "Sull'SX1278 il frame FSK può essere lungo al massimo 64 byte (FIFO); per questo i frame FSK portano 48 byte di dati (SX1262: fino a 240)."]),
           Spacer(1, 4 * mm)]

    # ---- cosa si scambia
    st += [H1("4. Quanto si riesce a scambiare")]
    st.append(P("Con il budget di <b>10 minuti</b> per oggetto, il gradino <b>più lento</b> che porta a termine l'invio è:"))
    items = [("un testo di 1 kB", 1024), ("una miniatura", 2000), ("un'immagine piccola", 5000), ("un'immagine media", 10000), ("un'immagine grande", 20000), ("il massimo del protocollo (64 kB)", 65536)]
    order = [r[0] for r in g.lora_rows()] + [2, 1, 0]
    rows = [["Oggetto", "Dimensione", "Gradino più lento che ci sta", "Tempo a quel gradino"]]
    for lab, n in items:
        best = next((rid for rid in order if p.estimate_seconds(n, rid) <= g.BUDGET_S), None)
        rows.append([lab, g.kb(n), "<b>R%d</b> (%s)" % (best, p.RUNGS[best][3]) if best is not None else "nessuno", g.tempo(p.estimate_seconds(n, best)) if best is not None else "oltre i 10 min"])
    st.append(table(rows, [52, 24, 58, 40]))
    st += [Spacer(1, 3 * mm),
           P("L'immagine non viene mandata in un blocco solo: è divisa in <b>livelli</b> (JPEG progressivo, tre livelli). Il primo livello, circa un terzo dei byte, è già l'immagine intera ma sfocata; i successivi la rifiniscono. Se il tempo non basta per tutti, <b>si ferma al confine dell'ultimo livello completo</b> e l'immagine resta utile. Se neanche il primo livello entra nel budget al gradino migliore possibile, l'invio non parte e si propone una versione più piccola."),
           P("I tempi <b>non</b> comprendono l'incontro (HELLO) né i cambi di gradino, e il tempo reale sarà più alto per le commutazioni trasmissione/ricezione, i tempi del FIFO e le pause di ascolto."),
           PageBreak()]

    # ---- negoziazione
    st += [H1("5. La negoziazione: panoramica"),
           P("Le due schede non conoscono in anticipo la qualità del collegamento. La logica ha quattro fasi, ognuna con una regola semplice:"),
           table([["Fase", "Che cosa succede", "Regola"],
                  ["1. Incontro", "Entrambe ascoltano su R10. Chi vuole inviare manda HELLO; l'altra risponde con HELLO + RSSI e SNR del frame appena sentito.", "R10 è l'ultimo gradino senza dubbi sul quarzo: <i>arriva dappertutto</i>."],
                  ["2. Capacità", "Nell'HELLO ogni scheda dichiara chip (SX1278 / SX1262) e <b>maschera dei gradini</b> che sa fare. Il gradino ammesso è l'<b>AND</b> delle due maschere.", "R3 si toglie se i chip differiscono (l'SF6 non è compatibile). R12-R14 solo se la scheda dichiara un TCXO. R0 solo SX1278."],
                  ["3. Salita", "Dalla misura dell'HELLO si sceglie il gradino più veloce con margine ≥ 6 dB, e lo si conferma con una <b>raffica di PROBE</b>; poi MODE-SET / MODE-ACK.", "Si accetta se arriva ≥ 90% dei PROBE. Se nessun gradino ha 6 dB si prova con 3 dB."],
                  ["4. Trasferimento", "OFFER → ACCEPT, poi DATA a finestre di fino a 16 frame; il ricevitore risponde con STATUS (mappa dei pezzi + qualità). Si ritrasmette solo il mancante.", "Perdita &gt; 20% scende; &lt; 2% per 3 finestre e margine ≥ 6 dB sale."]],
                 [26, 92, 56]),
           Spacer(1, 4 * mm), H2("Sequenza tipica di un invio"),
           Sequence([("fase", "1. Incontro su R10", ""),
                     ("->", "HELLO (nominativo, chip, maschera)", "dopo CAD"),
                     ("<-", "HELLO risposta + RSSI/SNR", "misura del frame"),
                     ("fase", "2-3. Scelta del gradino (es. R6)", ""),
                     ("->", "MODE-SET R6", "ripetuto 3 volte"),
                     ("<-", "MODE-ACK R6", "ancora su R10"),
                     ("->", "PROBE × 8 su R6", "raffica di prova"),
                     ("<-", "PROBE-REPORT (≥ 90%)", ""),
                     ("fase", "4. Trasferimento a R6", ""),
                     ("->", "OFFER (dimensione, livelli, CRC32)", ""),
                     ("<-", "ACCEPT (livelli, finestra 16)", ""),
                     ("->", "DATA × 16 (pezzi da 16 B)", "una finestra"),
                     ("<-", "STATUS (mappa, RSSI, SNR, perdita)", ""),
                     ("->", "DATA solo i mancanti", "ritrasmissione selettiva"),
                     ("->", "DONE (livelli, byte, CRC32)", ""),
                     ("<-", "STATUS completo", "fine")]),
           PageBreak()]

    # ---- dettaglio incontro, capacità, salita
    st += [H1("6. Incontro e capacità"),
           *LI(["<b>HELLO</b> (tipo 0): porta il nominativo, il chip, la <b>maschera a 16 bit</b> dei gradini supportati, il frame massimo, la memoria libera e, se presente, la posizione. La <b>risposta</b> all'HELLO porta anche RSSI e SNR del frame appena sentito: così il mittente sceglie il gradino da quella misura, senza una raffica di PROBE a R10 (che costava circa 21 s: ora circa 5 s con segnale forte, sul simulatore).",
                "<b>Se nessuno risponde</b>, l'HELLO si ripete con intervalli crescenti (da 5 a 60 s, con un po' di casualità) e per un tempo massimo (900 s nel firmware): un nodo non trasmette all'infinito.",
                "<b>Maschera dei gradini.</b> Una scheda annuncia solo i gradini che il suo chip realizza alla frequenza in uso con i quarzi che ha: R12-R14 richiedono un <b>TCXO</b> (con due quarzi da 10 ppm l'errore totale, 20 ppm, supera il margine di 18 ppm di R12); R3 (SF6) sull'SX1278 richiede l'intestazione implicita e oggi non è fatto dal driver; R0 (150 kbit/s) non è garantito sull'SX1262 a 433 MHz. Il TCXO si dichiara con il comando seriale <font name='DVM'>TCXO ON</font> (non è rilevabile dalla scheda)."]),
           H1("7. Scelta, salita e discesa del gradino"),
           H2("Come si misura il collegamento"),
           P("Il ricevitore misura <b>RSSI</b> (livello, dBm) e <b>SNR</b> (rapporto segnale-rumore, dB) e li manda nei frame HELLO-risposta e STATUS. Il <b>margine</b> di un gradino è la distanza fra il livello ricevuto e la sensibilità di quel gradino: <font name='DVM'>margine = RSSI − sensibilità(gradino)</font>. Il firmware scorre i gradini ammessi dal più veloce e sceglie il primo con margine ≥ 6 dB (se nessuno, ≥ 3 dB; se ancora nessuno, il più lento)."),
           H2("Le soglie (dal firmware, firmware/v3/src/img_proto.h)"),
           table([["Parametro", "Valore", "Significato"],
                  ["kMarginUpDb", "6 dB", "margine minimo per scegliere o salire a un gradino"],
                  ["kProbeOk", "90 %", "quota di PROBE ricevuti per confermare un cambio di gradino"],
                  ["kLossDown", "20 %", "perdita in una finestra oltre la quale si scende subito"],
                  ["kLossUp", "2 %", "perdita sotto la quale (per 3 finestre di fila, con margine ≥ 6 dB sul gradino successivo) si sale"],
                  ["kGuardS", "0,15 s", "pausa di sicurezza fra trasmissione e ricezione"],
                  ["kGiveUpS", "900 s", "tempo dopo il quale una stazione smette di cercare l'altra"],
                  ["finestra", "16 frame", "frame fra una risposta STATUS e l'altra (da 1 a 64 ammessi)"],
                  ["raffica PROBE", "8 frame (4 ai gradini lenti)", "lunghezza della prova a un gradino candidato"],
                  ["fallback", "max(30 s, 12 × tempo in aria di un frame)", "silenzio dopo il quale si considera perso il collegamento"]],
                 [38, 46, 90]),
           H2("Cambio di gradino"),
           P("<b>MODE-SET</b> (gradino nuovo e pezzi per frame, ripetuto 3 volte per sicurezza) → <b>MODE-ACK</b> sul gradino attuale → <b>entrambe</b> le stazioni passano al nuovo gradino <b>alla fine del MODE-ACK</b>. Si manda subito una raffica di <b>PROBE</b>: se ne arriva ≥ 90% il cambio è confermato, altrimenti si ritorna a un gradino più lento. Se la prima prova sul nuovo gradino non ottiene risposta entro il fallback, <b>si torna a R10</b> e si riparte da HELLO."),
           H2("Discesa"),
           P("Si scende di un gradino <b>subito</b> se in una finestra la perdita supera il 20% o se due STATUS di fila mancano. La discesa non richiede conferma: chi non sente più l'altra stazione passa alla <b>ricerca</b> dopo il tempo di fallback. Il timer conta <b>solo il tempo in ascolto</b>: mentre una stazione trasmette (una finestra a un gradino lento dura decine di secondi) non scorre. Senza questa regola il simulatore faceva scattare il fallback nel mezzo della finestra stessa."),
           PageBreak()]

    # ---- ricerca a calendario
    st += [H1("8. Quando il collegamento si perde: la ricerca a calendario"),
           P("Le due stazioni non possono accordarsi su un nuovo gradino se non si sentono più. Perciò seguono entrambe lo <b>stesso calendario in funzione dell'orologio</b>, senza scambiarsi nulla. Ogni voce dura 120 s (o più, se il frame lento dura di più) e <b>R10 compare a ogni secondo turno</b>, perché spesso il collegamento torna proprio lì:"),
           ]
    cal = [10, 11, 10, 12, 10, 13, 10, 14]
    cells = [[Paragraph("<b>R%d</b>" % r, ParagraphStyle("cc", parent=S["cell"], alignment=1, fontSize=9, textColor=colors.white)) for r in cal]]
    t = Table(cells, colWidths=[21.5 * mm] * 8, rowHeights=[9 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), ACC), ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#d9480f")), ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#d9480f")), ("BACKGROUND", (4, 0), (4, 0), colors.HexColor("#d9480f")), ("BACKGROUND", (6, 0), (6, 0), colors.HexColor("#d9480f")), ("GRID", (0, 0), (-1, -1), 1, colors.white), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    st += [t, P("<i>Calendario: R10, R11, R10, R12, R10, R13, R10, R14, poi daccapo. Si restringe ai gradini che entrambe le stazioni hanno annunciato (senza TCXO resta R10, R11).</i>", "note"), Spacer(1, 3 * mm),
           *LI(["Il <b>mittente</b> manda HELLO al gradino in cui si trova; il <b>ricevitore</b> ascolta e risponde.",
                "Il ricevitore esce dalla ricerca solo se sente un frame <b>diverso da HELLO</b>; il mittente tiene il gradino dopo la risposta ma riprende il calendario se la prova fallisce.",
                "Il ricevitore resta al gradino per 12 frame (almeno 60 s) dopo aver risposto.",
                "Ritrovati, si <b>riprende il trasferimento senza rifare le PROBE</b>.",
                "Risultati sul simulatore: dove R10 non si sente più, la consegna passa da 2 prove su 12 a 10 su 12; nei casi estremi (solo R13-R14) arriva a 5-6 su 12 (docs/simulatore-immagini.md)."]),
           H1("9. Ritrasmissione selettiva e finestre"),
           *LI(["L'oggetto è diviso in <b>pezzi da 16 byte</b>; un frame DATA porta k pezzi consecutivi (15 sui gradini veloci, 4 a R10, 2 da R11 in giù). La mappa dello STATUS ha un bit per blocco.",
                "Il mittente manda una <b>finestra</b> di frame (di base 16) e aspetta lo STATUS; ritrasmette <b>solo i blocchi mancanti</b>.",
                "Se lo STATUS non arriva, ripete l'ultimo frame fino a 3 volte, poi scende di un gradino.",
                "A fine oggetto: <b>DONE</b> con livelli e byte consegnati e CRC32 del prefisso consegnato; il ricevitore risponde con uno STATUS completo.",
                "Ogni circa 10 minuti di trasferimento si manda un frame <b>ID</b> con il nominativo, oltre a OFFER e DONE che già lo contengono."]),
           H1("10. Tre esempi"),
           table([["Situazione", "Che cosa fanno le schede", "Esito atteso (stima)"],
                  ["<b>Schede vicine, segnale forte</b> (come nel video di prova)", "Incontro a R10, HELLO-risposta con RSSI alto; si sceglie il gradino più veloce con 6 dB di margine, conferma con PROBE; trasferimento; durante l'invio, 3 finestre con perdita &lt; 2% → si sale ancora.", "Un'immagine da 20 kB in pochi secondi o decine di secondi secondo il gradino raggiunto (da 7 s a R3 a 19 s a R5)."],
                  ["<b>Collegamento medio</b>, colline e alberi", "RSSI intorno a −125 dBm: R6 (sensibilità −124) non ha margine; R8 ne ha 4,5 dB (meno di 6); R9 ne ha 7 dB, quindi si sceglie R9. Se in una finestra si perde più del 20% si scende di un gradino.", "20 kB in circa 3 minuti a R9; se il tempo non basta arriva il primo livello."],
                  ["<b>Collegamento marginale o perso</b>", "Dopo il fallback le due stazioni seguono il calendario R10, R11, R10, R12 … e si ritrovano su R10 (o R11); riprende il trasferimento da dove era.", "Immagini piccole (2-5 kB) in 4-11 minuti a R10-R11; sotto, quasi solo testo."]],
                 [40, 88, 46]),
           PageBreak()]

    # ---- limiti e stato
    st += [H1("11. Limiti tecnici"),
           *LI(["<b>Quarzo.</b> Sotto i 62,5 kHz di banda (R12-R14) l'errore di frequenza dei quarzi normali (circa 10 ppm per scheda, valore di lavoro da misurare) supera il margine: servono schede con TCXO, dichiarate con <font name='DVM'>TCXO ON</font> sulla seriale su <b>entrambe</b> le stazioni.",
                "<b>SX1278 e SX1262</b> non sono identici: FIFO FSK di 64 byte contro 255; SF6 incompatibile fra i due chip (R3 si usa solo fra chip uguali, e oggi non sul SX1278 per l'intestazione implicita non ancora fatta); R0 non garantito sull'SX1262 a 433 MHz.",
                "<b>Potenza.</b> Di base +17 dBm; il comando <font name='DVM'>POWER</font> la abbassa (utile con gli attenuatori); <b>BOOST</b> (+20 dBm) e <b>IOF MODE</b> (+22 dBm, solo SX1262) sono modalità estreme con rischi <b>tecnici</b>: calore, corrente, saturazione dei ricevitori vicini, armoniche e spurie.",
                "<b>Saturazione.</b> Con le schede vicine il ricevitore si satura: per le prove servono attenuatori (60-100 dB in totale).",
                "<b>Frequenze.</b> Quelle di T3 e T-Beam sono configurabili con <font name='DVM'>FREQ</font> nel campo del chip (SX1278: 137-175 e 410-525 MHz; SX1262: 150-960 MHz).",
                "<b>Il firmware misura il margine con RSSI − sensibilità</b> (stimata); il testo di progetto parla anche di SNR corretto per la banda: le due strade coincidono dove il segnale è sopra il rumore; la differenza si valuterà con le misure."]),
           H1("12. Che cosa è provato e che cosa no"),
           table([["Argomento", "Stato"],
                  ["Formule di sensibilità e tempi in aria", "Calcolati; sensibilità entro 2 dB dai datasheet; <b>nessuna misura</b>"],
                  ["Algoritmo di negoziazione (incontro, salita, discesa, ricerca a calendario)", "Provato sul <b>simulatore</b> con perdite e rumore e sul <b>nucleo C++</b> del firmware contro il riferimento Python; <b>non misurato sul campo</b>"],
                  ["Scambio su schede vere (T3, due schede, attenuatori)", "Testo e immagini consegnati dal telefono via Bluetooth/Android (video 28/11/2026); <b>gradini raggiunti non registrati</b>"],
                  ["Gradini lenti R11-R14 su schede vere", "<b>Mai provati</b>; R12-R14 richiedono TCXO"],
                  ["FSK R0-R2", "Mai provati su schede; il FIFO da 64 byte dell'SX1278 va confermato"],
                  ["Cambio di banda (2,4 GHz)", "Solo frame e codec sul PC; <b>non fa parte del firmware V3</b>"]],
                 [78, 96]),
           H1("13. Glossario"),
           table([["Termine", "Significato"],
                  ["Gradino (R0…R14)", "Uno dei 15 modi radio della scala."],
                  ["BW, SF, CR", "Banda occupata (kHz), fattore di espansione LoRa (6-12), codifica di correzione (qui 4/5)."],
                  ["FSK", "Modulazione di frequenza a due toni."],
                  ["Sensibilità", "Segnale più debole (dBm) che il ricevitore decodifica; più è negativa, meglio è."],
                  ["Margine", "Differenza in dB fra il livello ricevuto e la sensibilità del gradino."],
                  ["RSSI / SNR", "Livello ricevuto (dBm) / rapporto segnale-rumore (dB)."],
                  ["Tempo in aria", "Durata della trasmissione di un frame."],
                  ["HELLO / PROBE / MODE-SET / MODE-ACK", "Frame di incontro, di prova, di proposta e di conferma del cambio di gradino."],
                  ["OFFER / ACCEPT / DATA / STATUS / DONE", "Frame del trasferimento: proposta, accettazione, pezzi, risposta con la mappa dei pezzi, fine."],
                  ["Finestra", "Gruppo di frame (di base 16) fra due STATUS."],
                  ["TCXO", "Quarzo compensato in temperatura, molto più stabile di un quarzo normale."],
                  ["CAD", "Rilevamento di attività sul canale prima di trasmettere."]],
                 [58, 116]),
           Spacer(1, 4 * mm),
           P("<i>Fonti: docs/protocollo-immagini.md (protocollo e frame), docs/scala-modi.md (scala e sensibilità), docs/confronto-datasheet.md (limiti dei chip), docs/simulatore-immagini.md (risultati del simulatore), firmware/v3/src/img_proto.h e limits.h (soglie e maschera), tools/protocollo_immagini.py (tempi). Documento generato da tools/gen_pdf_modi.py.</i>", "note")]
    return st


def on_page(c, d):
    c.saveState()
    c.setFont("DV", 7.2); c.setFillColor(colors.HexColor("#5b6570"))
    c.drawString(18 * mm, 10 * mm, "VoLoRa V3 - I modi radio e la negoziazione - studio, stime non misure")
    c.drawRightString(A4[0] - 18 * mm, 10 * mm, "pag. %d" % d.page)
    c.setStrokeColor(LINE); c.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
    c.restoreState()


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    doc = BaseDocTemplate(OUT, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                          title="I modi radio e la negoziazione fra le schede - VoLoRa V3", author="IU5HJU - progetto VoLoRa V3", subject="Protocollo VoLoRa V3 (studio)", invariant=1)
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")], onPage=on_page)])
    doc.build(build())
    print("scritto", os.path.relpath(OUT, os.path.join(HERE, "..")), os.path.getsize(OUT), "byte")


if __name__ == "__main__":
    main()
