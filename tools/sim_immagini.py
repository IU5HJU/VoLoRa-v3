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

# i frame e il protocollo sono in img_frames.py e img_proto.py (qui restano canale, simulatore e riga di comando)
from img_frames import *  # noqa: F401,F403,E402
from img_frames import _call, _hdr, _s8  # noqa: F401,E402


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
# Il protocollo (collegamento, ricevitore, mittente) e' in img_proto.py e non conosce ne' il canale ne' l'orologio. Qui c'e' il MEZZO: canale con perdite, tempo
# simulato e i due gradini; il mittente chiede (azioni) e il mezzo esegue.
from img_proto import (GIVE_UP_S, GUARD_S, LOSS_DOWN, LOSS_UP, MARGIN_UP_DB, PROBE_COUNT, PROBE_OK, SCAN_ORDER, STATUS_RETRIES, UP_WINDOWS, WINDOW_FRAMES,  # noqa: F401,E402
                       Failure, Link, Receiver, Sender, fallback_s, scan_dwell_s, scan_order_for, scan_rung)


class Node(Link):
    """Un'estremita': lo stato del collegamento piu' il chip (per la maschera dei gradini)."""

    def __init__(self, name, chip, tcxo=False):
        super().__init__(name)
        self.chip, self.tcxo = chip, tcxo

    def mask(self):
        """Gradini annunciati nell'HELLO: quelli che il chip realizza (R0 solo SX1278, R3 d'intesa con il chip dell'altro) e R12-R14 solo con TCXO."""
        return lim.rung_mask(self.chip, self.tcxo)


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


# -------------------------------------------------------------------------------------------------------------- simulatore (il mezzo)
class Simulator:
    def __init__(self, obj_size=20000, layers=(0.2, 0.5, 1.0), channel=None, chip_a="SX1278", chip_b="SX1278", budget_s=600.0, seed=1,
                 call_a="IU5HJU", call_b="IK5XYZ", trace=False, window=WINDOW_FRAMES, max_time_s=4 * 3600.0, ricerca="calendario",
                 incontro="hello", probes_r10=PROBE_COUNT, tcxo_a=False, tcxo_b=False, data=None, layer_pieces=None):
        self.ricerca = ricerca
        self.incontro = incontro            # "hello": la risposta all'HELLO porta la misura; "probe": raffica di PROBE a R10 (vecchio)
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
        self.sender = Sender(self.sess, call_a, chip_a, tcxo_a, self.obj, self.layer_ends, budget_s, window, ricerca, probes_r10)
        self.receiver = Receiver(call_b, chip_b, tcxo_b, window, incontro)
        self.drop_hook = None     # funzione(frame decodificato) -> True per far perdere quel frame (prove)
        self._last_rssi = self._last_snr = 0.0

    # ----- utilita' -----
    def tr(self, who, msg):
        line = f"[{self.t:8.2f}s] {who}: {msg}"
        self.log.append(line)
        if self.trace_on:
            print(line)

    def scan_order(self):
        """Calendario della ricerca ristretto ai gradini che entrambe le stazioni hanno annunciato (dopo l'incontro la maschera comune e' nota a tutte e due)."""
        return scan_order_for(self.S.chip, self.S.mask(), self.R.chip, self.R.mask())

    def _events(self, node, events):
        for e in events:
            if e[0] == "fallback":
                self.tr(node.name, f"silenzio di {e[1]:.0f} s a R{e[2]}: ricerca")
                self.res.fallbacks += 1
            else:
                self.res.rung_changes.append((round(self.t, 1), node.name, e[1], e[2]))

    def tick(self):
        """Il tempo e' passato: ogni stazione controlla il proprio silenzio e il proprio calendario."""
        self._events(self.S, self.S.tick(self.t, self.sender_scan_order, self.ricerca))
        self._events(self.R, self.R.tick(self.t, self.receiver.scan_order, self.ricerca))

    def sender_scan_order(self):
        return self.sender.scan_order() if self.sender.caps is not None else (pi.RENDEZVOUS,)

    def set_rung(self, node, rid):
        self._events(node, node.set_rung(rid))

    def advance(self, dt):
        self.t += dt
        self.tick()
        if self.t > self.max_time:
            raise Failure("tempo massimo di simulazione superato")

    def guard(self):
        self.advance(GUARD_S)

    def air(self, tx, rx, frame):
        """tx trasmette `frame` al suo gradino: ritorna il frame decodificato se rx lo sente, altrimenti None. Avanza il tempo."""
        rid = tx.rung
        a = pi.frame_airtime_s(rid, len(frame)) if len(frame) else 0.0
        self.res.rung_time[rid] = self.res.rung_time.get(rid, 0.0) + a
        d = decode(frame)
        name = d["nome"] if d else "?"
        self.res.frames[name] = self.res.frames.get(name, 0) + 1
        self.advance(a)
        tx.on_tx(self.t)
        heard = False
        p = None
        if rx.rung == rid:
            heard, p = self.ch.success(self.t, rid, len(frame))
            if heard and self.drop_hook is not None and d is not None and self.drop_hook(d):
                heard = False
        if heard:
            rx.on_heard(self.t, d["tipo"] if d is not None else None, bool(d and d.get("reply")))
            self._last_rssi, self._last_snr = p, p - noise_floor_dbm(rid)
        self.tr(tx.name, f"{name} {len(frame)}B a R{rid} ({a * 1000:.0f} ms) -> {'sentito' if heard else 'perso'}")
        return d if heard else None

    def recv(self, f):
        """Il ricevitore reagisce a un frame sentito: ritorna la risposta (bytes) o None; applica la tenuta del gradino. `rung_after` lo applica chi trasmette la risposta."""
        rep = self.receiver.on_frame(f, self._last_rssi, self._last_snr, self.t, self.R.rung, self.R.lost_since is not None)
        if rep.hold_until is not None:
            self.R.hold_until = rep.hold_until
        self._rung_after = rep.rung_after
        return rep.frame

    # ----- le azioni del mittente -----
    def exchange(self, frame, expect, tries=1):
        """Il mittente manda `frame`; il ricevitore risponde (se sente); ritorna la risposta decodificata (tipo atteso) o None."""
        for _ in range(tries):
            f = self.air(self.S, self.R, frame)
            reply = None
            if f is not None:
                reply = self.recv(f)
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

    def do_probe(self, frames):
        for fr in frames:
            r = self.air(self.S, self.R, fr)
            if r is not None:
                self.recv(r)
        # il ricevitore manda il PROBE-REPORT a timer, dopo la raffica, se ne ha sentito almeno uno (come lo STATUS dopo una finestra)
        rep = self.receiver.probe_report()
        if rep is None:
            self.advance(2 * GUARD_S)
            return None
        self.guard()
        rf = self.air(self.R, self.S, rep)
        self.guard()
        return rf

    def do_modeset(self, frame, target):
        f = self.air(self.S, self.R, frame)
        if f is None:
            return None
        ack = self.recv(f)
        after = self._rung_after
        self.guard()
        # il ricevitore passa al nuovo gradino alla fine del MODE-ACK, sia che il mittente lo senta o no
        rack = self.air(self.R, self.S, ack)
        self.set_rung(self.R, after)
        return rack

    def do_burst(self, frames):
        for fr in frames:
            f = self.air(self.S, self.R, fr)
            d = decode(fr)
            if d is not None and d["tipo"] == T["DATA"]:
                self.res.data_frames += 1
                if d["flags"] & F_RETX:
                    self.res.retx_frames += 1
            if f is not None:
                self.recv(f)

    def do_status(self, sent_blocks, k):
        self.guard()
        if self.receiver.window_heard > 0:
            stf = self.receiver.status(sent_blocks, k)
            rf = self.air(self.R, self.S, stf)
            self.guard()
            if rf is not None:
                return rf
        return None

    def do_legacy(self):
        """Vecchia ricerca (solo per confronto): si aspetta il fallback e tutte e due tornano a R10."""
        wait = max(fallback_s(self.S.rung), fallback_s(self.R.rung)) + 1.0
        self.advance(wait)
        for n in (self.S, self.R):
            if n.rung != pi.RENDEZVOUS:
                self.set_rung(n, pi.RENDEZVOUS)

    def perform(self, a):
        k = a[0]
        if k == "exchange":
            return self.exchange(a[1], a[2], a[3])
        if k == "probe":
            return self.do_probe(a[1])
        if k == "modeset":
            return self.do_modeset(a[1], a[2])
        if k == "burst":
            return self.do_burst(a[1])
        if k == "status":
            return self.do_status(a[1], a[2])
        if k == "wait":
            return self.advance(a[1])
        if k == "rand":
            return self.rng.random()
        if k == "setrung":
            return self.set_rung(self.S, a[1])
        if k == "holdclear":
            self.S.hold = False
            return None
        if k == "legacy":
            return self.do_legacy()
        if k == "oracle":
            return self.receiver.done is not None
        if k == "note":
            return self.tr("S", a[1])
        raise ValueError(a)

    def run(self):
        snd = self.sender
        proc = snd.proc()
        ans = None
        try:
            while True:
                snd.t, snd.rung, snd.lost = self.t, self.S.rung, self.S.lost_since is not None
                try:
                    act = proc.send(ans)
                except StopIteration as e:
                    self.res.ok = True
                    li, nbytes = e.value
                    self.res.layers_delivered, self.res.bytes_delivered = li, nbytes
                    self.res.crc_ok = bool(self.receiver.done[0]) if self.receiver.done else False
                    break
                ans = self.perform(act)
        except Failure as e:
            self.res.reason = str(e)
            self.tr("--", f"FALLITO: {e}")
        self.res.t_hello = snd.t_hello
        self.res.time_s = self.t
        self.res.transfer_s = self.t - (snd.t_transfer0 if snd.t_transfer0 is not None else self.t)
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
