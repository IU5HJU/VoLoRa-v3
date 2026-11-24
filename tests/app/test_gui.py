"""Prova dell'interfaccia con le schede finte: va eseguita con uno schermo (anche virtuale: xvfb-run).
   xvfb-run -a python3 tests/app/test_gui.py [cartella-schermate]
Salta se Tkinter non c'e'."""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "app"))
try:
    import tkinter as tk
except ImportError:
    print("Tkinter non disponibile: prova saltata")
    sys.exit(0)
from volora_misure import gui  # noqa: E402

shots = sys.argv[1] if len(sys.argv) > 1 else None
os.environ.setdefault("APPDATA", os.path.join(os.environ.get("TMPDIR", "/tmp"), "volora-test-config"))
fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


def pump(root, seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def shot(root, name):
    if shots:
        os.makedirs(shots, exist_ok=True)
        root.update()
        os.system(f"import -window root '{os.path.join(shots, name)}' 2>/dev/null")


root = tk.Tk()
app = gui.App(root, simulate=True)
pump(root, 0.3)
app.action("F1")
pump(root, 0.5)
check("INFO" in app.pa.log.get("1.0", "end"), "F1: INFO sul monitor della scheda A")
app.call.set("IU5HJU")
app.action("F2")
pump(root, 0.5)
check("OK call IU5HJU" in app.pb.log.get("1.0", "end"), "F2: nominativo su entrambe")
app.mode.current(3)  # L4
app.vars["att"].set("100"); app.vars["count"].set("20"); app.vars["interval"].set("300"); app.vars["payload"].set("64")
app.action("F3")
pump(root, 1.5)
check("Modo L4" in app.status.get(), "F3: modo applicato: " + app.status.get())
app.action("F4")
for _ in range(100):
    pump(root, 0.2)
    if app.rows:
        break
check(len(app.rows) == 1 and app.rows[0]["rx_ok"] == 20, "F4: una riga di risultato con 20/20")
check(len(app.tree.get_children()) == 1, "tabella dei risultati aggiornata")
txt = app.pa.log.get("1.0", "end") + app.pb.log.get("1.0", "end")
check("TXSUM" in txt and "RXSUM" in txt, "monitor: righe TXSUM e RXSUM")
# attenuazione oltre la sensibilita': perdita alta
app.vars["att"].set("140")
app.action("F4")
for _ in range(100):
    pump(root, 0.2)
    if len(app.rows) == 2:
        break
check(len(app.rows) == 2 and app.rows[1]["loss_pct"] >= 90, "seconda misura sotto la sensibilita'")
# scheda Modulo 2,4 GHz con moduli finti
from volora_misure import uartlink  # noqa: E402
pair = uartlink.FakeModulePair(loss=0.0, seed=1)
streams = {"/dev/fakeA": pair.a, "/dev/fakeB": pair.b}
app.uart_opener = lambda port, baud, parity: streams[port]
app.u_vars["ptx"].set("/dev/fakeA"); app.u_vars["prx"].set("/dev/fakeB")
app.u_vars["count"].set("20"); app.u_vars["size"].set("80"); app.u_vars["interval"].set("0.01"); app.u_vars["wait"].set("1")
app.uart_run()
for _ in range(100):
    pump(root, 0.2)
    if "UARTSUM" in app.u_log.get("1.0", "end"):
        break
check("ricevuti=20" in app.u_log.get("1.0", "end"), "scheda Modulo 2,4 GHz: prova con moduli finti, 20 su 20")
fm_cfg = uartlink.FakeConfigModule()
app.uart_opener = lambda port, baud, parity: fm_cfg
app.c_vars["port"].set("/dev/fakeC"); app.c_vars["chan"].set("30"); app.c_air.current(4); app.c_baud.set("115200")
app.uart_cfg_write()
for _ in range(60):
    pump(root, 0.2)
    if "Scritti e riletti" in app.u_log.get("1.0", "end"):
        break
txt = app.u_log.get("1.0", "end")
check("Scritti e riletti" in txt and "canale 30" in txt and "115200" in txt and "2460 MHz" in txt, "scheda Modulo 2,4 GHz: scrittura e rilettura dei parametri con un modulo finto")
# serie con F10
app.series_modes.set("L4,L5"); app.series_count.set("5"); app.vars["att"].set("100")
app.action("F10")
for _ in range(150):
    pump(root, 0.2)
    if len(app.rows) == 4:
        break
check(len(app.rows) == 4 and [r["mode"] for r in app.rows[2:]] == ["L4", "L5"], "F10: la serie aggiunge una riga per modo")
# riga dei comandi con cronologia
app.pa.entry.insert(0, "SHOW"); app.pa.send()
pump(root, 0.3)
app.pa.history(-1)
check(app.pa.entry.get() == "SHOW", "cronologia dei comandi (freccia su)")
# immagini
app.img_kind.set("blob"); app.img_size.set("5000")
os.environ["HOME"] = os.environ.get("TMPDIR", "/tmp")
app.gen_image()
check(len(app.est.get_children()) == 15 and "5000 byte" in app.img_info.get(), "scheda Immagini: stime per 15 gradini")
app.nb.select(1)
pump(root, 0.3)
shot(root, "gui-immagini.png")
app.nb.select(2)
pump(root, 0.3)
shot(root, "gui-github.png")
app.nb.select(0)
pump(root, 0.3)
shot(root, "gui-misure.png")
app.action("Ctrl+L")
check(app.pa.log.get("1.0", "end").strip() == "", "Ctrl+L pulisce il monitor")
app.action("Esc")
pump(root, 0.3)
check("STOP" in app.status.get(), "Esc: STOP")
root.destroy()

# collegamento con riscontro: SerialBoard sostituita da una scheda finta (nessuna seriale vera)
from volora_misure import serialio  # noqa: E402
root = tk.Tk()
app = gui.App(root, simulate=False)
link = serialio.FakeLink()
made = []


def fake_serial(name, port, baud=921600):
    b = serialio.FakeBoard(name, link, "SX1278", speed=100.0)
    made.append(b)
    return b


serialio.SerialBoard = fake_serial
pump(root, 0.2)
check(app.pa.state.cget("text") == "○ scollegata", "prima di collegare: indicatore 'scollegata'")
app.pa.port.set("/dev/ttyUSB0")
app.pa.toggle()
pump(root, 0.3)
check(app.pa.state.cget("text") == "● collegata" and app.pa.btn.cget("text") == "Scollega", "collegando: indicatore verde e pulsante 'Scollega'")
check("[sistema] collegata a /dev/ttyUSB0" in app.pa.log.get("1.0", "end"), "collegando: messaggio nel monitor")
pump(root, 2.3)
check("INFO misura" in app.pa.log.get("1.0", "end") and app.pa.chip.cget("text") == "SX1278", "dopo l'avvio parte INFO da solo e compare il chip")
app.pa.toggle()
pump(root, 0.2)
check(app.pa.state.cget("text") == "○ scollegata" and app.pa.btn.cget("text") == "Collega", "scollegando: indicatore torna grigio")
app.pb.port.set("")
shown = []
gui.messagebox.showinfo = lambda *a, **k: shown.append(a)
app.pb.toggle()
check(len(shown) == 1 and app.pb.board is None, "senza porta scelta: avviso e nessun collegamento")
root.destroy()

# ---- prove sul campo con una scheda sola, NTP e GPS finti ----
import datetime  # noqa: E402
import tempfile  # noqa: E402
from volora_misure import timesync, field  # noqa: E402

root = tk.Tk()
app = gui.App(root, simulate=False)
link = serialio.FakeLink()
serialio.SerialBoard = lambda name, port, baud=921600: serialio.FakeBoard(name, link, "SX1278", speed=100.0)
app.pa.port.set("/dev/ttyACM0")
app.pa.toggle()
app.call.set("IU5HJU")
pump(root, 0.3)
# F5 e F6 con una scheda sola
app.vars["count"].set("3"); app.vars["interval"].set("100"); app.vars["payload"].set("64")
app.action("F3") if False else None
app.action("F5")
pump(root, 1.0)
check("TXSUM sent=3" in app.pa.log.get("1.0", "end"), "una scheda sola: F5 trasmette")
app.action("F6")
pump(root, 4.0)
check("RXSUM" in app.pa.log.get("1.0", "end"), "una scheda sola: F6 ascolta (prima non faceva niente)")
# NTP finto
app.ntp_func = lambda servers: (0.25, 0.003, servers[0])
app.sync_ntp()
pump(root, 0.5)
check("ntp" in app.clock.sources and abs(app.clock.sources["ntp"][0] - 0.25) < 1e-9 and "250" in app.lbl_ntp.cget("text"), "NTP: sorgente impostata, scarto mostrato: " + app.lbl_ntp.cget("text"))


class FakeGpsSerial:
    cd = False

    def __init__(self):
        self.k = 0

    def readline(self):
        time.sleep(0.05)
        now = datetime.datetime.now(datetime.timezone.utc)
        hms = now.strftime("%H%M%S") + ".00"
        self.k += 1
        body = (f"GPRMC,{hms},A,4346.176,N,01115.348,E,0,0,{now.strftime('%d%m%y')},,,A" if self.k % 2 else
                f"GPGGA,{hms},4346.176,N,01115.348,E,1,10,0.8,95.0,M,46.9,M,,")
        c = 0
        for ch in body:
            c ^= ord(ch)
        return f"${body}*{c:02X}\r\n".encode()

    def close(self):
        pass


app.gps_opener = lambda port, baud: FakeGpsSerial()
app.gps_port.set("/dev/ttyACM9")
app.toggle_gps()
pump(root, 2.0)
check(app.gps is not None and app.gps.position() is not None and "FIX" in app.lbl_gps.cget("text") and "JN53" in app.lbl_gps.cget("text"), "GPS finto: fix, posizione e locatore: " + app.lbl_gps.cget("text"))
check("gps" in app.clock.sources, "GPS finto: compare fra le sorgenti dell'orologio")
check(app.clock.best()[0] == "ntp", "l'orologio sceglie l'NTP (incertezza minore del GPS senza PPS)")
check("Distanza" in app.lbl_dist.cget("text") or "Manca la posizione del collega" in app.lbl_dist.cget("text"), "etichetta della distanza: " + app.lbl_dist.cget("text")[:70])
# appuntamento: parte all'ora giusta
app.role.set("TX")
app.mode.current(3)
app.vars["count"].set("5"); app.vars["interval"].set("100"); app.vars["payload"].set("64")
t0 = int(app.clock.now()) + 7
app.t0_var.set(timesync.fmt_utc(t0, ms=False).replace(" UTC", ""))
app.program_run()
pump(root, 0.5)
check(app.sched is not None and app.sched["state"] == "attesa" and "partenza fra" in app.lbl_count.cget("text"), "appuntamento: conto alla rovescia: " + app.lbl_count.cget("text"))
for _ in range(120):
    pump(root, 0.2)
    if app.field_runs:
        break
check(len(app.field_runs) == 1 and app.field_runs[0]["sent"] == 5 and app.field_runs[0]["role"] == "TX", "la prova e' partita ed e' registrata")
r = app.field_runs[0]
check(abs(r["start_err_ms"]) < 60 and r["clock_src"] == "ntp" and r["t0"] == t0, f"errore di partenza {r['start_err_ms']:.1f} ms con orologio {r['clock_src']}")
check(r.get("my_loc", "").startswith("JN53") and r.get("my_alt") == 95.0, "posizione e quota dal GPS nella prova")
# serie programmata di due modi (coda e pausa ridotte per la prova)
app.field_runs.clear()
for ch in app.ftree.get_children():
    app.ftree.delete(ch)
app.series_tail, app.series_gap = 1.0, 0.0
app.lead_rx.set("1")
app.field_series.set("L4,L5"); app.series_count.set("3"); app.series_payload.set("26")
ts0 = int(app.clock.now()) + 7
app.t0_var.set(timesync.fmt_utc(ts0, ms=False).replace(" UTC", ""))
app.program_run()
for _ in range(200):
    pump(root, 0.2)
    if len(app.field_runs) == 2:
        break
check(len(app.field_runs) == 2 and [x["mode"] for x in app.field_runs] == ["L4", "L5"] and app.field_runs[1]["t0"] > ts0, "serie programmata: due prove consecutive L4 e L5")
check("SERIE" in app.plan_text() and "L4,L5" in app.plan_text(), "condizioni della serie per il collega: " + app.plan_text()[:80])
remote = "\n".join(field.export_line(dict(role="RX", t0=x["t0"], my_call="IK5XYZ", mode=x["mode"], freq_mhz=x["freq_mhz"], rx_ok=3, rx_bad=0, rssi=-100.0, snr=5.0, fei_hz=0.0)) for x in app.field_runs)
check(app.merge_many(remote) == (2, 0) and all(x.get("remote_call") == "IK5XYZ" for x in app.field_runs), "unione automatica di due righe del collega")
app.field_series.set("")
app.field_runs.clear()
for ch in app.ftree.get_children():
    app.ftree.delete(ch)
app.vars["count"].set("5"); app.vars["interval"].set("100"); app.vars["payload"].set("64")
app.lead_rx.set("5"); app.series_tail, app.series_gap = 10.0, 20.0
t0 = int(app.clock.now()) + 7
app.t0_var.set(timesync.fmt_utc(t0, ms=False).replace(" UTC", ""))
app.program_run()
for _ in range(120):
    pump(root, 0.2)
    if app.field_runs:
        break
r = app.field_runs[0]
# unione con il collega
rem = field.export_line(dict(role="RX", t0=t0, my_call="IK5XYZ", my_lat=44.0, my_lon=11.9, mode=r["mode"], freq_mhz=r["freq_mhz"], rx_ok=5, rx_bad=0, rssi=-100.0, snr=7.0, fei_hz=10.0))
res = app.merge_remote_text("Dati: " + rem)
check(res and res[0]["loss_pct"] == 0.0 and 40 < res[0]["distance_km"] < 70 and app.rem_call.get() == "IK5XYZ", f"unione con il collega: distanza {res[0]['distance_km']:.1f} km, perdita {res[0]['loss_pct']} %")
check("distanza" in app.status.get(), "stato: " + app.status.get())
app.root.clipboard_clear()
app.copy_mine()
check("VOLORA-PROVA 1" in app.root.clipboard_get() and "role=TX" in app.root.clipboard_get(), "copia dei miei dati negli appunti")
with tempfile.TemporaryDirectory() as td:
    path = os.path.join(td, "campo.csv")
    gui.filedialog.asksaveasfilename = lambda **k: path
    app.f_extra["percorso"].set("in vista"); app.f_extra["meteo"].set("sereno")
    app.save_field_csv()
    rows = open(path, encoding="utf-8").read().strip().split("\n")
    check(len(rows) == 2 and rows[0].split(",") == field.RILIEVO_FIELDS and "IK5XYZ" in rows[1] and "in vista" in rows[1], "CSV di rilievo salvato con la riga della prova")
def _all_text(w, acc):
    for c in w.winfo_children():
        try:
            acc.append(str(c.cget("text")))
        except Exception:  # noqa
            pass
        _all_text(c, acc)
    return acc


texts = _all_text(app.root, [])
check("⟳" not in texts and texts.count("Aggiorna") >= 3, "i pulsanti dell'elenco porte si chiamano 'Aggiorna' (prima un quadratino illeggibile)")
check(str(app.pa.log.cget("wrap")) == "word", "i monitor vanno a capo (le righe lunghe non si perdono)")
app.pa.board.inbox.put(("rx", "MODE LORA bw 250.00 kHz sf 7 cr 4/5 | freq 433.4750 MHz power 2 dBm payload 255 preamble 8 call IU5HJU ready 1 " + "x" * 120))
pump(root, 0.4)
check(app.pa.log.count("1.0", "end", "displaylines")[0] > app.pa.log.count("1.0", "end", "lines")[0], "una riga di 200 caratteri occupa piu' righe sullo schermo")
app.nb.select(app.tab_field)
pump(root, 0.4)
shot(root, "gui-campo.png")
app.toggle_gps()
check(app.gps is None and "gps" not in app.clock.sources, "GPS scollegato: sorgente tolta")
# appuntamento troppo vicino: rifiutato
shown = []
gui.messagebox.showwarning = lambda *a, **k: shown.append(a)
app.t0_var.set(timesync.fmt_utc(int(app.clock.now()) + 2, ms=False).replace(" UTC", ""))
app.program_run()
check(len(shown) == 1 and app.sched is None, "appuntamento fra meno di 5 s: rifiutato")
root.destroy()

# ---- GPS Bluetooth automatico, riconnessione, avvio automatico e calibrazione ----
from volora_misure import bluetooth as btmod  # noqa: E402

root = tk.Tk()
app = gui.App(root, simulate=False)
MAC = "00:11:22:33:44:55"
app.gps_port.set(btmod.label(MAC, "Nokia LD-3W"))
app.gps_retry_s = 0.5
opened = []


class DyingSerial(FakeGpsSerial):
    def readline(self):
        if self.k >= 24:
            raise OSError("collegamento Bluetooth chiuso dal GPS")
        return super().readline()


def bt_opener(mac):
    opened.append(mac)
    return (DyingSerial() if len(opened) == 1 else FakeGpsSerial()), f"Bluetooth {mac} canale 1 (finto)"


app.bt_opener = bt_opener
app.toggle_gps()
check(app.btn_gps.cget("text") == "Scollega GPS" and app.gps_want, "GPS Bluetooth: un clic, nessun terminale")
for _ in range(40):
    pump(root, 0.2)
    if app.gps is not None and app.gps.fix:
        break
pump(root, 0.5)
check(app.gps is not None and "FIX" in app.lbl_gps.cget("text") and opened == [MAC], "GPS Bluetooth: collegato in un thread, fix e posizione: " + app.lbl_gps.cget("text")[:60])
for _ in range(60):
    pump(root, 0.2)
    if len(opened) >= 2 and app.gps is not None and not app.gps.error and app.gps.fix:
        break
check(len(opened) == 2, f"collegamento caduto: riconnessione automatica (aperture: {len(opened)})")
check(app.gps is not None and app.gps.fix and "GPS" in app.lbl_gps.cget("text"), "dopo la riconnessione il GPS torna a dare il fix")
# calibrazione
app.ntp_func = lambda servers: (-0.013, 0.003, "finto")
app.gps.samples.clear()
app.gps.samples.extend([(-0.390, None)] * 14)
app.gps.last_sample = time.time()
app.calibrate_gps()
pump(root, 0.8)
check(abs(app.cfg["gps_delay_s"] - 0.377) < 1e-6 and app.gps.calibrated and "tarato" in app.lbl_cal.cget("text") and "377" in app.lbl_cal.cget("text"), "calibrazione dal pulsante: ritardo 377 ms salvato: " + app.lbl_cal.cget("text")[:80])
app.gps.samples.clear()
app.gps.samples.extend([(-0.390, None)] * 5)
app.calibrate_gps()
pump(root, 0.8)
check("non riuscita" in app.lbl_cal.cget("text") and "almeno 10" in app.lbl_cal.cget("text"), "calibrazione con pochi dati: messaggio chiaro")
# scollegamento volontario: niente piu' riconnessioni
n = len(opened)
app.toggle_gps()
pump(root, 1.5)
check(app.gps is None and not app.gps_want and len(opened) == n and app.btn_gps.cget("text") == "Collega GPS", "Scollega: il GPS resta scollegato e non si riconnette da solo")
# GPS spento: errore chiaro e nuovi tentativi, finche' non si scollega
tries = []


def bt_down(mac):
    tries.append(1)
    raise OSError("GPS 00:11:22:33:44:55 non raggiungibile: Host is down (acceso, vicino, non gia' collegato a un altro apparecchio?)")


app.bt_opener = bt_down
app.toggle_gps()
pump(root, 2.5)
check(len(tries) >= 2 and "non raggiungibile" in app.lbl_gps.cget("text") and "riprovo" in app.lbl_gps.cget("text"), f"GPS spento: errore chiaro e tentativi ({len(tries)}): " + app.lbl_gps.cget("text")[:70])
app.toggle_gps()
m = len(tries)
pump(root, 1.5)
check(len(tries) == m and app.gps is None, "dopo Scollega si smette di riprovare")
# avvio automatico
app.bt_opener = lambda mac: (FakeGpsSerial(), "Bluetooth finto")
app.gps_auto.set(True)
app._auto_gps()
pump(root, 1.5)
check(app.gps is not None and app.gps_want, "avvio automatico: il GPS si collega da solo")
app.toggle_gps()
root.destroy()
print("interfaccia: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
