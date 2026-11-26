#!/usr/bin/env python3
"""Simulatore del protocollo immagini V3 (bozza, docs/protocollo-immagini.md): mittente e ricevitore, canale con perdite, tempo simulato.

  python3 tools/sim_immagini.py --size 20000 --layers 3 --prx -110 --scenario degrada --seed 1 --trace
  python3 tools/sim_immagini.py --sweep --size 5000          # tabella: tempo e riuscita al variare della potenza ricevuta

Modello (ipotesi di lavoro, da sostituire con le misure della fase 1):
 * un frame arriva con probabilita' logistica attorno alla sensibilita' stimata del gradino (docs/scala-modi.md), elevata a (byte / 64):
   i frame lunghi si perdono piu' spesso;
 * la potenza ricevuta e' quella di partenza meno la perdita extra dello scenario, piu' un affievolimento casuale per frame;
 * mezzo duplex: una sola stazione trasmette alla volta; ogni cambio di verso costa un tempo di commutazione (GUARD_S);
 * ogni stazione ha il proprio gradino: se non coincide con quello del trasmettitore il frame non si sente (cosi' si vedono i
   disallineamenti dopo un MODE-ACK perso) e dopo un lungo silenzio ritorna al gradino di incontro (fallback).
Tutti i frame sono codificati e decodificati con i formati reali (decode(encode(x)) provato in tests/sim)."""
import argparse
import math
import os
import random
import statistics
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import protocollo_immagini as pi  # noqa: E402
import limiti_chip as lim  # noqa: E402
import scala_modi as sm  # noqa: E402
import frame_mesh as fm  # noqa: E402

VERSION = 3
GUARD_S = 0.15            # commutazione trasmissione-ricezione
WINDOW_FRAMES = 16        # frame per finestra (di base)
MARGIN_UP_DB = 6.0        # margine richiesto per salire
LOSS_DOWN = 0.20          # perdita di una finestra che fa scendere
LOSS_UP = 0.02            # perdita sotto la quale si puo' salire
UP_WINDOWS = 3            # finestre di fila sotto LOSS_UP prima di tentare la salita
PROBE_COUNT = 8
PROBE_OK = 0.9
PROBE_BYTES = 32          # frame di PROBE
STATUS_RETRIES = 3
GIVE_UP_S = 900.0         # senza progressi per tanto tempo: si rinuncia
T = dict(HELLO=0, PROBE=1, PROBE_REPORT=2, MODE_SET=3, MODE_ACK=4, OFFER=5, ACCEPT=6, DATA=7, STATUS=8, PARITY=9, DONE=10, ABORT=11, ID=12,
         TEST=15)
TNAME = {v: k for k, v in T.items()}
F_LAST_WINDOW, F_RETX, F_LAST_OBJECT, F_LAYER_END = 1, 2, 4, 8
OBJ_BLOCK = 0


# ----------------------------------------------------------------------------------------------------------------- frame
def _hdr(tipo, sess, flags=0):
    return struct.pack(">BHB", (VERSION << 4) | tipo, sess & 0xFFFF, flags & 0xFF)


def _call(c):
    b = c.encode("ascii")
    return bytes([len(b)]) + b


def _s8(v):
    return struct.pack("b", max(-128, min(127, int(round(v)))))


F_POS = 16    # HELLO e OFFER: in coda la posizione (7 byte, vedi frame_mesh.pack_pos)
F_OPT = fm.F_OPT   # HELLO e OFFER: in coda opzioni TLV (revisione, profili fisici, identificativo a 32 bit, firma riservata)


def enc_hello(sess, call, chip, rung_mask, max_frame, mem_kb, reply=False, rssi=None, snr=None, pos=None, opts=None):
    """Con `rssi` e `snr` la risposta (reply) porta anche la misura del HELLO appena sentito (flag 2): il mittente puo' scegliere il gradino senza raffica di PROBE.
    Con `pos` (locatore o GPS) in coda la posizione (flag 16). Al primo contatto puo' mancare: la regola del progetto ammette il solo nominativo."""
    flags = (1 if reply else 0) | (2 if rssi is not None else 0) | (F_POS if pos is not None else 0) | (F_OPT if opts else 0)
    b = _hdr(T["HELLO"], sess, flags) + _call(call) + bytes([1 if chip == "SX1262" else 0]) + struct.pack(">HBH", rung_mask, max_frame, mem_kb)
    if rssi is not None:
        b += _s8(rssi) + _s8(snr)
    if pos is not None:
        b += fm.pack_pos(pos)
    if opts:
        b += fm.pack_opts(opts)
    return b


def enc_probe(sess, rung, idx, count, filler=PROBE_BYTES - 7):
    return _hdr(T["PROBE"], sess) + bytes([rung, idx, count]) + bytes(max(0, filler))


def enc_probe_report(sess, rung, expected, received, rssi, snr):
    return _hdr(T["PROBE_REPORT"], sess) + bytes([rung, expected, received]) + _s8(rssi) + _s8(snr)


def enc_mode_set(sess, rung, k, repeat):
    return _hdr(T["MODE_SET"], sess) + bytes([rung, k, repeat])


def enc_mode_ack(sess, rung):
    return _hdr(T["MODE_ACK"], sess) + bytes([rung])


def enc_offer(sess, call, objtype, size, piece, npieces, w, h, layer_ends, crc, pos=None, opts=None):
    """Con `pos` in coda la posizione del mittente (flag 16): nelle trasmissioni vere e' obbligatoria (docs/regole-radioamatoriali.md)."""
    return (_hdr(T["OFFER"], sess, (F_POS if pos is not None else 0) | (F_OPT if opts else 0)) + _call(call) + bytes([objtype]) + size.to_bytes(3, "big") + bytes([piece]) + struct.pack(">HHH", npieces, w, h) +
            bytes([len(layer_ends)]) + b"".join(struct.pack(">H", e) for e in layer_ends) + struct.pack(">I", crc) +
            (fm.pack_pos(pos) if pos is not None else b"") + (fm.pack_opts(opts) if opts else b""))


def enc_accept(sess, layers, window, k):
    return _hdr(T["ACCEPT"], sess) + bytes([layers, window, k])


def enc_data(sess, offset, payload, flags=0):
    return _hdr(T["DATA"], sess, flags) + struct.pack(">H", offset) + payload


def enc_status(sess, base, bitmap64, rssi, snr, loss_pct, layers_done, flags=0):
    return _hdr(T["STATUS"], sess, flags) + struct.pack(">HQ", base, bitmap64) + _s8(rssi) + _s8(snr) + bytes([min(100, int(loss_pct)), layers_done])


def enc_done(sess, call, layers_delivered, nbytes, crc_prefix):
    return _hdr(T["DONE"], sess) + _call(call) + bytes([layers_delivered]) + nbytes.to_bytes(3, "big") + struct.pack(">I", crc_prefix)


def enc_abort(sess, reason):
    return _hdr(T["ABORT"], sess) + bytes([reason])


def decode(b):
    """Decodifica un frame; ritorna un dizionario con 'tipo' e i campi, o None se non e' un frame V3 valido."""
    if len(b) < 4 or (b[0] >> 4) != VERSION:
        return None
    tipo = b[0] & 0x0F
    d = {"tipo": tipo, "nome": TNAME.get(tipo, "?"), "sess": struct.unpack(">H", b[1:3])[0], "flags": b[3], "len": len(b)}
    body = b[4:]
    try:
        if tipo == T["HELLO"]:
            n = body[0]
            d.update(call=body[1:1 + n].decode(), chip="SX1262" if body[1 + n] else "SX1278", reply=bool(d["flags"] & 1))
            d["rung_mask"], d["max_frame"], d["mem_kb"] = struct.unpack(">HBH", body[2 + n:7 + n])
            o = 7 + n
            if d["flags"] & 2:
                d["rssi"], d["snr"] = struct.unpack("bb", body[o:o + 2])
                o += 2
            if d["flags"] & F_POS:
                d["pos"] = fm.unpack_pos(body[o:o + 7])
                o += 7
            if d["flags"] & F_OPT:
                d["opts"] = fm.unpack_opts(body[o:])
        elif tipo == T["PROBE"]:
            d.update(rung=body[0], idx=body[1], count=body[2])
        elif tipo == T["PROBE_REPORT"]:
            d.update(rung=body[0], expected=body[1], received=body[2], rssi=struct.unpack("b", body[3:4])[0], snr=struct.unpack("b", body[4:5])[0])
        elif tipo == T["MODE_SET"]:
            d.update(rung=body[0], k=body[1], repeat=body[2])
        elif tipo == T["MODE_ACK"]:
            d.update(rung=body[0])
        elif tipo == T["OFFER"]:
            n = body[0]
            o = 1 + n
            d["call"] = body[1:o].decode()
            d["objtype"] = body[o]
            d["size"] = int.from_bytes(body[o + 1:o + 4], "big")
            d["piece"] = body[o + 4]
            d["npieces"], d["w"], d["h"] = struct.unpack(">HHH", body[o + 5:o + 11])
            nl = body[o + 11]
            d["layer_ends"] = [struct.unpack(">H", body[o + 12 + 2 * i:o + 14 + 2 * i])[0] for i in range(nl)]
            d["crc"] = struct.unpack(">I", body[o + 12 + 2 * nl:o + 16 + 2 * nl])[0]
            e = o + 16 + 2 * nl
            if d["flags"] & F_POS:
                d["pos"] = fm.unpack_pos(body[e:e + 7])
                e += 7
            if d["flags"] & F_OPT:
                d["opts"] = fm.unpack_opts(body[e:])
        elif tipo == T["ACCEPT"]:
            d.update(layers=body[0], window=body[1], k=body[2])
        elif tipo == T["DATA"]:
            d["offset"] = struct.unpack(">H", body[:2])[0]
            d.update(relayed=bool(d["flags"] & fm.F_RELAYED), hops=d["flags"] >> fm.HOP_SHIFT)
            d["payload"] = body[2:]
        elif tipo == T["STATUS"]:
            d["base"], d["bitmap"] = struct.unpack(">HQ", body[:10])
            d["rssi"], d["snr"] = struct.unpack("bb", body[10:12])
            d["loss_pct"], d["layers_done"] = body[12], body[13]
        elif tipo == T["DONE"]:
            n = body[0]
            d["call"] = body[1:1 + n].decode()
            d["layers"] = body[1 + n]
            d["nbytes"] = int.from_bytes(body[2 + n:5 + n], "big")
            d["crc"] = struct.unpack(">I", body[5 + n:9 + n])[0]
        elif tipo == T["ABORT"]:
            d["reason"] = body[0]
    except (IndexError, struct.error, UnicodeDecodeError):
        return None
    return d


# ---------------------------------------------------------------------------------------------------------------- canale
def noise_floor_dbm(rid):
    kind, (a, b) = pi.RUNGS[rid][1], pi.RUNGS[rid][2]
    bw_khz = a if kind == "LORA" else (a + 2 * b)
    return -174 + 10 * math.log10(bw_khz * 1000) + sm.NF


class Channel:
    """Potenza ricevuta nel tempo: `prx0` meno la perdita extra dello scenario, piu' un affievolimento per frame."""

    def __init__(self, prx0, scenario="costante", extra_db=20.0, when_s=120.0, span_s=600.0, fading_db=1.5, rng=None):
        self.prx0, self.scenario, self.extra, self.when, self.span, self.fading = prx0, scenario, extra_db, when_s, span_s, fading_db
        self.rng = rng or random.Random(1)

    def loss_extra(self, t):
        if self.scenario == "costante":
            return 0.0
        if self.scenario == "degrada":       # sale linearmente fino a extra_db in span_s secondi
            return self.extra * min(1.0, t / self.span)
        if self.scenario == "gradino":       # un salto di extra_db a when_s
            return self.extra if t >= self.when else 0.0
        if self.scenario == "oscilla":       # +- extra_db/2 con periodo span_s
            return self.extra / 2 * (1 + math.sin(2 * math.pi * t / self.span))
        raise ValueError(self.scenario)

    def prx(self, t):
        return self.prx0 - self.loss_extra(t) + self.rng.gauss(0.0, self.fading)

    def success(self, t, rid, nbytes):
        """(riuscito, potenza ricevuta) per un frame di nbytes byte a gradino rid."""
        p = self.prx(t)
        x = p - pi.sensitivity_dbm(rid)
        p_ok = 1.0 / (1.0 + math.exp(-x / 0.8))
        p_ok = p_ok ** (max(nbytes, 1) / 64.0)
        return self.rng.random() < p_ok, p


# ------------------------------------------------------------------------------------------------------------- stazioni
class Node:
    def __init__(self, name, chip, tcxo=False):
        self.name, self.chip, self.tcxo = name, chip, tcxo
        self.rung = pi.RENDEZVOUS
        self.last_heard = 0.0     # ultimo istante di attivita': frame sentito o trasmissione propria
        self.had_link = False     # ha sentito almeno un frame in questa sessione (prima la ricerca non c'e': si e' ancora all'incontro)
        self.hold_until = 0.0     # il ricevitore resta al gradino per un po' dopo aver risposto a un HELLO, per dare tempo alle prove
        self.hold = False         # il mittente tiene il gradino dopo la risposta a un HELLO, in attesa che una prova confermi
        self.lost_since = None    # istante in cui e' scaduto il timer di ascolto: da qui in poi vale il calendario della ricerca

    def mask(self):
        """Gradini annunciati nell'HELLO: quelli che il chip realizza (R0 solo SX1278, R3 d'intesa con il chip dell'altro) e R12-R14 solo con TCXO."""
        return lim.rung_mask(self.chip, self.tcxo)


SCAN_ORDER = (10, 11, 10, 12, 10, 13, 10, 14)   # calendario della ricerca: R10 a ogni secondo turno (il collegamento spesso torna), i gradini lenti a rotazione


def scan_dwell_s(rid):
    """Quanto si resta a un gradino della ricerca: almeno 120 s e abbastanza per tre HELLO."""
    return max(120.0, 3.0 * (pi.frame_airtime_s(rid, 25) + 2 * GUARD_S))


def scan_rung(elapsed_s, order=SCAN_ORDER):
    """Gradino del calendario `elapsed_s` secondi dopo l'inizio della ricerca (il calendario ricomincia dopo l'ultimo gradino)."""
    cycle = sum(scan_dwell_s(r) for r in order)
    e = elapsed_s % cycle
    for r in order:
        d = scan_dwell_s(r)
        if e < d:
            return r
        e -= d
    return order[-1]


def fallback_s(rid):
    return max(30.0, 12.0 * pi.frame_airtime_s(rid, pi.DATA_HEADER + 2 * pi.PIECE))


class Failure(Exception):
    pass


class Result:
    def __init__(self):
        self.ok = False
        self.reason = ""
        self.time_s = 0.0
        self.transfer_s = 0.0
        self.layers_delivered = 0
        self.bytes_delivered = 0
        self.crc_ok = False
        self.frames = {}
        self.retx_frames = 0
        self.data_frames = 0
        self.fallbacks = 0
        self.rung_time = {}
        self.rung_changes = []
        self.t_hello = 0.0

    def summary(self):
        return (f"{'RIUSCITO' if self.ok else 'FALLITO: ' + self.reason} in {pi.fmt_time(self.time_s)} (trasferimento {pi.fmt_time(self.transfer_s)}); livelli consegnati {self.layers_delivered}, "
                f"byte {self.bytes_delivered}, CRC {'ok' if self.crc_ok else 'no'}; frame DATA {self.data_frames} (di cui ritrasmessi {self.retx_frames}), "
                f"fallback {self.fallbacks}")


# -------------------------------------------------------------------------------------------------------------- simulatore
class Simulator:
    def __init__(self, obj_size=20000, layers=(0.2, 0.5, 1.0), channel=None, chip_a="SX1278", chip_b="SX1278", budget_s=600.0, seed=1,
                 call_a="IU5HJU", call_b="IK5XYZ", trace=False, window=WINDOW_FRAMES, max_time_s=4 * 3600.0, ricerca="calendario",
                 incontro="hello", probes_r10=PROBE_COUNT, tcxo_a=False, tcxo_b=False, data=None, layer_pieces=None):
        self.ricerca = ricerca
        self.incontro = incontro            # "hello": la risposta all'HELLO porta la misura; "probe": raffica di PROBE a R10 (vecchio)
        self.probes_r10 = probes_r10
        self.hello_metrics = None
        self.rssi_est = None            # ultima stima della potenza ricevuta (misura dell'HELLO, report delle PROBE o STATUS)
        self.rng = random.Random(seed)
        self.ch = channel or Channel(-100.0, rng=random.Random(seed + 1))
        self.S, self.R = Node("S", chip_a, tcxo_a), Node("R", chip_b, tcxo_b)
        self.t = 0.0
        self.budget = budget_s
        self.trace_on = trace
        self.log = []
        self.res = Result()
        self.call_a, self.call_b = call_a, call_b
        self.window = window
        self.max_time = max_time_s
        self.sess = self.rng.randrange(1, 65535)
        # oggetto sintetico a livelli (frazioni cumulative della dimensione)
        prng = random.Random(seed + 7)
        self.obj = bytes(data) if data is not None else bytes(prng.getrandbits(8) for _ in range(obj_size))   # data: un oggetto vero (per esempio un JPEG progressivo)
        obj_size = len(self.obj)
        self.npieces = math.ceil(obj_size / pi.PIECE)
        self.layer_ends = [max(1, min(self.npieces, math.ceil(self.npieces * f))) for f in layers]
        self.layer_ends[-1] = self.npieces
        if layer_pieces is not None:        # confini dei livelli gia' in pezzi (immagine vera: tools/immagine_livelli.pezzi)
            self.layer_ends = list(layer_pieces)
        # ricevitore
        self.r_have = [None] * self.npieces
        self.r_info = None
        self.r_window_heard = 0
        self.r_window_sent = 0
        self.r_rssi, self.r_snr, self.r_seen_in_window = [], [], 0
        self.k_now = self.k_for(pi.RENDEZVOUS)
        self.drop_hook = None     # funzione(frame decodificato) -> True per far perdere quel frame (prove)

    # ----- utilita' -----
    def tr(self, who, msg):
        line = f"[{self.t:8.2f}s] {who}: {msg}"
        self.log.append(line)
        if self.trace_on:
            print(line)

    def scan_order(self):
        """Calendario della ricerca ristretto ai gradini che entrambe le stazioni hanno annunciato (dopo l'incontro la maschera comune e' nota a tutte e due)."""
        m = lim.common_mask(self.S.chip, self.S.mask(), self.R.chip, self.R.mask())
        return tuple(r for r in SCAN_ORDER if m >> r & 1) or (pi.RENDEZVOUS,)

    def tick(self):
        """Dopo un lungo silenzio in ascolto una stazione entra in ricerca: segue il calendario dei gradini (stesso per entrambe, in funzione del tempo).
        Con ricerca="r10" (vecchio comportamento, per confronto) torna solo al gradino di incontro."""
        for n in (self.S, self.R):
            if n.lost_since is None and n.had_link and self.t - n.last_heard > fallback_s(n.rung):
                n.lost_since = n.last_heard + fallback_s(n.rung)
                self.tr(n.name, f"silenzio di {self.t - n.last_heard:.0f} s a R{n.rung}: ricerca")
                self.res.fallbacks += 1
            if n.lost_since is not None and not n.hold and self.t >= n.hold_until:
                if self.ricerca == "calendario":
                    self.set_rung(n, scan_rung(self.t - n.lost_since, self.scan_order()))
                else:
                    self.set_rung(n, pi.RENDEZVOUS)

    def set_rung(self, node, rid):
        if node.rung != rid:
            self.res.rung_changes.append((round(self.t, 1), node.name, node.rung, rid))
        node.rung = rid

    def advance(self, dt):
        self.t += dt
        self.tick()
        if self.t > self.max_time:
            raise Failure("tempo massimo di simulazione superato")

    def air(self, tx, rx, frame):
        """tx trasmette `frame` al suo gradino: ritorna il frame decodificato se rx lo sente, altrimenti None. Avanza il tempo."""
        rid = tx.rung
        a = pi.frame_airtime_s(rid, len(frame)) if len(frame) else 0.0
        self.res.rung_time[rid] = self.res.rung_time.get(rid, 0.0) + a
        d = decode(frame)
        name = d["nome"] if d else "?"
        self.res.frames[name] = self.res.frames.get(name, 0) + 1
        self.advance(a)
        tx.last_heard = self.t     # il tempo in cui si trasmette non e' silenzio: il fallback conta solo l'ascolto senza risposta
        heard = False
        p = None
        if rx.rung == rid:
            heard, p = self.ch.success(self.t, rid, len(frame))
            if heard and self.drop_hook is not None and d is not None and self.drop_hook(d):
                heard = False
        if heard:
            rx.last_heard = self.t
            rx.had_link = True
            if d is not None and d["tipo"] == T["HELLO"]:
                if d["reply"]:
                    rx.hold = True        # il mittente ha la risposta: tiene il gradino, ma resta in ricerca finche' una prova non e' confermata
                # un HELLO senza risposta non fa uscire il ricevitore dalla ricerca: continua il suo calendario
            else:
                rx.lost_since = None      # frame diverso da HELLO: collegamento ristabilito
                rx.hold = False
            tx_snr = p - noise_floor_dbm(rid)
            self._last_rssi, self._last_snr = p, tx_snr
        self.tr(tx.name, f"{name} {len(frame)}B a R{rid} ({a * 1000:.0f} ms) -> {'sentito' if heard else 'perso'}")
        return d if heard else None

    def give_up(self):
        """Tempo senza progressi dopo cui si rinuncia: 15 minuti, o quattro finestre al gradino attuale se sono piu' lunghe."""
        return max(GIVE_UP_S, 4.0 * self.window * pi.frame_airtime_s(self.S.rung, pi.DATA_HEADER + 2 * pi.PIECE))

    def k_for(self, rid):
        """Pezzi per frame DATA a un gradino: il minimo fra i due chip (devono capirsi)."""
        return min(pi.pieces_per_frame(rid, self.S.chip), pi.pieces_per_frame(rid, self.R.chip))

    def guard(self):
        self.advance(GUARD_S)

    # ----- ricevitore -----
    def r_handle(self, f):
        """Il ricevitore reagisce a un frame (gia' decodificato). Ritorna il frame di risposta (bytes) o None."""
        t = f["tipo"]
        if t == T["HELLO"] and not f["reply"]:
            self.s_caps = f
            if self.R.lost_since is not None:      # in ricerca: resta qui il tempo di 12 frame, poi riprende il calendario (che e' in funzione del tempo)
                self.R.hold_until = self.t + max(60.0, 12.0 * pi.frame_airtime_s(self.R.rung, PROBE_BYTES))
            if self.incontro == "hello":
                return enc_hello(self.sess, self.call_b, self.R.chip, self.R.mask(), pi.max_frame(pi.RENDEZVOUS, self.R.chip), 100, reply=True,
                                 rssi=self._last_rssi, snr=self._last_snr)
            return enc_hello(self.sess, self.call_b, self.R.chip, self.R.mask(), pi.max_frame(pi.RENDEZVOUS, self.R.chip), 100, reply=True)
        if t == T["PROBE"]:
            self.r_rssi.append(self._last_rssi)
            self.r_snr.append(self._last_snr)
            self.probe_heard = getattr(self, "probe_heard", 0) + 1
            self.probe_count = f["count"]
            self.probe_rung = f["rung"]
            return None
        if t == T["MODE_SET"]:
            self.r_pending = (f["rung"], f["k"])
            return enc_mode_ack(self.sess, f["rung"])
        if t == T["OFFER"]:
            self.r_info = f
            self.r_have = [None] * f["npieces"]
            return enc_accept(self.sess, len(f["layer_ends"]), self.window, 1)
        if t == T["DATA"]:
            self.r_window_heard += 1
            self.r_rssi.append(self._last_rssi)
            self.r_snr.append(self._last_snr)
            off = f["offset"]
            pl = f["payload"]
            for i in range(math.ceil(len(pl) / pi.PIECE)):
                if off + i < len(self.r_have):
                    self.r_have[off + i] = pl[i * pi.PIECE:(i + 1) * pi.PIECE]
            return None
        if t == T["DONE"]:
            have = self.r_have
            n_ok = 0
            for p in have:
                if p is None:
                    break
                n_ok += 1
            data = b"".join(have[:n_ok])[:f["nbytes"]]
            self.r_done = (len(data) == f["nbytes"] and (zlib.crc32(data) & 0xFFFFFFFF) == f["crc"], f["layers"], len(data))
            return enc_status(self.sess, n_ok, 0, 0, 0, 0, f["layers"], flags=1)
        return None

    def r_status(self, sent_blocks, k):
        """STATUS del ricevitore alla fine di una finestra: base = primo pezzo mancante, un bit per blocco di k pezzi."""
        have = self.r_have
        base = 0
        while base < len(have) and have[base] is not None:
            base += 1
        bm = 0
        for i in range(64):
            lo = base + i * k
            if lo >= len(have):
                break
            blk = have[lo:lo + k]
            if all(x is not None for x in blk):
                bm |= 1 << (63 - i)
        rs = statistics.mean(self.r_rssi) if self.r_rssi else -128
        sn = statistics.mean(self.r_snr) if self.r_snr else -128
        loss = 100.0 * (1 - min(self.r_window_heard, sent_blocks) / sent_blocks) if sent_blocks else 0.0
        ld = sum(1 for e in self.r_info["layer_ends"] if base >= e) if self.r_info else 0
        self.r_rssi, self.r_snr = [], []
        self.r_window_heard = 0
        return enc_status(self.sess, base, bm, rs, sn, loss, ld)

    # ----- scambi -----
    def exchange(self, frame, expect, tries=1):
        """Il mittente manda `frame`; il ricevitore risponde (se sente); ritorna la risposta decodificata (tipo atteso) o None."""
        for _ in range(tries):
            f = self.air(self.S, self.R, frame)
            reply = None
            if f is not None:
                reply = self.r_handle(f)
            if reply is not None:
                self.guard()
                rf = self.air(self.R, self.S, reply)
                if rf is not None and rf["tipo"] == expect:
                    self.guard()
                    return rf
            else:
                self.advance(pi.frame_airtime_s(self.S.rung, 20) + 2 * GUARD_S)   # attesa della risposta che non arriva
            self.guard()
        return None

    # ----- fasi -----
    def phase_hello(self):
        wait = 5.0
        t0 = self.t
        while True:
            r = self.exchange(enc_hello(self.sess, self.call_a, self.S.chip, self.S.mask(), pi.max_frame(10, self.S.chip), 100), T["HELLO"])
            if r is not None:
                self.caps = r
                if "rssi" in r:
                    self.hello_metrics = (r["rssi"], r["snr"])
                self.res.t_hello = self.t - t0
                return
            self.advance(wait * (0.8 + 0.4 * self.rng.random()))
            wait = min(60.0, wait * 2)
            if self.t - t0 > 600.0:
                raise Failure("nessun incontro (HELLO senza risposta)")

    def allowed(self):
        m = lim.common_mask(self.S.chip, self.S.mask(), self.R.chip, self.caps["rung_mask"])
        return [r for r in range(len(pi.RUNGS)) if m >> r & 1]

    def probe(self, rid_check=None):
        """Raffica di PROBE al gradino attuale; ritorna (ricevuti, attesi, rssi, snr) dal report, o None."""
        n = self.probes_r10 if self.S.rung <= pi.RENDEZVOUS else 4
        self.probe_heard = 0
        self.r_rssi, self.r_snr = [], []
        for i in range(n):
            r = self.air(self.S, self.R, enc_probe(self.sess, self.S.rung, i, n))
            if r is not None:
                self.r_handle(r)
        # il ricevitore manda il PROBE-REPORT a timer, dopo la raffica, se ne ha sentito almeno uno (come lo STATUS dopo una finestra)
        if self.probe_heard == 0:
            self.advance(2 * GUARD_S)
            return None
        rs, sn = statistics.mean(self.r_rssi), statistics.mean(self.r_snr)
        rep = enc_probe_report(self.sess, self.S.rung, n, self.probe_heard, rs, sn)
        self.r_rssi, self.r_snr = [], []
        self.probe_heard = 0
        self.guard()
        rf = self.air(self.R, self.S, rep)
        self.guard()
        if rf is None:
            return None
        return rf["received"], rf["expected"], rf["rssi"], rf["snr"]

    def switch(self, target):
        """MODE-SET (3 volte) al gradino attuale e MODE-ACK; poi entrambe passano al nuovo gradino. True se il mittente ha sentito l'ACK."""
        k = self.k_for(target)
        for rep in range(3):
            f = self.air(self.S, self.R, enc_mode_set(self.sess, target, k, rep))
            if f is not None:
                ack = self.r_handle(f)
                self.guard()
                # il ricevitore passa al nuovo gradino alla fine del MODE-ACK, sia che il mittente lo senta o no
                rack = self.air(self.R, self.S, ack)
                self.set_rung(self.R, target)
                if rack is not None:
                    self.set_rung(self.S, target)
                    self.k_now = k
                    self.guard()
                    return True
            self.advance(pi.frame_airtime_s(self.S.rung, 8) + 2 * GUARD_S)
        return False

    def resync(self):
        """Dopo un cambio non confermato o un silenzio le due stazioni possono stare su gradini diversi: il mittente aspetta di essere in ricerca
        come il ricevitore, poi manda HELLO al gradino del calendario in cui si trova finche' il ricevitore risponde."""
        self.tr("--", f"disallineamento o silenzio (S=R{self.S.rung}, R=R{self.R.rung}): ricerca")
        t0 = self.t
        self.S.hold = False
        if self.ricerca != "calendario":
            wait = max(fallback_s(self.S.rung), fallback_s(self.R.rung)) + 1.0
            self.advance(wait)
            for n in (self.S, self.R):
                if n.rung != pi.RENDEZVOUS:
                    self.set_rung(n, pi.RENDEZVOUS)
            self.k_now = self.k_for(pi.RENDEZVOUS)
            return
        while self.S.lost_since is None:          # il mittente entra in ricerca con lo stesso timer del ricevitore
            self.advance(1.0)
        while True:
            hello = enc_hello(self.sess, self.call_a, self.S.chip, self.S.mask(), pi.max_frame(10, self.S.chip), 100)
            r = self.exchange(hello, T["HELLO"])
            if r is not None:
                self.k_now = self.k_for(self.S.rung)
                self.just_reconnected = True     # lo scambio di HELLO ha gia' provato il collegamento: niente nuova raffica di PROBE
                self.tr("--", f"ritrovati a R{self.S.rung} dopo {self.t - t0:.0f} s")
                return
            self.advance(pi.frame_airtime_s(self.S.rung, 25) * (1.0 + self.rng.random()))
            if self.t - t0 > max(GIVE_UP_S, 3.0 * sum(scan_dwell_s(r) for r in self.scan_order())):   # tre giri del calendario
                raise Failure("collegamento perso (la ricerca non ha ritrovato la stazione)")

    def predicted_best(self, prx_est, allowed, margin):
        """Il gradino piu' veloce con il margine richiesto; se nessuno lo ha, con 3 dB; se neppure, il piu' lento ammesso."""
        for m in (margin, 3.0):
            for r in allowed:
                if prx_est - pi.sensitivity_dbm(r) >= m:
                    return r
        return allowed[-1]

    def negotiate(self, want_up=True):
        """Dal gradino attuale cerca il gradino migliore: misura (PROBE), propone (MODE-SET), verifica (PROBE) e scende se non regge."""
        allowed = self.allowed()
        if getattr(self, "just_reconnected", False):
            self.just_reconnected = False
            return
        fails = 0
        for attempt in range(8):
            if self.hello_metrics is not None:           # la misura e' gia' arrivata con la risposta all'HELLO: niente raffica
                rs, sn = self.hello_metrics
                self.hello_metrics = None
                m = (1, 1, rs, sn)
            else:
                m = self.probe()
            if m is None:
                fails += 1
                if fails >= 2:
                    self.resync()
                    fails = 0
                else:
                    self.advance(5.0)
                continue
            rec, exp, rssi, snr = m
            self.rssi_est = rssi
            target = self.predicted_best(rssi, allowed, MARGIN_UP_DB)
            if target == self.S.rung:
                return
            if target > self.S.rung and rec >= PROBE_OK * exp:
                return       # il gradino attuale ha appena dimostrato di funzionare (>= 90 % delle prove): non si scende senza motivo
            ok = self.switch(target)
            if not ok:
                self.resync()
                continue
            # verifica al nuovo gradino, scendendo se serve
            while True:
                m2 = self.probe()
                if m2 is not None and m2[0] >= PROBE_OK * m2[1]:
                    return
                slower = [r for r in allowed if r > self.S.rung]
                if not slower:
                    return
                if not self.switch(slower[0]):
                    self.resync()
                    break
        raise Failure("negoziazione del gradino non riuscita")

    def target_layers(self, acked_prefix_pieces):
        """Quanti livelli stanno nel budget di tempo, con il gradino attuale: il primo e' obbligatorio. Ritorna l'indice dell'ultimo livello."""
        elapsed = self.t - self.t_transfer0
        rid = self.S.rung
        best = 0
        for i, e in enumerate(self.layer_ends):
            remaining = max(0, e - acked_prefix_pieces) * pi.PIECE
            est = pi.estimate_seconds(remaining, rid, self.S.chip) if remaining else 0.0
            if elapsed + est <= self.budget:
                best = i
        return best

    def phase_transfer(self):
        crc_obj = zlib.crc32(self.obj) & 0xFFFFFFFF
        offer = enc_offer(self.sess, self.call_a, OBJ_BLOCK, len(self.obj), pi.PIECE, self.npieces, 0, 0, self.layer_ends, crc_obj)
        acc = None
        for attempt in range(4):
            acc = self.exchange(offer, T["ACCEPT"], tries=2)
            if acc is not None:
                break
            self.resync()
            self.negotiate()
        if acc is None:
            raise Failure("OFFER senza ACCEPT")
        self.t_transfer0 = self.t
        # budget iniziale: il primo livello deve entrare, altrimenti non si parte
        # il primo livello deve entrare nel budget al gradino migliore che la misura lascia sperare (margine 3 dB): una sola misura e' rumorosa,
        # e dopo le prime finestre il mittente puo' ancora salire di gradino
        rid_best = min(self.S.rung, self.predicted_best(self.rssi_est, self.allowed(), 3.0)) if self.rssi_est is not None else self.S.rung
        est0 = pi.estimate_seconds(self.layer_ends[0] * pi.PIECE, rid_best, self.S.chip)
        if est0 > self.budget:
            self.air(self.S, self.R, enc_abort(self.sess, 1))
            raise Failure(f"il primo livello non entra nel budget (stima {pi.fmt_time(est0)} contro {pi.fmt_time(self.budget)})")
        acked = [False] * self.npieces
        frontier = 0
        good_windows = 0
        up_block = 0
        last_progress = self.t
        status_fail = 0
        while True:
            base = 0
            while base < self.npieces and acked[base]:
                base += 1
            tl = self.target_layers(base)
            end = self.layer_ends[tl]
            if base >= end:
                break
            k = self.k_now
            # finestra: prima i pezzi non confermati gia' inviati, poi i nuovi, fino a `window` frame
            todo, retx_set = [], set()
            for p in range(base, min(frontier, end)):
                if not acked[p]:
                    todo.append(p)
                    retx_set.add(p)
            p = max(frontier, base)
            while p < end and len(todo) < self.window * k:
                todo.append(p)
                p += 1
            frames = []
            run = []
            for p in todo:
                if run and (p != run[-1] + 1 or len(run) >= k):
                    frames.append(run)
                    run = []
                run.append(p)
            if run:
                frames.append(run)
            frames = frames[:self.window]
            heard_last = False
            for fi, run in enumerate(frames):
                payload = self.obj[run[0] * pi.PIECE:(run[-1] + 1) * pi.PIECE]
                fl = (F_LAST_WINDOW if fi == len(frames) - 1 else 0) | (F_RETX if run[0] in retx_set else 0)
                if run[-1] + 1 in self.layer_ends:
                    fl |= F_LAYER_END
                if run[-1] + 1 == self.npieces:
                    fl |= F_LAST_OBJECT
                f = self.air(self.S, self.R, enc_data(self.sess, run[0], payload, fl))
                self.res.data_frames += 1
                if fl & F_RETX:
                    self.res.retx_frames += 1
                if f is not None:
                    self.r_handle(f)
                    heard_last = heard_last or bool(fl & F_LAST_WINDOW)
                frontier = max(frontier, run[-1] + 1)
            # il ricevitore manda lo STATUS dopo l'ultimo frame, o (a timer) se ne ha sentito qualcuno
            st = None
            for attempt in range(STATUS_RETRIES):
                self.guard()
                if self.r_window_heard > 0:
                    stf = self.r_status(len(frames), k)
                    rf = self.air(self.R, self.S, stf)
                    self.guard()
                    if rf is not None:
                        st = rf
                        break
                # STATUS perso o nessun frame sentito: il mittente ripete l'ultimo frame con il flag di ultima finestra
                self.advance(pi.frame_airtime_s(self.S.rung, 20) + GUARD_S)
                last = frames[-1]
                payload = self.obj[last[0] * pi.PIECE:(last[-1] + 1) * pi.PIECE]
                f = self.air(self.S, self.R, enc_data(self.sess, last[0], payload, F_LAST_WINDOW | F_RETX))
                self.res.data_frames += 1
                self.res.retx_frames += 1
                if f is not None:
                    self.r_handle(f)
            if st is None:
                status_fail += 1
                self.tr("S", "nessun STATUS: scendo di un gradino")
                if not self._step_down():
                    self.resync()
                    self.negotiate()
                good_windows = 0
                if self.t - last_progress > self.give_up():
                    raise Failure("collegamento perso (nessun progresso)")
                continue
            status_fail = 0
            # il mittente aggiorna cio' che sa dallo STATUS
            self.rssi_est = st["rssi"]
            for pidx in range(min(st["base"], self.npieces)):
                if not acked[pidx]:
                    acked[pidx] = True
                    last_progress = self.t
            for i in range(64):
                if st["bitmap"] >> (63 - i) & 1:
                    lo = st["base"] + i * k
                    for pidx in range(lo, min(lo + k, self.npieces)):
                        if not acked[pidx]:
                            acked[pidx] = True
                            last_progress = self.t
            loss = st["loss_pct"] / 100.0
            if loss > LOSS_DOWN:
                good_windows = 0
                self.tr("S", f"perdita {loss * 100:.0f} % > {LOSS_DOWN * 100:.0f} %: scendo")
                if not self._step_down():
                    self.resync()
                    self.negotiate()
            elif loss < LOSS_UP:
                good_windows += 1
                if good_windows >= UP_WINDOWS and up_block <= 0:
                    good_windows = 0
                    faster = [r for r in self.allowed() if r < self.S.rung]
                    if faster:
                        cand = faster[-1]
                        if st["rssi"] - pi.sensitivity_dbm(cand) >= MARGIN_UP_DB:
                            old = self.S.rung
                            self.tr("S", f"{UP_WINDOWS} finestre buone: provo R{cand}")
                            if self.switch(cand):
                                m = self.probe()
                                if m is None or m[0] < PROBE_OK * m[1]:
                                    self.tr("S", "verifica fallita: torno indietro")
                                    if not self.switch(old):
                                        self.resync()
                                        self.negotiate()
                                    up_block = 5
                            else:
                                self.resync()
                                self.negotiate()
                                up_block = 5
                up_block -= 1
            else:
                good_windows = 0
                up_block -= 1
            if self.t - last_progress > self.give_up():
                raise Failure("collegamento perso (nessun progresso)")
        # DONE con il CRC dei byte consegnati (fino alla fine dell'ultimo livello completo)
        li = sum(1 for e in self.layer_ends if base >= e)
        end_p = self.layer_ends[li - 1]
        nbytes = min(len(self.obj), end_p * pi.PIECE)
        done = enc_done(self.sess, self.call_a, li, nbytes, zlib.crc32(self.obj[:nbytes]) & 0xFFFFFFFF)
        rf = self.exchange(done, T["STATUS"], tries=4)
        if rf is None:
            # la consegna e' avvenuta se il ricevitore lo ha sentito: verifica dal lato del ricevitore
            if getattr(self, "r_done", None) is None:
                raise Failure("DONE non confermato")
        self.res.layers_delivered, self.res.bytes_delivered = li, nbytes
        self.res.crc_ok = bool(getattr(self, "r_done", (False,))[0])

    def _step_down(self):
        slower = [r for r in self.allowed() if r > self.S.rung]
        if not slower:
            return True   # gia' al piu' lento ammesso
        return self.switch(slower[0])

    def run(self):
        try:
            self.phase_hello()
            self.negotiate()
            self.phase_transfer()
            self.res.ok = True
        except Failure as e:
            self.res.reason = str(e)
            self.tr("--", f"FALLITO: {e}")
        self.res.time_s = self.t
        self.res.transfer_s = self.t - getattr(self, "t_transfer0", self.t)
        return self.res


# ------------------------------------------------------------------------------------------------------------------ CLI
def run_once(args, seed):
    ch = Channel(args.prx, args.scenario, args.extra, args.when, args.span, rng=random.Random(seed + 1))
    layers = tuple((i + 1) / args.layers for i in range(args.layers))
    sim = Simulator(args.size, layers, ch, args.chip, args.chip, args.budget, seed, trace=args.trace, ricerca=args.ricerca, incontro=getattr(args, "incontro", "hello"),
                    probes_r10=getattr(args, "probes", PROBE_COUNT))
    return sim, sim.run()


def sweep(args):
    print(f"Oggetto {args.size} byte, {args.layers} livelli, scenario {args.scenario}, budget {pi.fmt_time(args.budget)}, {args.runs} prove per riga\n")
    print("| P rx dBm | riuscite | livelli (mediana) | tempo mediano | di cui trasferimento | ritrasmessi | fallback medi |")
    print("|---|---|---|---|---|---|---|")
    for prx in args.sweep_values:
        results = []
        for s in range(args.runs):
            a = argparse.Namespace(**vars(args))
            a.prx = prx
            a.trace = False
            _, r = run_once(a, s + 1)
            results.append(r)
        okr = [r for r in results if r.ok]
        tm = statistics.median(r.time_s for r in okr) if okr else float("nan")
        tt = statistics.median(r.transfer_s for r in okr) if okr else float("nan")
        lay = statistics.median(r.layers_delivered for r in okr) if okr else 0
        retx = statistics.mean((r.retx_frames / r.data_frames) if r.data_frames else 0 for r in okr) * 100 if okr else float("nan")
        fb = statistics.mean(r.fallbacks for r in results)
        print(f"| {prx:g} | {len(okr)}/{len(results)} | {lay:g} | {pi.fmt_time(tm) if okr else '—'} | {pi.fmt_time(tt) if okr else '—'} | "
              f"{retx:.0f} % | {fb:.1f} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--size", type=int, default=20000)
    ap.add_argument("--layers", type=int, default=3)
    ap.add_argument("--prx", type=float, default=-100.0, help="potenza ricevuta di partenza, dBm")
    ap.add_argument("--scenario", default="costante", choices=["costante", "degrada", "gradino", "oscilla"])
    ap.add_argument("--extra", type=float, default=20.0, help="perdita extra dello scenario, dB")
    ap.add_argument("--when", type=float, default=120.0, help="istante del gradino, s")
    ap.add_argument("--span", type=float, default=600.0, help="durata della rampa o periodo, s")
    ap.add_argument("--budget", type=float, default=600.0, help="budget di tempo per oggetto, s")
    ap.add_argument("--chip", default="SX1278", choices=["SX1278", "SX1262"])
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--incontro", default="hello", choices=["hello", "probe"], help="misura del collegamento all'incontro: nella risposta all'HELLO (nuovo) o con una raffica di PROBE (vecchio)")
    ap.add_argument("--probes", type=int, default=PROBE_COUNT, help="PROBE della raffica a R10 (solo con --incontro probe)")
    ap.add_argument("--ricerca", default="calendario", choices=["calendario", "r10"], help="cosa fanno le stazioni dopo un lungo silenzio: calendario dei gradini lenti (nuovo) o solo ritorno a R10 (vecchio)")
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--runs", type=int, default=10)
    a = ap.parse_args()
    a.sweep_values = [-80, -90, -100, -110, -115, -120, -125, -130, -135, -138]
    if a.sweep:
        sweep(a)
        return
    sim, res = run_once(a, a.seed)
    print(res.summary())
    print("tempo per gradino (aria):", {f"R{k}": f"{v:.0f}s" for k, v in sorted(res.rung_time.items())})
    print("frame:", res.frames)
    print("cambi di gradino:", res.rung_changes[:20], "..." if len(res.rung_changes) > 20 else "")


if __name__ == "__main__":
    main()
