"""Prova di collegamento con moduli radio UART a trasmissione trasparente (per esempio l'Ebyte E28-2G4T27SX a 2,4 GHz).
La prova manda frame numerati incapsulati (tools/uart_frame.py) da un modulo all'altro e conta ricevuti, scartati, tempi e velocita'. Non usa nessuna
funzione particolare del modulo: vale per qualunque radio che porti byte da una seriale all'altra. Provata sul PC con moduli finti (tests/app/test_uartlink.py),
NON con moduli veri."""
import queue
import random
import struct
import threading
import time

from . import core  # noqa: F401  (porta tools/ in sys.path)
import ebyte_e28 as eb  # noqa: E402
import uart_frame as uf  # noqa: E402

MAGIC = b"VL"
HEADER = struct.Struct(">2sHHI")      # magic, numero, totale, millisecondi di invio (32 bit)
MIN_SIZE = HEADER.size


def make_payload(seq, total, size, t_ms):
    """Payload di prova di `size` byte: intestazione e riempimento che si puo' ricalcolare (per riconoscere i byte rovinati)."""
    size = max(size, MIN_SIZE)
    return HEADER.pack(MAGIC, seq, total, t_ms & 0xFFFFFFFF) + bytes((seq * 31 + i * 7) & 0xFF for i in range(size - HEADER.size))


def check_payload(p):
    """(seq, totale, t_ms) se il payload e' valido, altrimenti None."""
    if len(p) < MIN_SIZE:
        return None
    magic, seq, total, t = HEADER.unpack(p[:HEADER.size])
    if magic != MAGIC or p[HEADER.size:] != bytes((seq * 31 + i * 7) & 0xFF for i in range(len(p) - HEADER.size)):
        return None
    return seq, total, t


class SerialStream:
    """Flusso su una porta seriale vera (pyserial)."""

    def __init__(self, port, baud=9600, parity="N"):
        import serial
        self.s = serial.Serial(port, baud, bytesize=8, parity=parity, stopbits=1, timeout=0.05, write_timeout=5)

    def write(self, b):
        self.s.write(b)
        self.s.flush()

    def read(self, n=256):
        return self.s.read(n)

    def close(self):
        try:
            self.s.close()
        except Exception:  # noqa
            pass


class FakeModulePair:
    """Due estremi di un collegamento radio finto: i byte scritti da una parte arrivano all'altra a pacchetti d'aria di al massimo `air_max` byte, con
    ritardo, velocita' seriale, perdita di pacchetti e byte rovinati. Serve alle prove sul PC."""

    def __init__(self, loss=0.0, corrupt=0.0, delay_s=0.002, air_max=eb.MAX_PACKET, bps=0.0, seed=1):
        self.loss, self.corrupt, self.delay, self.air_max, self.bps = loss, corrupt, delay_s, air_max, bps
        self.rng = random.Random(seed)
        self.a, self.b = self._End(self), self._End(self)
        self.a.peer, self.b.peer = self.b, self.a

    class _End:
        def __init__(self, link):
            self.link = link
            self.peer = None
            self.rx = queue.Queue()
            self.closed = False

        def write(self, data):
            lk = self.link
            for i in range(0, len(data), lk.air_max):
                pkt = bytearray(data[i:i + lk.air_max])
                if lk.bps:
                    time.sleep(len(pkt) * 10.0 / lk.bps)          # 10 bit per byte sulla seriale
                if lk.rng.random() < lk.loss:
                    continue
                if pkt and lk.rng.random() < lk.corrupt:
                    pkt[lk.rng.randrange(len(pkt))] ^= 0x5A
                self.peer.rx.put((time.monotonic() + lk.delay, bytes(pkt)))      # coda in ordine: la radio non scambia i pacchetti

        def read(self, n=256):
            try:
                ready, pkt = self.rx.get(timeout=0.05)
            except queue.Empty:
                return b""
            wait = ready - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            return pkt

        def close(self):
            self.closed = True


class FakeConfigModule:
    """Modulo finto in modo configurazione (M2 M1 M0 = 1 1 1, 9600 8N1): risponde a C1 C1 C1 e accetta C0/C2 + 5 byte. Per le prove sul PC."""

    def __init__(self):
        self.cfg = eb.build_config()
        self._buf = bytearray()
        self._out = bytearray()

    def write(self, data):
        self._buf += data
        while True:
            if self._buf.startswith(eb.CMD_READ):
                self._out += self.cfg
                del self._buf[:3]
            elif self._buf[:1] in (b"\xc0", b"\xc2") and len(self._buf) >= 6:
                eb.parse_config(bytes(self._buf[:6]))
                self.cfg = bytes(self._buf[:6])
                del self._buf[:6]
            else:
                break

    def read(self, n=256):
        time.sleep(0.01)
        out, self._out = bytes(self._out[:n]), self._out[n:]
        return out

    def close(self):
        pass


def read_config(stream, timeout=2.0):
    """Manda C1 C1 C1 (modulo in modo configurazione) e legge i 6 byte di risposta. Ritorna il dizionario dei parametri."""
    stream.write(eb.CMD_READ)
    got = b""
    t0 = time.monotonic()
    while len(got) < 6 and time.monotonic() - t0 < timeout:
        got += stream.read(6 - len(got))
    return eb.parse_config(got)


def write_config(stream, verify=True, **params):
    """Scrive i parametri (C0, salvati) e, con verify, li rilegge. Ritorna i parametri letti (o quelli scritti)."""
    cmd = eb.build_config(**params)
    stream.write(cmd)
    time.sleep(0.2)
    return read_config(stream) if verify else eb.parse_config(cmd)


def open_config_window(stream):
    """In trasmissione trasparente: E2 E2 E2 apre per 10 secondi la finestra in cui un comando C0 cambia i parametri; dopo 10 secondi il modulo lavora con i nuovi.
    (Dal manuale, pag. 11: non provato con un modulo vero.)"""
    stream.write(eb.WINDOW_E2)
    time.sleep(0.1)


def run_tx(stream, count, size, interval_s=0.0, stop=None, t0=None, now=time.monotonic):
    """Manda `count` frame di `size` byte. Ritorna (inviati, secondi)."""
    t_start = now()
    sent = 0
    for seq in range(count):
        if stop is not None and stop.is_set():
            break
        t_ms = int((now() - (t0 if t0 is not None else 0.0)) * 1000)
        stream.write(uf.encode_frame(make_payload(seq, count, size, t_ms)))
        sent += 1
        if interval_s > 0 and seq < count - 1:
            time.sleep(interval_s)
    return sent, now() - t_start


def run_rx(stream, count, window_s, stop=None, idle_s=None, t0=None, now=time.monotonic):
    """Ascolta fino a `window_s` secondi (o fino a `count` frame validi, o fino a `idle_s` secondi senza dati dopo il primo frame)."""
    dec = uf.Decoder()
    seen = {}
    bad_content = 0
    first = last = None
    lat = []
    t_start = now()
    last_data = None
    while now() - t_start < window_s:
        if stop is not None and stop.is_set():
            break
        chunk = stream.read(256)
        if chunk:
            last_data = now()
        for p in dec.feed(chunk):
            r = check_payload(p)
            if r is None:
                bad_content += 1
                continue
            seq, total, t_ms = r
            if seq not in seen:
                seen[seq] = len(p)
                tn = now()
                first = first if first is not None else tn
                last = tn
                if t0 is not None:
                    lat.append(tn * 1000 - (t0 * 1000 + t_ms))
        if len(seen) >= count:
            break
        if idle_s is not None and last_data is not None and now() - last_data > idle_s:
            break
    return {"ok": len(seen), "bad_crc": dec.bad, "bad_content": bad_content, "bytes_ok": sum(seen.values()), "first": first, "last": last, "lat_ms": lat,
            "seqs": sorted(seen)}


def run_link_test(tx_stream, rx_stream, count, size, interval_s=0.0, wait_s=5.0):
    """Prova completa con i due moduli collegati a questo computer. Ritorna un dizionario di risultati."""
    t0 = time.monotonic()
    stop = threading.Event()
    res = {}
    window = count * max(interval_s, 0.001) + wait_s + count * 0.01
    th = threading.Thread(target=lambda: res.update(rx=run_rx(rx_stream, count, window, stop, idle_s=wait_s, t0=t0)), daemon=True)
    th.start()
    time.sleep(0.2)
    t_tx = time.monotonic()
    sent, dur = run_tx(tx_stream, count, size, interval_s, t0=t0)
    th.join(window + 1.0)
    rx = res.get("rx") or {"ok": 0, "bad_crc": 0, "bad_content": 0, "bytes_ok": 0, "first": None, "last": None, "lat_ms": [], "seqs": []}
    span = (rx["last"] - t_tx) if rx["last"] else None
    wire = len(uf.encode_frame(make_payload(0, count, size, 0)))
    return {"sent": sent, "ok": rx["ok"], "bad_crc": rx["bad_crc"], "bad_content": rx["bad_content"], "loss_pct": 100.0 * (sent - rx["ok"]) / sent if sent else 0.0,
            "size": size, "wire_bytes": wire, "tx_s": dur, "span_s": span,
            "bps": (rx["bytes_ok"] * 8.0 / span) if span else 0.0,
            "lat_mean_ms": sum(rx["lat_ms"]) / len(rx["lat_ms"]) if rx["lat_ms"] else None, "lat_max_ms": max(rx["lat_ms"]) if rx["lat_ms"] else None}


def summary_line(r):
    lat = "" if r["lat_mean_ms"] is None else f" lat_medio={r['lat_mean_ms']:.0f}ms lat_max={r['lat_max_ms']:.0f}ms"
    return (f"UARTSUM inviati={r['sent']} ricevuti={r['ok']} crc_scartati={r['bad_crc']} perdita={r['loss_pct']:.1f}% "
            f"velocita={r['bps'] / 1000:.1f}kbit/s{lat}")
