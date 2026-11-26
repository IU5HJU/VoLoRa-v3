#!/usr/bin/env python3
"""Protocollo immagini V3 (docs/protocollo-immagini.md) come PROTOCOLLO, senza canale e senza orologio: tre pezzi indipendenti che il simulatore (tools/sim_immagini.py)
e, in futuro, il firmware (firmware/v3) fanno girare sul loro mezzo.

 * `Link`      lo stato del collegamento di una stazione: gradino, silenzio, ricerca a calendario, "tenuta" del gradino.
 * `Receiver`  il ricevitore: reagisce a un frame ricevuto con un frame di risposta; compone STATUS e PROBE-REPORT; tiene i pezzi.
 * `Sender`    il mittente: un PROCESSO (generatore) che, per ogni passo, CHIEDE al mezzo di fare qualcosa (azioni) e riceve la risposta. Non vede il canale, non vede
               il ricevitore, non vede l'orologio se non attraverso il tempo che il mezzo gli passa a ogni ripresa.

Azioni del mittente (tuple, il primo elemento dice quale):
  ("exchange", frame, atteso, tentativi)   manda un frame e aspetta la risposta del tipo atteso; risposta: frame decodificato o None
  ("probe", [frame...])                    raffica di PROBE e PROBE-REPORT del ricevitore; risposta: report decodificato o None
  ("modeset", frame, gradino)              MODE-SET e MODE-ACK; il ricevitore passa al nuovo gradino dopo l'ACK; risposta: ACK decodificato o None
  ("burst", [frame...])                    frame trasmessi di seguito (dati, abort); nessuna risposta
  ("status", frame_inviati, k)             richiesta dello STATUS dopo una finestra; risposta: STATUS decodificato o None
  ("wait", secondi)                        il mittente aspetta
  ("rand",)                                un numero casuale in [0, 1)
  ("setrung", gradino)                     il mittente passa a un altro gradino
  ("holdclear",)                           il mittente smette di tenere il gradino
  ("legacy",)                              (solo simulatore, confronto) vecchia ricerca che torna a R10
  ("oracle",)                              (solo simulatore) il ricevitore ha sentito il DONE?
  ("note", testo)                          riga di diario
Ad ogni ripresa il mezzo aggiorna `sender.t` (ora), `sender.rung` (gradino) e `sender.lost` (in ricerca).
Il mittente finisce con `Failure(motivo)` oppure con la restituzione (livelli consegnati, byte consegnati).
Questa e' la parte che il firmware C++ riprende (firmware/v3/src, prove di conformita' con vettori generati da qui)."""
import math
import os
import statistics
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import limiti_chip as lim  # noqa: E402
import protocollo_immagini as pi  # noqa: E402
from img_frames import (F_LAST_OBJECT, F_LAST_WINDOW, F_LAYER_END, F_RETX, OBJ_BLOCK, PROBE_BYTES, T, enc_abort, enc_accept, enc_data, enc_done, enc_hello,  # noqa: E402
                        enc_mode_ack, enc_mode_set, enc_offer, enc_probe, enc_probe_report, enc_status)

GUARD_S = 0.15            # commutazione trasmissione-ricezione
WINDOW_FRAMES = 16        # frame per finestra (di base)
MARGIN_UP_DB = 6.0        # margine richiesto per salire
LOSS_DOWN = 0.20          # perdita di una finestra che fa scendere
LOSS_UP = 0.02            # perdita sotto la quale si puo' salire
UP_WINDOWS = 3            # finestre di fila sotto LOSS_UP prima di tentare la salita
PROBE_COUNT = 8
PROBE_OK = 0.9
STATUS_RETRIES = 3
GIVE_UP_S = 900.0         # senza progressi per tanto tempo: si rinuncia

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


def scan_order_for(chip_a, mask_a, chip_b, mask_b):
    """Calendario della ricerca ristretto ai gradini che entrambe le stazioni hanno annunciato."""
    m = lim.common_mask(chip_a, mask_a, chip_b, mask_b)
    return tuple(r for r in SCAN_ORDER if m >> r & 1) or (pi.RENDEZVOUS,)


class Failure(Exception):
    pass


# --------------------------------------------------------------------------------------------------------------------------------- il collegamento
class Link:
    """Stato del collegamento di una stazione (gradino, silenzio, ricerca). Il mezzo lo aggiorna a ogni passaggio di tempo e a ogni frame trasmesso o sentito."""

    def __init__(self, name):
        self.name = name
        self.rung = pi.RENDEZVOUS
        self.last_heard = 0.0     # ultimo istante di attivita': frame sentito o trasmissione propria
        self.had_link = False     # ha sentito almeno un frame in questa sessione (prima la ricerca non c'e': si e' ancora all'incontro)
        self.hold_until = 0.0     # il ricevitore resta al gradino per un po' dopo aver risposto a un HELLO, per dare tempo alle prove
        self.hold = False         # il mittente tiene il gradino dopo la risposta a un HELLO, in attesa che una prova confermi
        self.lost_since = None    # istante in cui e' scaduto il timer di ascolto: da qui in poi vale il calendario della ricerca

    def tick(self, t, scan_order, ricerca="calendario"):
        """Dopo un lungo silenzio in ascolto la stazione entra in ricerca: segue il calendario dei gradini (stesso per entrambe, in funzione del tempo).
        Con ricerca="r10" (vecchio comportamento, per confronto) torna solo al gradino di incontro. Ritorna gli eventi: ('fallback', silenzio, gradino), ('rung', vecchio, nuovo)."""
        ev = []
        if self.lost_since is None and self.had_link and t - self.last_heard > fallback_s(self.rung):
            self.lost_since = self.last_heard + fallback_s(self.rung)
            ev.append(("fallback", t - self.last_heard, self.rung))
        if self.lost_since is not None and not self.hold and t >= self.hold_until:
            new = scan_rung(t - self.lost_since, scan_order()) if ricerca == "calendario" else pi.RENDEZVOUS
            if new != self.rung:
                ev.append(("rung", self.rung, new))
            self.rung = new
        return ev

    def set_rung(self, rid):
        ev = [("rung", self.rung, rid)] if self.rung != rid else []
        self.rung = rid
        return ev

    def on_tx(self, t):
        self.last_heard = t      # il tempo in cui si trasmette non e' silenzio: il fallback conta solo l'ascolto senza risposta

    def on_heard(self, t, tipo, reply):
        """Un frame sentito (tipo None se non decodificabile)."""
        self.last_heard = t
        self.had_link = True
        if tipo == T["HELLO"]:
            if reply:
                self.hold = True      # il mittente ha la risposta: tiene il gradino, ma resta in ricerca finche' una prova non e' confermata
            # un HELLO senza risposta non fa uscire il ricevitore dalla ricerca: continua il suo calendario
        else:
            self.lost_since = None    # frame diverso da HELLO: collegamento ristabilito
            self.hold = False


# --------------------------------------------------------------------------------------------------------------------------------- il ricevitore
class Reply:
    """Cosa fa il ricevitore dopo un frame: un frame di risposta (o None), un nuovo `hold_until`, un cambio di gradino dopo la trasmissione della risposta."""
    __slots__ = ("frame", "hold_until", "rung_after")

    def __init__(self, frame=None, hold_until=None, rung_after=None):
        self.frame, self.hold_until, self.rung_after = frame, hold_until, rung_after


class Receiver:
    def __init__(self, call, chip, tcxo, window, incontro):
        self.call, self.chip, self.tcxo, self.window, self.incontro = call, chip, tcxo, window, incontro
        self.sess = 0
        self.s_caps = None
        self.have = []
        self.info = None
        self.window_heard = 0
        self.rssi, self.snr = [], []
        self.probe_heard = 0
        self.probe_count = 0
        self.probe_rung = 0
        self.pending = None
        self.done = None          # (CRC giusto?, livelli, byte) dopo un DONE

    def mask(self):
        return lim.rung_mask(self.chip, self.tcxo)

    def scan_order(self):
        """Il calendario della ricerca: serve la maschera dell'altra stazione, che il ricevitore conosce dal HELLO."""
        if self.s_caps is None:
            return (pi.RENDEZVOUS,)
        return scan_order_for(self.chip, self.mask(), "SX1262" if self.s_caps["chip"] == "SX1262" else "SX1278", self.s_caps["rung_mask"])

    def on_frame(self, f, rssi, snr, t, rung, lost):
        """Il ricevitore reagisce a un frame decodificato (sentito con `rssi` e `snr`) all'ora `t`, al gradino `rung`, in ricerca se `lost`."""
        tp = f["tipo"]
        self.sess = f["sess"]
        if tp == T["HELLO"] and not f["reply"]:
            self.s_caps = f
            hold = t + max(60.0, 12.0 * pi.frame_airtime_s(rung, PROBE_BYTES)) if lost else None     # in ricerca: resta qui il tempo di 12 frame, poi riprende il calendario
            kw = dict(rssi=rssi, snr=snr) if self.incontro == "hello" else {}
            return Reply(enc_hello(self.sess, self.call, self.chip, self.mask(), pi.max_frame(pi.RENDEZVOUS, self.chip), 100, reply=True, **kw), hold_until=hold)
        if tp == T["PROBE"]:
            if f["idx"] == 0:
                self.rssi, self.snr, self.probe_heard = [], [], 0
            self.rssi.append(rssi)
            self.snr.append(snr)
            self.probe_heard += 1
            self.probe_count = f["count"]
            self.probe_rung = f["rung"]
            return Reply()
        if tp == T["MODE_SET"]:
            self.pending = (f["rung"], f["k"])
            return Reply(enc_mode_ack(self.sess, f["rung"]), rung_after=f["rung"])
        if tp == T["OFFER"]:
            self.info = f
            self.have = [None] * f["npieces"]
            return Reply(enc_accept(self.sess, len(f["layer_ends"]), self.window, 1))
        if tp == T["DATA"]:
            self.window_heard += 1
            self.rssi.append(rssi)
            self.snr.append(snr)
            off, pl = f["offset"], f["payload"]
            for i in range(math.ceil(len(pl) / pi.PIECE)):
                if off + i < len(self.have):
                    self.have[off + i] = pl[i * pi.PIECE:(i + 1) * pi.PIECE]
            return Reply()
        if tp == T["DONE"]:
            n_ok = 0
            for p in self.have:
                if p is None:
                    break
                n_ok += 1
            data = b"".join(self.have[:n_ok])[:f["nbytes"]]
            self.done = (len(data) == f["nbytes"] and (zlib.crc32(data) & 0xFFFFFFFF) == f["crc"], f["layers"], len(data))
            return Reply(enc_status(self.sess, n_ok, 0, 0, 0, 0, f["layers"], flags=1))
        return Reply()

    def status(self, sent_blocks, k):
        """STATUS alla fine di una finestra: base = primo pezzo mancante, un bit per blocco di k pezzi. `sent_blocks` e' il numero di frame della finestra
        (semplificazione del simulatore: nel protocollo vero il ricevitore lo deve ricavare dai frame, vedi docs/firmware-v3.md)."""
        have = self.have
        base = 0
        while base < len(have) and have[base] is not None:
            base += 1
        bm = 0
        for i in range(64):
            lo = base + i * k
            if lo >= len(have):
                break
            if all(x is not None for x in have[lo:lo + k]):
                bm |= 1 << (63 - i)
        rs = statistics.mean(self.rssi) if self.rssi else -128
        sn = statistics.mean(self.snr) if self.snr else -128
        loss = 100.0 * (1 - min(self.window_heard, sent_blocks) / sent_blocks) if sent_blocks else 0.0
        ld = sum(1 for e in self.info["layer_ends"] if base >= e) if self.info else 0
        self.rssi, self.snr = [], []
        self.window_heard = 0
        return enc_status(self.sess, base, bm, rs, sn, loss, ld)

    def probe_report(self):
        """Il PROBE-REPORT a timer, dopo la raffica, se ha sentito almeno un PROBE (come lo STATUS dopo una finestra); None se non ne ha sentiti."""
        if self.probe_heard == 0:
            return None
        rs, sn = statistics.mean(self.rssi), statistics.mean(self.snr)
        rep = enc_probe_report(self.sess, self.probe_rung, self.probe_count, self.probe_heard, rs, sn)
        self.rssi, self.snr = [], []
        self.probe_heard = 0
        return rep


# --------------------------------------------------------------------------------------------------------------------------------- il mittente
class Sender:
    def __init__(self, sess, call, chip, tcxo, obj, layer_ends, budget, window, ricerca="calendario", probes_r10=PROBE_COUNT):
        self.sess, self.call, self.chip, self.tcxo = sess, call, chip, tcxo
        self.obj, self.layer_ends, self.budget, self.window, self.ricerca, self.probes_r10 = obj, list(layer_ends), budget, window, ricerca, probes_r10
        self.npieces = math.ceil(len(obj) / pi.PIECE)
        # il mezzo li aggiorna a ogni ripresa
        self.t, self.rung, self.lost = 0.0, pi.RENDEZVOUS, False
        # cio' che il mittente impara
        self.caps = None
        self.peer_chip = None
        self.hello_metrics = None
        self.rssi_est = None
        self.just_reconnected = False
        self.k_now = None
        self.t_hello = 0.0
        self.t_transfer0 = None
        self.result = None

    def mask(self):
        return lim.rung_mask(self.chip, self.tcxo)

    def k_for(self, rid):
        """Pezzi per frame DATA a un gradino: il minimo fra i due chip (devono capirsi)."""
        return min(pi.pieces_per_frame(rid, self.chip), pi.pieces_per_frame(rid, self.peer_chip))

    def allowed(self):
        m = lim.common_mask(self.chip, self.mask(), self.peer_chip, self.caps["rung_mask"])
        return [r for r in range(len(pi.RUNGS)) if m >> r & 1]

    def scan_order(self):
        return scan_order_for(self.chip, self.mask(), self.peer_chip, self.caps["rung_mask"])

    def hello_frame(self):
        return enc_hello(self.sess, self.call, self.chip, self.mask(), pi.max_frame(10, self.chip), 100)

    def give_up(self):
        """Tempo senza progressi dopo cui si rinuncia: 15 minuti, o quattro finestre al gradino attuale se sono piu' lunghe."""
        return max(GIVE_UP_S, 4.0 * self.window * pi.frame_airtime_s(self.rung, pi.DATA_HEADER + 2 * pi.PIECE))

    # ----- il processo -----
    def proc(self):
        yield from self.phase_hello()
        yield from self.negotiate()
        yield from self.phase_transfer()
        return self.result

    def phase_hello(self):
        wait = 5.0
        t0 = self.t
        while True:
            r = yield ("exchange", self.hello_frame(), T["HELLO"], 1)
            if r is not None:
                self.caps = r
                self.peer_chip = r["chip"]
                if "rssi" in r:
                    self.hello_metrics = (r["rssi"], r["snr"])
                self.k_now = self.k_for(pi.RENDEZVOUS)
                self.t_hello = self.t - t0
                return
            rnd = yield ("rand",)
            yield ("wait", wait * (0.8 + 0.4 * rnd))
            wait = min(60.0, wait * 2)
            if self.t - t0 > 600.0:
                raise Failure("nessun incontro (HELLO senza risposta)")

    def probe(self):
        """Raffica di PROBE al gradino attuale; ritorna (ricevuti, attesi, rssi, snr) dal report, o None."""
        n = self.probes_r10 if self.rung <= pi.RENDEZVOUS else 4
        rf = yield ("probe", [enc_probe(self.sess, self.rung, i, n) for i in range(n)])
        if rf is None:
            return None
        return rf["received"], rf["expected"], rf["rssi"], rf["snr"]

    def switch(self, target):
        """MODE-SET (3 volte) al gradino attuale e MODE-ACK; poi entrambe passano al nuovo gradino. True se il mittente ha sentito l'ACK."""
        k = self.k_for(target)
        for rep in range(3):
            ack = yield ("modeset", enc_mode_set(self.sess, target, k, rep), target)
            if ack is not None:
                yield ("setrung", target)
                self.k_now = k
                yield ("wait", GUARD_S)
                return True
            yield ("wait", pi.frame_airtime_s(self.rung, 8) + 2 * GUARD_S)
        return False

    def resync(self):
        """Dopo un cambio non confermato o un silenzio le due stazioni possono stare su gradini diversi: il mittente aspetta di essere in ricerca
        come il ricevitore, poi manda HELLO al gradino del calendario in cui si trova finche' il ricevitore risponde."""
        yield ("note", f"disallineamento o silenzio (S=R{self.rung}): ricerca")
        t0 = self.t
        yield ("holdclear",)
        if self.ricerca != "calendario":
            yield ("legacy",)
            self.k_now = self.k_for(pi.RENDEZVOUS)
            return
        while not self.lost:                      # il mittente entra in ricerca con lo stesso timer del ricevitore
            yield ("wait", 1.0)
        while True:
            r = yield ("exchange", self.hello_frame(), T["HELLO"], 1)
            if r is not None:
                self.k_now = self.k_for(self.rung)
                self.just_reconnected = True     # lo scambio di HELLO ha gia' provato il collegamento: niente nuova raffica di PROBE
                yield ("note", f"ritrovati a R{self.rung} dopo {self.t - t0:.0f} s")
                return
            rnd = yield ("rand",)
            yield ("wait", pi.frame_airtime_s(self.rung, 25) * (1.0 + rnd))
            if self.t - t0 > max(GIVE_UP_S, 3.0 * sum(scan_dwell_s(r) for r in self.scan_order())):   # tre giri del calendario
                raise Failure("collegamento perso (la ricerca non ha ritrovato la stazione)")

    @staticmethod
    def predicted_best(prx_est, allowed, margin):
        """Il gradino piu' veloce con il margine richiesto; se nessuno lo ha, con 3 dB; se neppure, il piu' lento ammesso."""
        for m in (margin, 3.0):
            for r in allowed:
                if prx_est - pi.sensitivity_dbm(r) >= m:
                    return r
        return allowed[-1]

    def negotiate(self):
        """Dal gradino attuale cerca il gradino migliore: misura (PROBE), propone (MODE-SET), verifica (PROBE) e scende se non regge."""
        allowed = self.allowed()
        if self.just_reconnected:
            self.just_reconnected = False
            return
        fails = 0
        for attempt in range(8):
            if self.hello_metrics is not None:           # la misura e' gia' arrivata con la risposta all'HELLO: niente raffica
                rs, sn = self.hello_metrics
                self.hello_metrics = None
                m = (1, 1, rs, sn)
            else:
                m = yield from self.probe()
            if m is None:
                fails += 1
                if fails >= 2:
                    yield from self.resync()
                    fails = 0
                else:
                    yield ("wait", 5.0)
                continue
            rec, exp, rssi, snr = m
            self.rssi_est = rssi
            target = self.predicted_best(rssi, allowed, MARGIN_UP_DB)
            if target == self.rung:
                return
            if target > self.rung and rec >= PROBE_OK * exp:
                return       # il gradino attuale ha appena dimostrato di funzionare (>= 90 % delle prove): non si scende senza motivo
            ok = yield from self.switch(target)
            if not ok:
                yield from self.resync()
                continue
            # verifica al nuovo gradino, scendendo se serve
            while True:
                m2 = yield from self.probe()
                if m2 is not None and m2[0] >= PROBE_OK * m2[1]:
                    return
                slower = [r for r in allowed if r > self.rung]
                if not slower:
                    return
                ok2 = yield from self.switch(slower[0])
                if not ok2:
                    yield from self.resync()
                    break
        raise Failure("negoziazione del gradino non riuscita")

    def target_layers(self, acked_prefix_pieces):
        """Quanti livelli stanno nel budget di tempo, con il gradino attuale: il primo e' obbligatorio. Ritorna l'indice dell'ultimo livello."""
        elapsed = self.t - self.t_transfer0
        best = 0
        for i, e in enumerate(self.layer_ends):
            remaining = max(0, e - acked_prefix_pieces) * pi.PIECE
            est = pi.estimate_seconds(remaining, self.rung, self.chip) if remaining else 0.0
            if elapsed + est <= self.budget:
                best = i
        return best

    def step_down(self):
        slower = [r for r in self.allowed() if r > self.rung]
        if not slower:
            return True   # gia' al piu' lento ammesso
        ok = yield from self.switch(slower[0])
        return ok

    def phase_transfer(self):
        crc_obj = zlib.crc32(self.obj) & 0xFFFFFFFF
        offer = enc_offer(self.sess, self.call, OBJ_BLOCK, len(self.obj), pi.PIECE, self.npieces, 0, 0, self.layer_ends, crc_obj)
        acc = None
        for attempt in range(4):
            acc = yield ("exchange", offer, T["ACCEPT"], 2)
            if acc is not None:
                break
            yield from self.resync()
            yield from self.negotiate()
        if acc is None:
            raise Failure("OFFER senza ACCEPT")
        self.t_transfer0 = self.t
        # il primo livello deve entrare nel budget al gradino migliore che la misura lascia sperare (margine 3 dB): una sola misura e' rumorosa,
        # e dopo le prime finestre il mittente puo' ancora salire di gradino
        rid_best = min(self.rung, self.predicted_best(self.rssi_est, self.allowed(), 3.0)) if self.rssi_est is not None else self.rung
        est0 = pi.estimate_seconds(self.layer_ends[0] * pi.PIECE, rid_best, self.chip)
        if est0 > self.budget:
            yield ("burst", [enc_abort(self.sess, 1)])
            raise Failure(f"il primo livello non entra nel budget (stima {pi.fmt_time(est0)} contro {pi.fmt_time(self.budget)})")
        acked = [False] * self.npieces
        frontier = 0
        good_windows = 0
        up_block = 0
        last_progress = self.t
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
            frames, run = [], []
            for p in todo:
                if run and (p != run[-1] + 1 or len(run) >= k):
                    frames.append(run)
                    run = []
                run.append(p)
            if run:
                frames.append(run)
            frames = frames[:self.window]
            wire = []
            for fi, run in enumerate(frames):
                payload = self.obj[run[0] * pi.PIECE:(run[-1] + 1) * pi.PIECE]
                fl = (F_LAST_WINDOW if fi == len(frames) - 1 else 0) | (F_RETX if run[0] in retx_set else 0)
                if run[-1] + 1 in self.layer_ends:
                    fl |= F_LAYER_END
                if run[-1] + 1 == self.npieces:
                    fl |= F_LAST_OBJECT
                wire.append(enc_data(self.sess, run[0], payload, fl))
                frontier = max(frontier, run[-1] + 1)
            yield ("burst", wire)
            # il ricevitore manda lo STATUS dopo l'ultimo frame, o (a timer) se ne ha sentito qualcuno
            st = None
            for attempt in range(STATUS_RETRIES):
                st = yield ("status", len(frames), k)
                if st is not None:
                    break
                # STATUS perso o nessun frame sentito: il mittente ripete l'ultimo frame con il flag di ultima finestra
                yield ("wait", pi.frame_airtime_s(self.rung, 20) + GUARD_S)
                last = frames[-1]
                payload = self.obj[last[0] * pi.PIECE:(last[-1] + 1) * pi.PIECE]
                yield ("burst", [enc_data(self.sess, last[0], payload, F_LAST_WINDOW | F_RETX)])
            if st is None:
                yield ("note", "nessun STATUS: scendo di un gradino")
                ok = yield from self.step_down()
                if not ok:
                    yield from self.resync()
                    yield from self.negotiate()
                good_windows = 0
                if self.t - last_progress > self.give_up():
                    raise Failure("collegamento perso (nessun progresso)")
                continue
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
                yield ("note", f"perdita {loss * 100:.0f} % > {LOSS_DOWN * 100:.0f} %: scendo")
                ok = yield from self.step_down()
                if not ok:
                    yield from self.resync()
                    yield from self.negotiate()
            elif loss < LOSS_UP:
                good_windows += 1
                if good_windows >= UP_WINDOWS and up_block <= 0:
                    good_windows = 0
                    faster = [r for r in self.allowed() if r < self.rung]
                    if faster:
                        cand = faster[-1]
                        if st["rssi"] - pi.sensitivity_dbm(cand) >= MARGIN_UP_DB:
                            old = self.rung
                            yield ("note", f"{UP_WINDOWS} finestre buone: provo R{cand}")
                            ok = yield from self.switch(cand)
                            if ok:
                                m = yield from self.probe()
                                if m is None or m[0] < PROBE_OK * m[1]:
                                    yield ("note", "verifica fallita: torno indietro")
                                    back = yield from self.switch(old)
                                    if not back:
                                        yield from self.resync()
                                        yield from self.negotiate()
                                    up_block = 5
                            else:
                                yield from self.resync()
                                yield from self.negotiate()
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
        done = enc_done(self.sess, self.call, li, nbytes, zlib.crc32(self.obj[:nbytes]) & 0xFFFFFFFF)
        rf = yield ("exchange", done, T["STATUS"], 4)
        if rf is None:
            # la consegna e' avvenuta se il ricevitore lo ha sentito: verifica dal lato del ricevitore (solo simulatore)
            delivered = yield ("oracle",)
            if not delivered:
                raise Failure("DONE non confermato")
        self.result = (li, nbytes)
