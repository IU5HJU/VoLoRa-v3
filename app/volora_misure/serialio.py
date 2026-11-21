"""Schede: porta seriale vera (pyserial) e scheda finta per provare l'applicazione senza hardware."""
import math
import queue
import random
import threading
import time

from . import core


class BoardBase:
    """Interfaccia comune: righe in arrivo in `inbox` (per lo schermo) e attese di una riga con un prefisso (`expect`)."""

    def __init__(self, name):
        self.name = name
        self.inbox = queue.Queue()       # righe da mostrare: (direzione, testo) con direzione 'rx' | 'tx' | 'sys'
        self._watchers = []
        self._lock = threading.Lock()
        self.chip = "SX1278"
        self.connected = False

    def _deliver(self, line):
        self.inbox.put(("rx", line))
        with self._lock:
            for w in list(self._watchers):
                w.put(line)

    def send(self, line):
        self.inbox.put(("tx", line))
        self._write(line)

    def expect(self, prefix, timeout):
        """Aspetta una riga che inizia con prefix (o ERR). Ritorna il testo o None allo scadere. Va chiamata PRIMA di mandare il comando."""
        q = queue.Queue()
        with self._lock:
            self._watchers.append(q)
        return _Waiter(self, q, prefix, timeout)

    def _drop(self, q):
        with self._lock:
            if q in self._watchers:
                self._watchers.remove(q)

    def close(self):
        pass


class _Waiter:
    def __init__(self, board, q, prefix, timeout):
        self.board, self.q, self.prefix, self.timeout = board, q, prefix, timeout

    def wait(self):
        end = time.time() + self.timeout
        try:
            while time.time() < end:
                try:
                    line = self.q.get(timeout=min(0.2, max(0.01, end - time.time())))
                except queue.Empty:
                    continue
                if line.startswith(self.prefix) or line.startswith("ERR"):
                    return line
            return None
        finally:
            self.board._drop(self.q)

    def cancel(self):
        self.board._drop(self.q)


class SerialBoard(BoardBase):
    def __init__(self, name, port, baud=921600):
        super().__init__(name)
        import serial  # noqa: pyserial
        self.ser = serial.Serial(port, baud, timeout=0.1)
        self.connected = True
        self._stop = False
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _read(self):
        buf = b""
        while not self._stop:
            try:
                data = self.ser.read(256)
            except Exception as e:  # noqa
                self.inbox.put(("sys", f"porta chiusa: {e}"))
                self.connected = False
                return
            if not data:
                continue
            buf += data
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                text = raw.decode(errors="replace").strip()
                if text:
                    self._deliver(text)

    def _write(self, line):
        self.ser.write((line + "\n").encode())

    def close(self):
        self._stop = True
        self.connected = False
        try:
            self.ser.close()
        except Exception:  # noqa
            pass


# ---------- Schede finte ----------
class FakeLink:
    """Collegamento finto fra due schede finte: la probabilita' di ricezione segue una curva attorno alla sensibilita' stimata del modo."""

    def __init__(self, att_db=0.0, seed=1):
        self.att_db = att_db
        self.rng = random.Random(seed)
        self.boards = []
        self.tx_done = False

    def other(self, board):
        for b in self.boards:
            if b is not board:
                return b
        return None


class FakeBoard(BoardBase):
    """Risponde come il firmware di misura (docs/firmware-misura.md): INFO, CALL, MODE, FREQ, POWER, PAYLOAD, TX, RX, CW, STOP."""

    def __init__(self, name, link, chip="SX1278", speed=1.0):
        super().__init__(name)
        self.link = link
        self.chip = chip
        self.connected = True
        self.speed = speed          # 1 = tempo reale, valori grandi = prove veloci
        self.call = ""
        self.mode_code = "L4"
        self.power = 2
        self.payload = 64
        self.freq = 433.475
        self._cmds = queue.Queue()
        self._rxing = False
        self._rx_pkts = []
        self._stop_flag = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._emit(f"misura 0.1.0 {chip}")

    def _emit(self, line):
        self._deliver(line)

    def _write(self, line):
        if line.strip().upper() in ("STOP", "X"):
            self._stop_flag = True
        self._cmds.put(line)

    def close(self):
        self.connected = False
        self._stop_flag = True
        self._cmds.put(None)

    def _run(self):
        while True:
            line = self._cmds.get()
            if line is None:
                return
            try:
                self._handle(line)
            except Exception as e:  # noqa
                self._emit(f"ERR interno {e}")

    def _handle(self, line):
        t = line.split()
        if not t:
            return
        c = t[0].upper()
        if c == "INFO":
            self._emit(f"INFO misura 0.1.0 {self.chip} sync=0x5D tcxo=1.6")
        elif c in ("SHOW", "HELP"):
            self._emit(f"MODE {self.mode_code} | freq {self.freq} power {self.power} payload {self.payload} call {self.call or '-'}")
        elif c == "CALL" and len(t) == 2:
            self.call = t[1].upper()
            self._emit(f"OK call {self.call}")
        elif c == "MODE":
            code = _code_from_mode(t)
            if code is None:
                self._emit("ERR MODE non valido")
            else:
                self.mode_code = code
                self._emit(f"MODE {' '.join(t[1:])} | ready 1")
        elif c == "FREQ":
            self.freq = float(t[1]); self._emit(f"MODE freq {self.freq}")
        elif c == "POWER":
            self.power = int(t[1]); self._emit(f"MODE power {self.power}")
        elif c == "PAYLOAD":
            self.payload = int(t[1]); self._emit(f"MODE payload {self.payload}")
        elif c == "TX" and len(t) >= 3:
            self._tx(int(t[1]), int(t[2]), int(t[3]) if len(t) > 3 else 1)
        elif c == "RX" and len(t) == 2:
            self._rx(int(t[1]))
        elif c == "CW":
            self._emit(f"CW start {t[1]} s"); time.sleep(0.2 / self.speed); self._emit("CW fine pacchetti=3")
        elif c in ("STOP", "X"):
            pass
        else:
            self._emit("ERR comando non riconosciuto (HELP)")

    def _tx(self, n, interval, start):
        other = self.link.other(self)
        sens = core.sens_estimate(self.mode_code)
        prx = self.power - self.link.att_db
        pok = 1.0 / (1.0 + math.exp(-(prx - sens) / 1.0))
        self._stop_flag = False
        ok = 0
        for i in range(n):
            if self._stop_flag:
                self._emit("STOP"); break
            seq = start + i
            self._emit(f"TX seq={seq} len={self.payload} toa_us=1000 calc_us=1000 st=0")
            if other is not None and self.link.rng.random() < pok:
                other._rx_pkts.append((seq, prx))
            ok += 1
            time.sleep(max(0.0, interval / 1000.0 / self.speed))
        self._emit(f"TXSUM sent={ok} toa_mean_us=1000 calc_us=1000")
        self.link.tx_done = True

    def _rx(self, seconds):
        self._rx_pkts = []
        self._stop_flag = False
        end = time.time() + max(3.0, seconds / self.speed)
        seen = []
        snr_sum = rssi_sum = 0.0
        while time.time() < end and not self._stop_flag:
            while self._rx_pkts:
                seq, prx = self._rx_pkts.pop(0)
                seen.append(seq)
                rssi_sum += prx; snr_sum += prx - (-174 + 10 * math.log10(125000) + 6)
                self._emit(f"RX seq={seq} len={self.payload} rssi={prx:.1f} snr={prx + 174 - 10 * math.log10(125000) - 6:.1f} fei=0 rs=0 status=0 bit_err=0")
            time.sleep(0.02)
            # chiusura anticipata quando il trasmettitore ha finito (la scheda finta lo sa)
            if getattr(self.link, "tx_done", False) and not self._rx_pkts:
                break
        n = len(seen)
        lost = (max(seen) - min(seen) + 1 - len(set(seen))) if seen else 0
        self._emit("RXSUM ok=%d bad=0 lost=%d dup=0 bit_err=0 first=%d last=%d rssi=%.1f snr=%.1f fei_hz=0" %
                   (n, lost, min(seen) if seen else 0, max(seen) if seen else 0, rssi_sum / n if n else float("nan"), snr_sum / n if n else float("nan")))
        self.link.tx_done = False


def _code_from_mode(t):
    """Codice del modo (L1.., F1..) da un comando MODE gia' diviso in parole; None se non e' uno dei modi dello studio."""
    from . import core as c
    try:
        if t[1].upper() == "LORA":
            bw, sf = float(t[2]), int(t[3])
            for i, (b, s) in enumerate(c.sm.LORA, 1):
                if abs(b - bw) < 0.01 and s == sf:
                    return f"L{i}"
        elif t[1].upper() == "FSK":
            br, dev = float(t[2]), float(t[3])
            for i, (b, d) in enumerate(c.sm.FSK, 1):
                if abs(b - br) < 0.01 and abs(d - dev) < 0.01:
                    return f"F{i}"
    except (IndexError, ValueError):
        pass
    return None


def fake_pair(speed=50.0, chip_a="SX1278", chip_b="SX1278"):
    link = FakeLink()
    a, b = FakeBoard("A", link, chip_a, speed), FakeBoard("B", link, chip_b, speed)
    link.boards = [a, b]
    return link, a, b
