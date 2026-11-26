#!/usr/bin/env python3
"""Pilota due schede col firmware di misura (firmware/misura) e scrive i risultati in un CSV.

  misura.py scala  --tx PORTA --rx PORTA --call NOMINATIVO --modes L4,L5,F3 --count 200 [--att 60,70,80] [--out risultati.csv]
  misura.py analizza risultati.csv [--soglia 10]
  misura.py scala --simulate ...      (due schede finte, per provare lo script senza hardware)

I modi sono quelli di docs/scala-modi.md (L1-L13 LoRa, F1-F6 FSK). Senza --att l'attenuazione totale si chiede a tutto schermo ad ogni punto
(valore misurato con il NanoVNA, in dB). Serve pyserial per le schede vere (pip install pyserial)."""
import argparse, csv, math, os, random, re, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scala_modi as sm  # stesse tabelle dello studio

CAPS_RXBW = {"SX1278": 250.0, "SX1262": 467.0}  # banda di ricezione massima della radio (RadioLib)

def mode_table():
    t = {}
    for i, (bw, sf) in enumerate(sm.LORA, 1):
        t[f"L{i}"] = ("LORA", bw, sf)
    for i, (br, dev) in enumerate(sm.FSK, 1):
        t[f"F{i}"] = ("FSK", br, dev)
    return t

def mode_command(code, chip):
    kind, a, b = mode_table()[code]
    if kind == "LORA":
        return f"MODE LORA {a:g} {b} 5", ("LORA", a, b)
    rxbw = min((a + 2 * b) / (2 if chip == "SX1278" else 1), CAPS_RXBW[chip])   # SX1278: banda laterale singola; SX1262: doppia (datasheet)
    return f"MODE FSK {a:g} {b:g} {rxbw:g}", ("FSK", a, b)

def sens_estimate(code):
    kind, a, b = mode_table()[code]
    if kind == "LORA":
        return sm.sens_lora(a, b)
    return -174 + 10 * math.log10((a + 2 * b) * 1000) + sm.NF + 12

# ---------- Schede ----------
class Board:
    def __init__(self, port, name):
        try:
            import serial
        except ImportError:
            sys.exit("serve pyserial: pip install pyserial")
        self.s = serial.Serial(port, 921600, timeout=0.2)
        self.name = name
        time.sleep(0.5)
        self.s.reset_input_buffer()
        self.chip = None

    def send(self, line):
        self.s.write((line + "\n").encode())

    def read_until(self, prefix, timeout):
        end = time.time() + timeout
        lines = []
        while time.time() < end:
            raw = self.s.readline().decode(errors="replace").strip()
            if not raw:
                continue
            lines.append(raw)
            if raw.startswith(prefix):
                return raw, lines
            if raw.startswith("ERR"):
                return raw, lines
        return None, lines

    def command(self, line, expect="MODE", timeout=5):
        self.send(line)
        r, _ = self.read_until(expect, timeout)
        if r is None or r.startswith("ERR"):
            sys.exit(f"{self.name}: '{line}' non riuscito: {r}")
        return r

    def info(self):
        self.send("INFO")
        r, _ = self.read_until("INFO", 3)
        m = re.search(r"INFO \S+ (\S+)", r or "")
        self.chip = m.group(1) if m else "SX1278"
        self.read_until("MODE", 2)
        return self.chip

class SimBoard:
    """Scheda finta: la probabilita' che un pacchetto arrivi segue una curva attorno alla sensibilita' stimata."""
    link = {"sens": -120.0, "power": 2, "att": 0.0, "sent": 0, "ok": 0, "rng": random.Random(1)}
    def __init__(self, name, chip="SX1278"):
        self.name, self.chip, self.mode = name, chip, None
    def info(self):
        return self.chip
    def command(self, line, expect="MODE", timeout=5):
        return "OK"
    def set_mode(self, code):
        SimBoard.link["sens"] = sens_estimate(code)
        self.mode = code

# ---------- Una misura ----------
def run_point(tx, rx, code, count, interval, power, att, simulate, call, freq):
    cmd, _ = mode_command(code, tx.chip)
    if simulate:
        tx.set_mode(code)
        prx = power - att
        sens = SimBoard.link["sens"]
        pok = 1.0 / (1.0 + math.exp(-(prx - sens) / 1.0))
        rng = SimBoard.link["rng"]
        ok = sum(1 for _ in range(count) if rng.random() < pok)
        snr = prx - (-174 + 10 * math.log10(125000) + sm.NF)
        return dict(sent=count, ok=ok, bad=0, rssi=prx, snr=snr, fei=0.0, toa_mean=0, toa_calc=0)
    for b in (tx, rx):
        b.command(cmd)
        b.command(f"POWER {power}")
    window = int(count * interval / 1000.0) + 15
    result = {}
    def do_rx():
        rx.send(f"RX {window}")
        line, _ = rx.read_until("RXSUM", window + 10)
        result["rx"] = line
    th = threading.Thread(target=do_rx)
    th.start()
    time.sleep(1.0)
    tx.send(f"TX {count} {interval}")
    txline, _ = tx.read_until("TXSUM", window + 10)
    th.join()
    kv = lambda line: dict(re.findall(r"(\w+)=(-?[\d.]+|nan)", line or ""))
    t, r = kv(txline), kv(result.get("rx"))
    f = lambda d, k: float(d.get(k, "nan"))
    return dict(sent=int(f(t, "sent")) if t else 0, ok=int(f(r, "ok")) if r else 0, bad=int(f(r, "bad")) if r else 0,
                rssi=f(r, "rssi"), snr=f(r, "snr"), fei=f(r, "fei_hz"), toa_mean=f(t, "toa_mean_us"), toa_calc=f(t, "calc_us"))

FIELDS = ["time", "mode", "freq_mhz", "power_dbm", "att_db", "p_rx_dbm", "sent", "rx_ok", "rx_bad", "loss_pct", "rssi", "snr", "fei_hz", "toa_mean_us", "toa_calc_us"]

def cmd_scala(a):
    if a.simulate:
        tx, rx = SimBoard("TX"), SimBoard("RX")
    else:
        if not (a.tx and a.rx):
            sys.exit("servono --tx e --rx (oppure --simulate)")
        tx, rx = Board(a.tx, "TX"), Board(a.rx, "RX")
    tx.info(); rx.info()
    if not a.simulate:
        for b in (tx, rx):
            b.command(f"CALL {a.call}", "OK")
            b.command(f"FREQ {a.freq}")
            b.command(f"PAYLOAD {a.payload}")
    new = not os.path.exists(a.out)
    with open(a.out, "a", newline="") as fh:
        w = csv.DictWriter(fh, FIELDS)
        if new:
            w.writeheader()
        for code in a.modes.split(","):
            code = code.strip().upper()
            if code not in mode_table():
                sys.exit(f"modo sconosciuto: {code}")
            atts = [float(x) for x in a.att.split(",")] if a.att else None
            idx = 0
            while True:
                if atts:
                    if idx >= len(atts):
                        break
                    att = atts[idx]; idx += 1
                else:
                    s = input(f"[{code}] attenuazione totale in dB (vuoto = passa al modo successivo): ").strip()
                    if not s:
                        break
                    att = float(s)
                r = run_point(tx, rx, code, a.count, a.interval, a.power, att, a.simulate, a.call, a.freq)
                loss = 100.0 * (1 - r["ok"] / r["sent"]) if r["sent"] else 100.0
                row = dict(time=time.strftime("%Y-%m-%d %H:%M:%S"), mode=code, freq_mhz=a.freq, power_dbm=a.power, att_db=att,
                           p_rx_dbm=a.power - att, sent=r["sent"], rx_ok=r["ok"], rx_bad=r["bad"], loss_pct=round(loss, 1),
                           rssi=r["rssi"], snr=r["snr"], fei_hz=r["fei"], toa_mean_us=r["toa_mean"], toa_calc_us=r["toa_calc"])
                w.writerow(row); fh.flush()
                print(f"{code} att {att:g} dB -> p_rx {a.power - att:g} dBm: {r['ok']}/{r['sent']} ricevuti, perdita {loss:.1f} %")

def cmd_analizza(a):
    best = {}
    with open(a.file, newline="") as fh:
        for r in csv.DictReader(fh):
            if float(r["loss_pct"]) <= a.soglia:
                p = float(r["p_rx_dbm"])
                if r["mode"] not in best or p < best[r["mode"]]:
                    best[r["mode"]] = p
    print(f"Sensibilita' = potenza ricevuta piu' bassa con perdita <= {a.soglia:g} %")
    for m in sorted(best, key=lambda x: (x[0], int(x[1:]))):
        est = sens_estimate(m)
        print(f"{m}: {best[m]:.0f} dBm (stima dello studio {est:.0f} dBm, differenza {best[m] - est:+.0f} dB)")

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scala")
    s.add_argument("--tx"); s.add_argument("--rx"); s.add_argument("--call", default="N0CALL1")
    s.add_argument("--modes", default="L4"); s.add_argument("--count", type=int, default=200)
    s.add_argument("--interval", type=int, default=300, help="ms tra un pacchetto e il successivo")
    s.add_argument("--power", type=int, default=2); s.add_argument("--freq", type=float, default=433.475)
    s.add_argument("--payload", type=int, default=255); s.add_argument("--att", help="elenco di attenuazioni in dB, per esempio 60,70,80")
    s.add_argument("--out", default="risultati.csv"); s.add_argument("--simulate", action="store_true")
    s.set_defaults(fn=cmd_scala)
    z = sub.add_parser("analizza"); z.add_argument("file"); z.add_argument("--soglia", type=float, default=10.0)
    z.set_defaults(fn=cmd_analizza)
    a = ap.parse_args()
    a.fn(a)

if __name__ == "__main__":
    main()
