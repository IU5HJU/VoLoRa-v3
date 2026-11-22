"""Orologio preciso per le prove: NTP e GPS (NMEA su seriale o USB, con PPS facoltativo), scelta della sorgente migliore e partenza a un
orario concordato. Tutto provato con sorgenti finte (tests/app/test_timesync.py): NTP e GPS veri non sono stati provati."""
import collections
import datetime
import socket
import statistics
import struct
import threading
import time

NTP_DELTA = 2208988800   # secondi fra il 1900 (NTP) e il 1970 (Unix)


# ---------------------------------------------------------------------------------------------------------------- NTP
def ntp_query(server, port=123, timeout=2.0, now=time.time):
    """Una richiesta SNTP. Ritorna (scarto, ritardo) in secondi: scarto = ora vera - ora del computer."""
    pkt = b"\x1b" + 47 * b"\0"          # LI 0, versione 3, modo 3 (client)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        t1 = now()
        s.sendto(pkt, (server, port))
        data, _ = s.recvfrom(512)
        t4 = now()
    if len(data) < 48:
        raise OSError("risposta NTP troppo corta")
    if (data[0] & 0x07) != 4 and (data[0] & 0x07) != 5:
        raise OSError("la risposta non e' di un server NTP")
    rx_s, rx_f, tx_s, tx_f = struct.unpack("!4I", data[32:48])
    if tx_s == 0:
        raise OSError("server NTP non sincronizzato")
    t2 = rx_s - NTP_DELTA + rx_f / 2 ** 32
    t3 = tx_s - NTP_DELTA + tx_f / 2 ** 32
    return ((t2 - t1) + (t3 - t4)) / 2.0, (t4 - t1) - (t3 - t2)


def ntp_sync(servers, samples=4, timeout=2.0, port=123, now=time.time):
    """Interroga i server e tiene il campione con il ritardo minore (il piu' attendibile). Ritorna (scarto, incertezza, server)."""
    best = None
    errors = []
    for srv in servers:
        for _ in range(samples):
            try:
                off, delay = ntp_query(srv, port, timeout, now)
            except OSError as e:
                errors.append(f"{srv}: {e}")
                break
            if best is None or delay < best[1]:
                best = (off, delay, srv)
    if best is None:
        raise OSError("nessun server NTP raggiungibile (" + "; ".join(errors[:3]) + ")")
    return best[0], max(0.002, best[1] / 2.0), best[2]


# --------------------------------------------------------------------------------------------------------------- NMEA
def nmea_checksum_ok(line):
    line = line.strip()
    if not line.startswith("$") or "*" not in line:
        return False
    body, _, cs = line[1:].partition("*")
    c = 0
    for ch in body:
        c ^= ord(ch)
    try:
        return c == int(cs[:2], 16)
    except ValueError:
        return False


def _deg(v, hemi):
    if not v:
        return None
    dot = v.index(".")
    d = int(v[:dot - 2])
    m = float(v[dot - 2:])
    r = d + m / 60.0
    return -r if hemi in ("S", "W") else r


def _hms(s):
    if not s or len(s) < 6:
        return None
    return int(s[0:2]), int(s[2:4]), float(s[4:])


def parse_nmea(line):
    """Interpreta RMC, GGA e ZDA (con la somma di controllo giusta). Ritorna un dizionario o None.
    Campi: tipo, utc (secondi Unix, se la frase ha la data), hms (ora del giorno), lat, lon, fix, sats, hdop, alt."""
    if not nmea_checksum_ok(line):
        return None
    f = line.strip()[1:].split("*")[0].split(",")
    kind = f[0][-3:]
    try:
        if kind == "RMC" and len(f) >= 10:
            hms = _hms(f[1])
            d = {"tipo": "RMC", "fix": f[2] == "A", "lat": _deg(f[3], f[4]), "lon": _deg(f[5], f[6]), "hms": hms}
            if hms and len(f[9]) == 6:
                dt = datetime.datetime(2000 + int(f[9][4:6]), int(f[9][2:4]), int(f[9][0:2]), hms[0], hms[1], int(hms[2]), int(round((hms[2] % 1) * 1e6)),
                                       tzinfo=datetime.timezone.utc)
                d["utc"] = dt.timestamp()
            return d
        if kind == "GGA" and len(f) >= 10:
            return {"tipo": "GGA", "hms": _hms(f[1]), "lat": _deg(f[2], f[3]), "lon": _deg(f[4], f[5]), "fix": f[6] not in ("", "0"),
                    "sats": int(f[7]) if f[7] else 0, "hdop": float(f[8]) if f[8] else None, "alt": float(f[9]) if f[9] else None}
        if kind == "ZDA" and len(f) >= 5:
            hms = _hms(f[1])
            dt = datetime.datetime(int(f[4]), int(f[3]), int(f[2]), hms[0], hms[1], int(hms[2]), int(round((hms[2] % 1) * 1e6)),
                                   tzinfo=datetime.timezone.utc)
            return {"tipo": "ZDA", "hms": hms, "utc": dt.timestamp(), "fix": True}
    except (ValueError, IndexError):
        return None
    return None


# ---------------------------------------------------------------------------------------------------------------- GPS
GPS_WEEK_S = 1024 * 7 * 86400        # i ricevitori vecchi contano le settimane con 10 bit: ogni 19,6 anni la data ritorna indietro
MAX_GPS_DIFF_S = 2 * 86400           # un'ora GPS che differisce dal computer di piu' di due giorni (dopo la correzione) non e' credibile


def unroll_gps_week(utc, ref):
    """Corregge il rollover della settimana GPS: se la data del GPS e' indietro di un numero intero di 1024 settimane rispetto al computer (a meno di
    due giorni, per un computer sbagliato di poco), la riporta avanti. Ritorna (utc corretto, numero di cicli aggiunti). L'ora del giorno e il giorno
    della settimana del GPS restano quelli buoni: il computer serve solo a scegliere l'anno."""
    diff = ref - utc
    n = round(diff / GPS_WEEK_S)
    if n >= 1 and abs(diff - n * GPS_WEEK_S) <= MAX_GPS_DIFF_S:
        return utc + n * GPS_WEEK_S, n
    return utc, 0


class GpsReader:
    """Legge un GPS da una porta seriale (anche USB): posizione, satelliti, qualita' e scarto dell'orologio.
    `opener()` ritorna un oggetto con readline() -> bytes e, facoltativo, `cd` (PPS sul pin DCD). Con `pps=True` si cerca il fronte del
    PPS (sul pin DCD, se l'adattatore lo porta): lo scarto e' allora quello del fronte (pochi ms) e non quello della frase NMEA (centinaia di ms)."""

    def __init__(self, opener, baud=9600, pps=False, now=time.time):
        self.opener, self.baud, self.pps, self.now = opener, baud, pps, now
        self.lat = self.lon = self.alt = self.hdop = None
        self.fix = False
        self.sats = 0
        self.samples = collections.deque(maxlen=30)
        self.last_sample = 0.0
        self.pps_edges = collections.deque(maxlen=4)
        self.lines = 0
        self.bad = 0
        self.delay_s = 0.0         # ritardo della frase NMEA rispetto al secondo che dichiara, misurato con NTP (calibrazione)
        self.calibrated = False
        self.rollover = 0          # quante volte la data e' stata corretta (rollover della settimana GPS)
        self.rejected = 0          # ore GPS scartate perche' troppo lontane dal computer
        self.last_rejected = None
        self.error = None
        self._stop = False
        self._lock = threading.Lock()
        self._ser = None

    def start(self):
        self._ser = self.opener()
        threading.Thread(target=self._read, daemon=True).start()
        if self.pps:
            threading.Thread(target=self._poll_pps, daemon=True).start()

    def stop(self):
        self._stop = True
        try:
            if self._ser:
                self._ser.close()
        except Exception:  # noqa
            pass

    def _poll_pps(self):
        last = False
        while not self._stop:
            try:
                cd = bool(self._ser.cd)
            except Exception:  # noqa
                return
            if cd and not last:
                with self._lock:
                    self.pps_edges.append(self.now())
            last = cd
            time.sleep(0.001)

    def _read(self):
        while not self._stop:
            try:
                raw = self._ser.readline()
            except Exception as e:  # noqa
                self.error = str(e)
                return
            if not raw:
                continue
            arrival = self.now()
            self.lines += 1
            try:
                line = raw.decode("ascii", errors="replace").strip()
            except Exception:  # noqa
                continue
            self.feed(line, arrival, len(raw))

    def feed(self, line, arrival, nbytes=0):
        """Elabora una frase (usata dal lettore e dalle prove)."""
        d = parse_nmea(line)
        if d is None:
            if line.startswith("$"):
                self.bad += 1
            return
        with self._lock:
            if d.get("lat") is not None and d.get("fix"):
                self.lat, self.lon = d["lat"], d["lon"]
            if d["tipo"] == "GGA":
                self.fix = d["fix"]
                self.sats = d["sats"]
                self.hdop = d["hdop"]
                if d["alt"] is not None:
                    self.alt = d["alt"]
            if d["tipo"] == "RMC":
                self.fix = d["fix"]
            if "utc" in d and d.get("fix", True):
                utc, n = unroll_gps_week(d["utc"], arrival)
                if n:
                    self.rollover += 1
                if abs(utc - arrival) > MAX_GPS_DIFF_S:       # data impossibile (anche dopo la correzione): non si usa per l'orologio
                    self.rejected += 1
                    self.last_rejected = d["utc"]
                    return
                sec = round(utc)                      # il PPS segna l'inizio del secondo
                edge = None
                for e in reversed(self.pps_edges):
                    if 0.0 <= arrival - e <= 1.0:
                        edge = e
                        break
                if edge is not None:
                    self.samples.append((sec - edge, 0.005))
                else:
                    first_byte = arrival - nbytes * 10.0 / self.baud    # inizio della frase: nessuna correzione del ritardo del ricevitore
                    self.samples.append((utc - first_byte, None))
                self.last_sample = arrival

    def clock_offset(self):
        """(scarto, incertezza, usa_pps) o None se non ci sono campioni recenti. Scarto = ora vera - ora del computer."""
        with self._lock:
            smp = list(self.samples)
        if not smp or self.now() - self.last_sample > 15:
            return None
        pps = [s for s in smp if s[1] is not None]
        use = pps if len(pps) >= 3 else [s for s in smp if s[1] is None]
        if not use:
            return None
        vals = [s[0] for s in use]
        off = statistics.median(vals)
        spread = (max(vals) - min(vals)) / 2.0 if len(vals) > 1 else 0.0
        if use is pps:
            return off, max(0.005, spread + 0.003), True
        if self.calibrated:
            # con il ritardo tarato resta la dispersione fra le frasi e la deriva del ritardo nel tempo (non misurata): mai meno di 80 ms
            return off + self.delay_s, max(0.08, spread + 0.05), False
        return off, max(0.4, spread + 0.3), False   # il ricevitore puo' ritardare la frase di 100-500 ms: incertezza onesta

    def raw_offset(self):
        """(scarto mediano delle sole frasi NMEA senza correzione del ritardo, dispersione, quanti campioni) o None."""
        with self._lock:
            vals = [s[0] for s in self.samples if s[1] is None]
        if not vals:
            return None
        return statistics.median(vals), (max(vals) - min(vals)) / 2.0, len(vals)

    def position(self):
        with self._lock:
            return (self.lat, self.lon) if self.lat is not None and self.fix else None


MAX_DELAY_S = 3.0          # un ritardo oltre questo non e' un ritardo di ricevitore: e' un errore (per esempio i secondi intercalari)


def calibrate_gps_delay(gps, ntp_offset, ntp_uncertainty=0.0):
    """Ritardo della frase NMEA = scarto NTP - scarto grezzo del GPS. Va usato con il GPS fermo e collegato da qualche decina di secondi.
    Solleva ValueError con un messaggio comprensibile se i dati non sono credibili."""
    raw = gps.raw_offset()
    if raw is None or raw[2] < 10:
        raise ValueError("servono almeno 10 frasi con il fix: aspetta qualche secondo")
    if raw[1] > 0.3:
        raise ValueError(f"le frasi arrivano troppo irregolari (dispersione {raw[1] * 1000:.0f} ms): il collegamento Bluetooth non e' stabile")
    if ntp_uncertainty > 0.1:
        raise ValueError(f"l'NTP non e' abbastanza preciso (incertezza {ntp_uncertainty * 1000:.0f} ms)")
    delay = ntp_offset - raw[0]
    if abs(delay) > MAX_DELAY_S:
        raise ValueError(f"ritardo di {delay:.2f} s non credibile: un numero intero di secondi fa pensare ai secondi intercalari (vedi docs/gps-tempo.md)")
    return delay, raw[1], raw[2]


# -------------------------------------------------------------------------------------------------------------- Orologio
class Clock:
    """Ora UTC preciso: ora del computer piu' lo scarto della migliore sorgente (quella con la minore incertezza fra le recenti)."""
    FRESH_S = 900.0

    def __init__(self, now=time.time):
        self._now = now
        self.sources = {}     # nome -> (scarto, incertezza, quando)

    def set_source(self, name, offset, uncertainty):
        self.sources[name] = (offset, uncertainty, self._now())

    def clear_source(self, name):
        self.sources.pop(name, None)

    def best(self):
        t = self._now()
        cand = [(unc, name, off) for name, (off, unc, when) in self.sources.items() if t - when <= self.FRESH_S]
        if not cand:
            return "computer", 0.0, 1.0           # nessuna sorgente: si fida dell'orologio del computer, con 1 s di incertezza dichiarata
        unc, name, off = min(cand)
        return name, off, unc

    def now(self):
        return self._now() + self.best()[1]

    def info(self):
        name, off, unc = self.best()
        return {"sorgente": name, "scarto_s": off, "incertezza_s": unc, "utc": self.now()}

    def differences(self):
        """Differenza fra le sorgenti, per un controllo incrociato (GPS contro NTP): {(a, b): secondi}."""
        names = sorted(self.sources)
        return {(a, b): self.sources[a][0] - self.sources[b][0] for i, a in enumerate(names) for b in names[i + 1:]}


def fmt_utc(t, ms=True):
    dt = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S") + (f".{int(dt.microsecond / 1000):03d}" if ms else "") + " UTC"


def parse_utc(s):
    """'2026-11-22 10:30:00', '2026-11-22T10:30:00Z' o solo '10:30:00' (oggi, UTC) -> secondi Unix."""
    s = s.strip().replace("T", " ").rstrip("Zz").replace(" UTC", "").strip()
    if len(s) <= 8:
        today = datetime.datetime.now(datetime.timezone.utc).date()
        h = datetime.datetime.strptime(s, "%H:%M:%S" if s.count(":") == 2 else "%H:%M").time()
        return datetime.datetime.combine(today, h, tzinfo=datetime.timezone.utc).timestamp()
    fmt = "%Y-%m-%d %H:%M:%S" if s.count(":") == 2 else "%Y-%m-%d %H:%M"
    return datetime.datetime.strptime(s, fmt).replace(tzinfo=datetime.timezone.utc).timestamp()


# ---------------------------------------------------------------------------------------------------------- Appuntamento
def plan_run(t0, count, interval_ms, lead_rx=5.0, tail=10.0):
    """Orari di una prova concordata: chi riceve parte `lead_rx` secondi prima di T0 e ascolta fino a `tail` secondi dopo l'ultimo pacchetto."""
    dur = count * interval_ms / 1000.0
    return {"t0": t0, "tx_start": t0, "rx_start": t0 - lead_rx, "rx_window_s": int(dur + lead_rx + tail + 0.999), "tx_duration_s": dur}


def wait_until(clock, target_utc, stop=None, sleep=time.sleep, spin_s=0.05):
    """Aspetta l'ora UTC `target_utc` (secondi Unix). Ritorna l'errore in secondi (ora vera - bersaglio al momento dell'uscita), o None se interrotta."""
    while True:
        if stop is not None and stop.is_set():
            return None
        rest = target_utc - clock.now()
        if rest <= 0:
            return clock.now() - target_utc
        if rest > spin_s + 0.02:
            sleep(min(0.2, rest - spin_s))
        else:
            sleep(0.001)      # negli ultimi istanti si controlla ogni millisecondo: precisione dell'ordine di 1-2 ms
