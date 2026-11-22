"""Prove di orologio, NTP, GPS, distanze e appuntamento, con sorgenti finte: python3 -I tests/app/test_timesync.py"""
import datetime
import os
import socket
import struct
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "app"))
from volora_misure import geo, timesync as ts  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


def nmea(body):
    c = 0
    for ch in body:
        c ^= ord(ch)
    return f"${body}*{c:02X}"


# ---- geo ----
check(abs(geo.haversine_km(0, 0, 1, 0) - 111.195) < 0.01 and abs(geo.haversine_km(0, 0, 0, 1) - 111.195) < 0.01, "1 grado di meridiano o di equatore = 111,195 km")
d = geo.haversine_km(41.9028, 12.4964, 45.4642, 9.1900)
check(474 < d < 480, f"Roma-Milano {d:.1f} km")
check(geo.haversine_km(43.0, 11.0, 43.0, 11.0) == 0.0, "distanza di un punto da se stesso")
check(abs(geo.bearing_deg(0, 0, 1, 0)) < 1e-6 and abs(geo.bearing_deg(0, 0, 0, 1) - 90) < 1e-6 and abs(geo.bearing_deg(1, 0, 0, 0) - 180) < 1e-6, "direzioni nord, est, sud")
check(geo.maidenhead(43.7696, 11.2558) == "JN53ps" and geo.maidenhead(43.7696, 11.2558, 4) == "JN53", "locatore di Firenze: JN53ps")
la, lo = geo.from_maidenhead("JN53ps")
check(abs(la - 43.7696) < 0.03 and abs(lo - 11.2558) < 0.05, f"dal locatore al centro del quadrato: {la:.3f}, {lo:.3f}")
check(geo.maidenhead(*geo.from_maidenhead("JN53ps12"), 8) == "JN53ps12", "locatore a 8 caratteri: andata e ritorno")
check(geo.maidenhead(-33.87, 151.21) == "QF56od" and geo.maidenhead(0, 0) == "JJ00aa", "locatori di Sydney e dell'origine")
for bad in ("XX", "JN5", "5N53ps", "JN53pp9"):
    try:
        geo.from_maidenhead(bad)
        check(False, "locatore non valido accettato: " + bad)
    except ValueError:
        pass
check(True, "locatori non validi rifiutati")

# ---- NMEA ----
rmc = nmea("GPRMC,123519.00,A,4346.176,N,01115.348,E,000.0,084.4,221126,,,A")
d = ts.parse_nmea(rmc)
exp = datetime.datetime(2026, 11, 22, 12, 35, 19, tzinfo=datetime.timezone.utc).timestamp()
check(d["tipo"] == "RMC" and d["fix"] and abs(d["utc"] - exp) < 1e-6 and abs(d["lat"] - 43.7696) < 1e-3 and abs(d["lon"] - 11.2558) < 1e-3, "RMC: ora, data, posizione")
gga = nmea("GNGGA,123519.00,4346.176,N,01115.348,E,1,09,0.9,142.5,M,46.9,M,,")
d = ts.parse_nmea(gga)
check(d["tipo"] == "GGA" and d["fix"] and d["sats"] == 9 and d["hdop"] == 0.9 and d["alt"] == 142.5, "GGA: fix, satelliti, HDOP, quota")
d = ts.parse_nmea(nmea("GPGGA,123519.00,,,,,0,00,99.9,,M,,M,,"))
check(d and not d["fix"] and d["sats"] == 0 and d["lat"] is None, "GGA senza fix")
d = ts.parse_nmea(nmea("GPRMC,123519.00,V,,,,,,,221126,,,N"))
check(d and not d["fix"] and d["lat"] is None, "RMC non valida (V)")
d = ts.parse_nmea(nmea("GPZDA,123519.00,22,11,2026,00,00"))
check(abs(d["utc"] - exp) < 1e-6, "ZDA")
south = ts.parse_nmea(nmea("GPRMC,000000.00,A,3352.200,S,15112.600,E,0,0,010126,,,A"))
check(south["lat"] < 0 and south["lon"] > 150 and abs(south["lat"] + 33.87) < 0.01, "emisferi sud ed est")
check(ts.parse_nmea(rmc[:-2] + "00") is None and ts.parse_nmea("$GPRMC,1,2") is None and ts.parse_nmea("rumore") is None, "somma di controllo sbagliata e frasi rotte scartate")

# ---- NTP con un server finto in locale ----
class FakeNtp(threading.Thread):
    def __init__(self, offset, delay=0.0, answer=True):
        super().__init__(daemon=True)
        self.offset, self.delay, self.answer = offset, delay, answer
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.stop = False

    def run(self):
        while not self.stop:
            try:
                data, addr = self.sock.recvfrom(512)
            except socket.timeout:
                continue
            if not self.answer:
                continue
            time.sleep(self.delay)
            t = time.time() + self.offset + ts.NTP_DELTA
            s, f = int(t), int((t % 1) * 2 ** 32)
            pkt = bytearray(48)
            pkt[0] = 0x24
            pkt[32:40] = struct.pack("!II", s, f)
            pkt[40:48] = struct.pack("!II", s, f)
            self.sock.sendto(bytes(pkt), addr)


srv = FakeNtp(0.250)
srv.start()
off, delay = ts.ntp_query("127.0.0.1", srv.port, timeout=1.0)
check(abs(off - 0.250) < 0.01 and 0 <= delay < 0.05, f"NTP: scarto {off * 1000:.1f} ms (atteso 250), ritardo {delay * 1000:.1f} ms")
off, unc, name = ts.ntp_sync(["127.0.0.1"], samples=3, timeout=1.0, port=srv.port)
check(abs(off - 0.250) < 0.01 and 0.002 <= unc < 0.05, f"NTP: sincronizzazione, incertezza {unc * 1000:.1f} ms")
srv.stop = True
dead = FakeNtp(0.0, answer=False)
dead.start()
try:
    ts.ntp_sync(["127.0.0.1"], samples=1, timeout=0.3, port=dead.port)
    check(False, "server muto: serviva un errore")
except OSError as e:
    check("nessun server" in str(e), "server NTP muto: errore chiaro")
dead.stop = True

# ---- GPS finto ----
class Fake:
    def __init__(self, t):
        self.t = t


# senza PPS: il computer e' avanti di 2 s, il ricevitore ritarda la frase di 0,35 s
clk = Fake(1000.0)
g = ts.GpsReader(lambda: None, baud=9600, now=lambda: clk.t)
true_s = datetime.datetime(2026, 11, 22, 12, 0, 0, tzinfo=datetime.timezone.utc).timestamp()
for k in range(5):
    S = true_s + k
    line = nmea(f"GPRMC,{12:02d}0{0 if k < 10 else ''}0{k:01d}.00,A,4346.176,N,01115.348,E,0,0,221126,,,A")
    arrival = S + 2.0 + 0.35 + 0.073          # ora del computer all'arrivo della frase (computer +2 s, ricevitore +0,35 s, trasmissione 0,073 s)
    clk.t = arrival
    g.feed(line, arrival, nbytes=70)
    g.feed(nmea("GPGGA,%02d0%d00.00,4346.176,N,01115.348,E,1,08,1.1,140,M,46,M,," % (12, k)), arrival, nbytes=70)
o = g.clock_offset()
check(o is not None and abs(o[0] - (-2.0 - 0.35)) < 0.005 and o[1] >= 0.4 and not o[2], f"GPS senza PPS: scarto {o[0]:.3f} s, incertezza {o[1]:.2f} s (onesta: il ritardo del ricevitore non si conosce)")
pos = g.position()
check(pos and abs(pos[0] - 43.7696) < 1e-3 and g.sats == 8 and g.hdop == 1.1 and g.fix, "GPS: posizione, satelliti, HDOP")
# con PPS sul pin DCD: scarto esatto a pochi ms
clk2 = Fake(5000.0)
g2 = ts.GpsReader(lambda: None, baud=9600, pps=True, now=lambda: clk2.t)
for k in range(5):
    S = true_s + k
    edge = S + 2.0                              # il fronte PPS letto dal computer (avanti di 2 s)
    g2.pps_edges.append(edge)
    arrival = edge + 0.3
    clk2.t = arrival
    g2.feed(nmea(f"GPRMC,12000{k}.00,A,4346.176,N,01115.348,E,0,0,221126,,,A"), arrival, nbytes=70)
o2 = g2.clock_offset()
check(o2 is not None and o2[2] and abs(o2[0] - (-2.0)) < 1e-6 and o2[1] < 0.01, f"GPS con PPS: scarto {o2[0]:.4f} s, incertezza {o2[1] * 1000:.0f} ms")
clk2.t += 60
check(g2.clock_offset() is None, "campioni vecchi (60 s): nessuno scarto")
# lettore con una seriale finta e una frase rotta
lines = [nmea("GPRMC,120000.00,A,4346.176,N,01115.348,E,0,0,221126,,,A").encode() + b"\r\n", b"$GPGGA,rotta\r\n", b"rumore\r\n"]


class FakeSerial:
    cd = False

    def readline(self):
        time.sleep(0.01)
        return lines.pop(0) if lines else b""

    def close(self):
        pass


g3 = ts.GpsReader(lambda: FakeSerial(), baud=9600)
g3.start()
time.sleep(0.3)
g3.stop()
check(g3.lines == 3 and g3.bad == 1 and g3.position() is not None, f"lettore: 3 righe, 1 frase rotta contata ({g3.lines}, {g3.bad})")

# ---- orologio ----
c = Fake(10000.0)
clock = ts.Clock(now=lambda: c.t)
check(clock.best()[0] == "computer" and clock.now() == 10000.0, "senza sorgenti: ora del computer")
clock.set_source("gps", -2.3, 0.4)
check(clock.best()[0] == "gps" and abs(clock.now() - 9997.7) < 1e-9, "una sorgente: la usa")
clock.set_source("ntp", -2.0, 0.02)
check(clock.best()[0] == "ntp" and abs(clock.now() - 9998.0) < 1e-9, "sceglie la sorgente con l'incertezza minore")
clock.set_source("gps-pps", -2.001, 0.005)
check(clock.best()[0] == "gps-pps", "il PPS vince")
diff = clock.differences()
check(abs(diff[("gps", "ntp")] - (-0.3)) < 1e-9, "differenza fra GPS e NTP per il controllo incrociato")
c.t += 1000
check(clock.best()[0] == "computer", "sorgenti vecchie (> 15 minuti): si torna al computer")
info = ts.fmt_utc(1795344000.123)
check(info.endswith("UTC") and ".123" in info, "formato UTC: " + info)
check(ts.parse_utc("2026-11-22T10:30:00Z") == datetime.datetime(2026, 11, 22, 10, 30, tzinfo=datetime.timezone.utc).timestamp(), "parse dell'ora UTC con data")
today = datetime.datetime.now(datetime.timezone.utc).date()
check(ts.parse_utc("10:30") == datetime.datetime.combine(today, datetime.time(10, 30), tzinfo=datetime.timezone.utc).timestamp(), "parse dell'ora senza data (oggi)")

# ---- appuntamento ----
p = ts.plan_run(1000.0, 200, 300, lead_rx=5, tail=10)
check(p["tx_start"] == 1000.0 and p["rx_start"] == 995.0 and p["rx_window_s"] == 75 and abs(p["tx_duration_s"] - 60.0) < 1e-9, "piano: chi riceve parte 5 s prima, ascolta 75 s")
c2 = Fake(2000.0)
clk3 = ts.Clock(now=lambda: c2.t)


def fake_sleep(s):
    c2.t += s


err = ts.wait_until(clk3, 2003.0, sleep=fake_sleep)
check(err is not None and 0 <= err < 0.1, f"attesa fino all'ora concordata: errore {err * 1000:.0f} ms")
ev = threading.Event()
ev.set()
check(ts.wait_until(clk3, 99999.0, stop=ev, sleep=fake_sleep) is None, "attesa interrotta con STOP")
clk3.set_source("gps", 1.5, 0.01)
c2.t = 2000.0
err = ts.wait_until(clk3, 2003.0, sleep=fake_sleep)
check(err is not None and 0 <= err < 0.1 and abs(c2.t - 2001.5) < 0.2, "l'attesa usa l'ora corretta dallo scarto della sorgente")

print("orologio: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
