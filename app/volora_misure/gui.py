"""Interfaccia grafica (Tkinter): due monitor seriali, tasti rapidi, misure, risultati, immagini di prova e invio su GitHub."""
import os
import queue
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import __version__, bluetooth, core, field, geo, runner, serialio, timesync

SHORTCUTS = [
    ("F1", "INFO", "Chiede a entrambe le schede il chip e la versione (INFO)"),
    ("F2", "Nominativo", "Manda CALL a entrambe le schede"),
    ("F3", "Modo", "Imposta modo, frequenza, potenza e pacchetto su entrambe"),
    ("F4", "Misura", "Esegue un punto di misura con l'attenuazione indicata e lo aggiunge ai risultati"),
    ("F5", "TX", "Solo trasmette: la scheda scelta manda N pacchetti"),
    ("F6", "RX 60 s", "Solo ascolta, per 60 secondi, sulla scheda che non trasmette"),
    ("F7", "CW 10 s", "Portante per il misuratore di potenza (10 secondi)"),
    ("Esc", "STOP", "Ferma subito TX, RX e CW"),
    ("F8", "Salva CSV", "Salva i risultati in un file CSV"),
    ("F9", "GitHub", "Va alla scheda GitHub per inviare i risultati"),
    ("Ctrl+L", "Pulisci", "Cancella i due monitor"),
]


class BoardPane(ttk.LabelFrame):
    """Un monitor seriale: scelta della porta, registro colorato, riga dei comandi con cronologia."""

    def __init__(self, master, app, name):
        super().__init__(master, text=f"Scheda {name}")
        self.app, self.name = app, name
        self.board = None
        self.hist, self.hist_i = [], 0
        top = ttk.Frame(self)
        top.pack(fill="x", padx=4, pady=3)
        self.port = ttk.Combobox(top, width=18, values=serialio_ports())
        self.port.pack(side="left")
        ttk.Button(top, text="Aggiorna", width=8, command=self.refresh).pack(side="left", padx=2)
        self.btn = ttk.Button(top, text="Collega", command=self.toggle)
        self.btn.pack(side="left", padx=2)
        self.state = tk.Label(top, text="○ scollegata", fg="#888888", font=("TkDefaultFont", 9, "bold"))
        self.state.pack(side="left", padx=(8, 2))
        self.chip = ttk.Label(top, text="—")
        self.chip.pack(side="left", padx=4)
        self.log = tk.Text(self, height=16, width=58, wrap="word", state="disabled", font=("TkFixedFont", 9))   # le righe lunghe vanno a capo
        sb = ttk.Scrollbar(self, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", pady=3)
        self.log.pack(side="top", fill="both", expand=True, padx=(4, 0), pady=3)
        self.log.tag_config("tx", foreground="#2a6fd6")
        self.log.tag_config("rx", foreground="#1b8a3c")
        self.log.tag_config("sys", foreground="#888888")
        self.log.tag_config("err", foreground="#c0392b")
        self.log.tag_config("sum", foreground="#8e44ad", font=("TkFixedFont", 9, "bold"))
        row = ttk.Frame(self)
        row.pack(fill="x", padx=4, pady=3, side="bottom")
        self.entry = ttk.Entry(row)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", self.send)
        self.entry.bind("<Up>", lambda e: self.history(-1))
        self.entry.bind("<Down>", lambda e: self.history(1))
        ttk.Button(row, text="Invia", command=self.send).pack(side="left", padx=2)

    def refresh(self):
        self.port["values"] = serialio_ports() + ["(finta)"]

    def toggle(self):
        if self.board is not None:
            self.app.disconnect(self)
        else:
            self.app.connect(self, self.port.get().strip())

    def show(self, kind, text):
        tag = kind
        if kind == "rx" and (text.startswith("ERR")):
            tag = "err"
        elif kind == "rx" and (text.startswith("TXSUM") or text.startswith("RXSUM")):
            tag = "sum"
        self.log.configure(state="normal")
        self.log.insert("end", ("> " if kind == "tx" else "") + text + "\n", tag)
        if int(self.log.index("end-1c").split(".")[0]) > 3000:
            self.log.delete("1.0", "500.0")
        if self.app.autoscroll.get():
            self.log.see("end")
        self.log.configure(state="disabled")

    def set_state(self, text, color):
        self.state.configure(text=text, fg=color)

    def clear(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def send(self, _e=None):
        line = self.entry.get().strip()
        if not line or self.board is None:
            return
        self.hist.append(line)
        self.hist_i = len(self.hist)
        self.board.send(line)
        self.entry.delete(0, "end")

    def history(self, d):
        if not self.hist:
            return
        self.hist_i = max(0, min(len(self.hist), self.hist_i + d))
        self.entry.delete(0, "end")
        if self.hist_i < len(self.hist):
            self.entry.insert(0, self.hist[self.hist_i])


def serialio_ports():
    try:
        from serial.tools import list_ports
        return [p.device for p in list_ports.comports()]
    except Exception:  # noqa: pyserial non installato
        return []


class App:
    def __init__(self, root, simulate=False):
        self.root = root
        self.simulate = simulate
        self.rows = []
        self.cfg = core.load_config()
        self.busy = threading.Event()
        self.fake_link = None
        self.clock = timesync.Clock()
        self.gps = None
        self.field_runs = []
        self.sched = None                      # appuntamento in corso: dizionario
        self.sched_stop = threading.Event()
        self.ntp_func = timesync.ntp_sync      # sostituibili dalle prove
        self.gps_opener = self._open_gps_serial
        self.bt_opener = bluetooth.open_bt        # (indirizzo) -> (oggetto tipo seriale, descrizione): sostituibile dalle prove
        self.gps_want = False                     # l'utente vuole il GPS collegato: se cade, si riconnette da solo
        self.gps_connecting = False
        self.gps_last_try = 0.0
        self.gps_retry_s = 6.0
        self.gps_note = ""
        self.ui = queue.Queue()   # funzioni da eseguire nel thread dell'interfaccia (i thread di lavoro non toccano Tk)
        root.title(f"VoLoRa V3 misure {__version__}" + (" (schede finte)" if simulate else ""))
        root.geometry("1280x800")
        self.autoscroll = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Collega le due schede e premi F1.")
        self._build()
        self._bind_keys()
        root.after(80, self._pump)
        root.protocol("WM_DELETE_WINDOW", self.close)
        if simulate:
            self.fake_link, a, b = serialio.fake_pair(speed=80.0)
            for pane, board in ((self.pa, a), (self.pb, b)):
                pane.board = board
                pane.btn.configure(text="Scollega")
                pane.port.set("(finta)")
                pane.set_state("● finta", "#1b8a3c")
                pane.chip.configure(text=board.chip)

    # ----- costruzione -----
    def _build(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True)
        self.nb = nb
        mis = ttk.Frame(nb)
        nb.add(mis, text="Misure")
        panes = ttk.Frame(mis)
        panes.pack(fill="both", expand=True, padx=4, pady=4)
        self.pa, self.pb = BoardPane(panes, self, "A"), BoardPane(panes, self, "B")
        self.pa.pack(side="left", fill="both", expand=True, padx=(0, 3))
        self.pb.pack(side="left", fill="both", expand=True, padx=(3, 0))
        self.pa.refresh(); self.pb.refresh()

        par = ttk.LabelFrame(mis, text="Parametri e tasti rapidi")
        par.pack(fill="x", padx=4, pady=2)
        r1 = ttk.Frame(par); r1.pack(fill="x", padx=4, pady=2)
        ttk.Label(r1, text="Nominativo").pack(side="left")
        self.call = tk.StringVar(value=self.cfg.get("call", ""))
        ttk.Entry(r1, textvariable=self.call, width=10).pack(side="left", padx=(2, 8))
        ttk.Label(r1, text="Modo").pack(side="left")
        self.mode = ttk.Combobox(r1, width=30, state="readonly", values=[f"{c}  {d}" for c, d in core.mode_names()])
        self.mode.current(3)
        self.mode.pack(side="left", padx=(2, 8))
        self.vars = {}
        r2 = ttk.Frame(par); r2.pack(fill="x", padx=4, pady=2)
        for rowf, items in ((r1, (("Freq MHz", "freq", "433.475", 8), ("Potenza dBm", "power", "2", 4), ("Pacchetto B", "payload", "255", 5))),
                            (r2, (("Quanti", "count", "200", 5), ("Intervallo ms", "interval", "300", 5), ("Attenuazione dB", "att", "60", 6)))):
            for label, key, val, w in items:
                ttk.Label(rowf, text=label).pack(side="left")
                v = tk.StringVar(value=val)
                self.vars[key] = v
                ttk.Entry(rowf, textvariable=v, width=w).pack(side="left", padx=(2, 8))
        ttk.Label(r2, text="Trasmette").pack(side="left", padx=(10, 0))
        self.txsel = tk.StringVar(value="A")
        ttk.Radiobutton(r2, text="A", variable=self.txsel, value="A").pack(side="left")
        ttk.Radiobutton(r2, text="B", variable=self.txsel, value="B").pack(side="left", padx=(0, 10))
        ttk.Checkbutton(r2, text="Segui il monitor", variable=self.autoscroll).pack(side="right")
        r3 = ttk.Frame(par); r3.pack(fill="x", padx=4, pady=(2, 4))
        for key, label, hint in SHORTCUTS:
            ttk.Button(r3, text=f"{key} {label}", width=11, command=lambda k=key: self.action(k)).pack(side="left", padx=1)

        res = ttk.LabelFrame(mis, text="Risultati (ogni misura F4 aggiunge una riga)")
        res.pack(fill="both", padx=4, pady=2)
        cols = ("mode", "att_db", "p_rx_dbm", "sent", "rx_ok", "loss_pct", "rssi", "snr", "fei_hz", "toa")
        self.tree = ttk.Treeview(res, columns=cols, show="headings", height=6)
        for c, t, w in (("mode", "Modo", 60), ("att_db", "Att dB", 70), ("p_rx_dbm", "P rx dBm", 80), ("sent", "Inviati", 70), ("rx_ok", "Ricevuti", 70),
                        ("loss_pct", "Perdita %", 80), ("rssi", "RSSI", 70), ("snr", "SNR", 70), ("fei_hz", "Deriva Hz", 80), ("toa", "ToA µs (mis./calc.)", 150)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill="x", padx=4, pady=3)
        ttk.Label(self.root, textvariable=self.status, relief="sunken", anchor="w").pack(fill="x", side="bottom")

        self._build_field(nb)
        self._build_images(nb)
        self._build_github(nb)
        self._build_help(nb)

    # ------------------------------------------------------------------------------------------ prove sul campo (una scheda)
    def _build_field(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="Prove sul campo")
        self.tab_field = f
        ttk.Label(f, text="Una scheda per stazione: ci si accorda a voce (su un'altra banda) su ruolo e orario UTC, l'app fa partire la prova all'ora giusta e poi si "
                          "scambiano le righe dei risultati.", justify="left").pack(anchor="w", padx=8, pady=(6, 2))
        # --- orologio
        c = ttk.LabelFrame(f, text="1. Orologio (UTC)")
        c.pack(fill="x", padx=8, pady=3)
        r = ttk.Frame(c); r.pack(fill="x", padx=4, pady=2)
        self.lbl_utc = tk.Label(r, text="—", font=("TkFixedFont", 13, "bold"), width=26, anchor="w")
        self.lbl_utc.pack(side="left")
        self.lbl_src = ttk.Label(r, text="")
        self.lbl_src.pack(side="left", padx=8)
        r2 = ttk.Frame(c); r2.pack(fill="x", padx=4, pady=2)
        ttk.Label(r2, text="Server NTP").pack(side="left")
        self.ntp_server = tk.StringVar(value=self.cfg.get("ntp", "pool.ntp.org"))
        ttk.Entry(r2, textvariable=self.ntp_server, width=22).pack(side="left", padx=4)
        ttk.Button(r2, text="Sincronizza NTP", command=self.sync_ntp).pack(side="left", padx=2)
        self.lbl_ntp = ttk.Label(r2, text="")
        self.lbl_ntp.pack(side="left", padx=8)
        r3 = ttk.Frame(c); r3.pack(fill="x", padx=4, pady=2)
        ttk.Label(r3, text="GPS (seriale o USB)").pack(side="left")
        self.gps_port = ttk.Combobox(r3, width=38, values=serialio_ports())
        if self.cfg.get("gps_sel"):
            self.gps_port.set(self.cfg["gps_sel"])
        self.gps_port.pack(side="left", padx=4)
        ttk.Button(r3, text="Aggiorna", width=8, command=self.refresh_gps_ports).pack(side="left")
        self.gps_baud = ttk.Combobox(r3, width=7, state="readonly", values=["4800", "9600", "19200", "38400", "57600", "115200"])
        self.gps_baud.set(str(self.cfg.get("gps_baud", "9600")))
        self.gps_baud.pack(side="left", padx=4)
        self.gps_pps = tk.BooleanVar(value=False)
        ttk.Checkbutton(r3, text="PPS sul pin DCD", variable=self.gps_pps).pack(side="left", padx=4)
        self.btn_gps = ttk.Button(r3, text="Collega GPS", command=self.toggle_gps)
        self.btn_gps.pack(side="left", padx=4)
        r3b = ttk.Frame(c); r3b.pack(fill="x", padx=4, pady=1)
        self.gps_auto = tk.BooleanVar(value=bool(self.cfg.get("gps_auto", False)))
        self.gps_reconnect = tk.BooleanVar(value=True)
        self.gps_use_cal = tk.BooleanVar(value=True)
        ttk.Checkbutton(r3b, text="Collega il GPS all'avvio", variable=self.gps_auto).pack(side="left", padx=4)
        ttk.Checkbutton(r3b, text="Riconnetti da solo", variable=self.gps_reconnect).pack(side="left", padx=4)
        ttk.Checkbutton(r3b, text="Usa il ritardo tarato", variable=self.gps_use_cal).pack(side="left", padx=4)
        ttk.Button(r3b, text="Calibra il ritardo del GPS con NTP", command=self.calibrate_gps).pack(side="left", padx=8)
        self.lbl_cal = ttk.Label(c, text=self._cal_text())
        self.lbl_cal.pack(anchor="w", padx=6)
        self.lbl_gps = ttk.Label(c, text="GPS non collegato")
        self.lbl_gps.pack(anchor="w", padx=6, pady=(0, 3))
        # --- stazioni
        s = ttk.LabelFrame(f, text="2. Le stazioni")
        s.pack(fill="x", padx=8, pady=3)
        g = ttk.Frame(s); g.pack(fill="x", padx=4, pady=2)
        self.man_pos = tk.StringVar(value=self.cfg.get("man_pos", ""))
        self.rem_call = tk.StringVar()
        self.rem_pos = tk.StringVar()
        for i, (label, var, w, hint) in enumerate((("Mia posizione se manca il GPS", self.man_pos, 24, "lat,lon oppure locatore (JN53ps)"),
                                                   ("Collega: nominativo", self.rem_call, 10, ""), ("Collega: posizione", self.rem_pos, 24, "lat,lon oppure locatore"))):
            ttk.Label(g, text=label).grid(row=0, column=2 * i, sticky="w", padx=(0, 3))
            ttk.Entry(g, textvariable=var, width=w).grid(row=0, column=2 * i + 1, padx=(0, 10))
        self.lbl_dist = ttk.Label(s, text="")
        self.lbl_dist.pack(anchor="w", padx=6, pady=(0, 3))
        # --- appuntamento
        a = ttk.LabelFrame(f, text="3. Appuntamento")
        a.pack(fill="x", padx=8, pady=3)
        r = ttk.Frame(a); r.pack(fill="x", padx=4, pady=2)
        ttk.Label(r, text="Io").pack(side="left")
        self.role = tk.StringVar(value="TX")
        ttk.Radiobutton(r, text="Trasmetto", variable=self.role, value="TX").pack(side="left", padx=4)
        ttk.Radiobutton(r, text="Ricevo", variable=self.role, value="RX").pack(side="left", padx=(0, 12))
        ttk.Label(r, text="Scheda").pack(side="left")
        self.field_board_sel = ttk.Combobox(r, width=3, state="readonly", values=["A", "B"])
        self.field_board_sel.set("A")
        self.field_board_sel.pack(side="left", padx=(3, 12))
        ttk.Label(r, text="Partenza T0 (UTC)").pack(side="left")
        self.t0_var = tk.StringVar(value="")
        ttk.Entry(r, textvariable=self.t0_var, width=21).pack(side="left", padx=4)
        ttk.Button(r, text="fra 3 min", command=lambda: self.t0_var.set(timesync.fmt_utc(int(self.clock.now()) + 180, ms=False).replace(" UTC", ""))).pack(side="left")
        r2 = ttk.Frame(a); r2.pack(fill="x", padx=4, pady=2)
        ttk.Label(r2, text="Chi riceve parte con anticipo di (s)").pack(side="left")
        self.lead_rx = tk.StringVar(value="5")
        ttk.Entry(r2, textvariable=self.lead_rx, width=4).pack(side="left", padx=(3, 12))
        ttk.Label(r2, text="Attenuatore in serie (dB)").pack(side="left")
        self.field_att = tk.StringVar(value="0")
        ttk.Entry(r2, textvariable=self.field_att, width=5).pack(side="left", padx=(3, 12))
        self.btn_prog = ttk.Button(r2, text="Programma la prova", command=self.program_run)
        self.btn_prog.pack(side="left", padx=4)
        ttk.Button(r2, text="Annulla", command=self.cancel_run).pack(side="left")
        ttk.Button(r2, text="Copia le condizioni per il collega", command=self.copy_plan).pack(side="left", padx=12)
        self.lbl_count = tk.Label(a, text="Nessun appuntamento.", font=("TkDefaultFont", 11, "bold"), anchor="w")
        self.lbl_count.pack(fill="x", padx=6, pady=(2, 4))
        ttk.Label(a, text="Modo, frequenza, potenza, pacchetto, quanti e intervallo sono quelli della scheda Misure (devono essere uguali per i due colleghi).",
                  foreground="#666666").pack(anchor="w", padx=6)
        # --- risultati
        rr = ttk.LabelFrame(f, text="4. Risultati (scambia la riga con il collega e uniscila)")
        rr.pack(fill="both", expand=True, padx=8, pady=3)
        cols = ("t0", "role", "mode", "dist", "sent", "ok", "loss", "rssi", "snr", "err", "src")
        self.ftree = ttk.Treeview(rr, columns=cols, show="headings", height=5)
        for c_, t_, w_ in (("t0", "T0 (UTC)", 150), ("role", "Ruolo", 50), ("mode", "Modo", 50), ("dist", "km", 60), ("sent", "Inviati", 60), ("ok", "Ricevuti", 65),
                           ("loss", "Perdita %", 70), ("rssi", "RSSI", 60), ("snr", "SNR", 55), ("err", "Partenza ms", 85), ("src", "Orologio", 110)):
            self.ftree.heading(c_, text=t_)
            self.ftree.column(c_, width=w_, anchor="center")
        self.ftree.pack(fill="x", padx=4, pady=3)
        b = ttk.Frame(rr); b.pack(fill="x", padx=4, pady=2)
        ttk.Button(b, text="Copia i miei dati", command=self.copy_mine).pack(side="left", padx=2)
        ttk.Button(b, text="Incolla i dati del collega…", command=self.paste_remote).pack(side="left", padx=2)
        ttk.Button(b, text="Salva CSV di rilievo", command=self.save_field_csv).pack(side="left", padx=2)
        self.f_extra = {k: tk.StringVar(value=self.cfg.get("f_" + k, "")) for k in ("percorso", "meteo", "scheda", "antenna", "note")}
        e = ttk.Frame(rr); e.pack(fill="x", padx=4, pady=2)
        for k, w in (("percorso", 12), ("meteo", 10), ("scheda", 10), ("antenna", 14), ("note", 22)):
            ttk.Label(e, text=k.capitalize()).pack(side="left")
            ttk.Entry(e, textvariable=self.f_extra[k], width=w).pack(side="left", padx=(2, 8))
        self.root.after(250, self._tick_field)
        self.refresh_gps_ports()
        if self.cfg.get("gps_auto") and self.cfg.get("gps_sel"):
            self.root.after(1500, self._auto_gps)

    # ----- orologio, NTP, GPS
    def _open_gps_serial(self, port, baud):
        import serial
        return serial.Serial(port, baud, timeout=1.0)

    def sync_ntp(self):
        server = self.ntp_server.get().strip()
        self.lbl_ntp.configure(text="… sincronizzo")
        def job():
            try:
                off, unc, srv = self.ntp_func([server])
            except Exception as e:  # noqa
                self.post(lambda: self.lbl_ntp.configure(text=f"errore: {e}"))
                return
            def done():
                self.clock.set_source("ntp", off, unc)
                self.lbl_ntp.configure(text=f"scarto {off * 1000:+.0f} ms, incertezza {unc * 1000:.0f} ms ({srv})")
            self.post(done)
        threading.Thread(target=job, daemon=True).start()

    def refresh_gps_ports(self):
        """Elenco: porte seriali e GPS Bluetooth accoppiati (letti da bluetoothctl, in un thread per non bloccare l'interfaccia)."""
        base = serialio_ports()
        self.gps_port.configure(values=base)
        def job():
            try:
                bt = [bluetooth.label(m, n) for m, n in bluetooth.list_paired()]
            except Exception:  # noqa
                bt = []
            self.post(lambda: self.gps_port.configure(values=base + bt))
        threading.Thread(target=job, daemon=True).start()

    def _cal_text(self):
        d = self.cfg.get("gps_delay_s")
        if d is None:
            return "Ritardo del GPS non tarato: l'ora GPS ha un'incertezza di ±0,4 s. Con GPS e NTP collegati, premi \"Calibra\" (con il GPS fermo)."
        return f"Ritardo del GPS tarato: {d * 1000:.0f} ms (il {self.cfg.get('gps_delay_date', '?')}); vale per questo GPS e questo collegamento."

    def toggle_gps(self):
        if self.gps is not None or self.gps_want or self.gps_connecting:
            self.gps_want = False
            self._gps_close()
            self.btn_gps.configure(text="Collega GPS")
            self.lbl_gps.configure(text="GPS non collegato")
            return
        sel = self.gps_port.get().strip()
        if not sel:
            messagebox.showinfo("GPS", "Scegli il GPS: una porta seriale (per esempio /dev/ttyACM0) oppure un GPS Bluetooth accoppiato (premi Aggiorna).")
            return
        self.gps_want = True
        self.btn_gps.configure(text="Scollega GPS")
        self._gps_connect()

    def _gps_close(self):
        if self.gps is not None:
            self.gps.stop()
            self.gps = None
        self.clock.clear_source("gps")
        self.clock.clear_source("gps-pps")

    def _gps_connect(self):
        """Apre il GPS (seriale o Bluetooth) in un thread: il Bluetooth puo' impiegare diversi secondi."""
        if self.gps_connecting:
            return
        kind, ident = bluetooth.parse_choice(self.gps_port.get())
        try:
            baud = int(self.gps_baud.get())
        except ValueError:
            baud = 9600
        pps = self.gps_pps.get()
        self.gps_connecting = True
        self.gps_last_try = time.time()
        self.lbl_gps.configure(text="GPS Bluetooth: collego (puo' richiedere alcuni secondi)…" if kind == "bt" else f"GPS: apro {ident}…")
        def job():
            try:
                if kind == "bt":
                    ser, desc = self.bt_opener(ident)
                    g = timesync.GpsReader(lambda: ser, baud=baud, pps=False)
                else:
                    ser, desc = None, f"{ident} a {baud} baud"
                    g = timesync.GpsReader(lambda: self.gps_opener(ident, baud), baud=baud, pps=pps)
                g.start()
            except Exception as e:  # noqa
                msg = str(e)
                def fail():
                    self.gps_connecting = False
                    if self.gps_want:
                        self.lbl_gps.configure(text=f"GPS: non collegato ({msg})" + (" - riprovo da solo" if self.gps_reconnect.get() else ""))
                        if not self.gps_reconnect.get():
                            self.gps_want = False
                            self.btn_gps.configure(text="Collega GPS")
                self.post(fail)
                return
            def ok():
                self.gps_connecting = False
                if not self.gps_want:           # l'utente ha premuto Scollega nel frattempo
                    g.stop()
                    return
                if self.gps_use_cal.get() and self.cfg.get("gps_delay_s") is not None:
                    g.delay_s, g.calibrated = float(self.cfg["gps_delay_s"]), True
                self.gps = g
                self.gps_note = desc
                self.lbl_gps.configure(text=f"GPS collegato: {desc}: attendo le frasi NMEA…")
            self.post(ok)
        threading.Thread(target=job, daemon=True).start()

    def _auto_gps(self):
        if self.gps is None and not self.gps_want and not self.gps_connecting and self.gps_port.get().strip():
            self.gps_want = True
            self.btn_gps.configure(text="Scollega GPS")
            self._gps_connect()

    def calibrate_gps(self):
        """Tara il ritardo della frase NMEA: scarto dell'NTP meno scarto grezzo del GPS (docs/gps-tempo.md)."""
        if self.gps is None:
            messagebox.showinfo("Calibrazione", "Collega prima il GPS e aspetta il fix.")
            return
        server = self.ntp_server.get().strip()
        g = self.gps
        self.lbl_cal.configure(text="Calibrazione: sincronizzo l'NTP…")
        def job():
            try:
                off, unc, srv = self.ntp_func([server])
                delay, spread, n = timesync.calibrate_gps_delay(g, off, unc)
            except (OSError, ValueError) as e:
                msg = str(e)
                self.post(lambda: self.lbl_cal.configure(text=f"Calibrazione non riuscita: {msg}"))
                return
            def done():
                self.clock.set_source("ntp", off, unc)
                if self.gps is g:
                    g.delay_s, g.calibrated = delay, True
                self.cfg["gps_delay_s"] = delay
                self.cfg["gps_delay_date"] = time.strftime("%Y-%m-%d %H:%M")
                self.lbl_cal.configure(text=self._cal_text() + f" Dispersione ±{spread * 1000:.0f} ms su {n} frasi, NTP ±{unc * 1000:.0f} ms.")
                self.set_status(f"Ritardo del GPS tarato: {delay * 1000:.0f} ms")
            self.post(done)
        threading.Thread(target=job, daemon=True).start()

    def my_position(self):
        """(lat, lon, origine) dal GPS se ha il fix, altrimenti dalla posizione scritta a mano; None se manca."""
        if self.gps is not None:
            p = self.gps.position()
            if p:
                return p[0], p[1], "GPS"
        pos = self._parse_pos(self.man_pos.get())
        return (pos[0], pos[1], "manuale") if pos else None

    @staticmethod
    def _parse_pos(s):
        s = s.strip()
        if not s:
            return None
        try:
            if "," in s:
                a, b = s.split(",", 1)
                return float(a), float(b)
            return geo.from_maidenhead(s)
        except ValueError:
            return None

    def _tick_field(self):
        # riconnessione automatica del GPS
        if self.gps_want and not self.gps_connecting and (self.gps is None or self.gps.error) and self.gps_reconnect.get():
            if self.gps is not None and self.gps.error:
                self.lbl_gps.configure(text=f"GPS: collegamento perso ({self.gps.error}): riconnessione automatica…")
                self._gps_close()
                self.gps_last_try = time.time()
            elif time.time() - self.gps_last_try >= self.gps_retry_s:
                self._gps_connect()
        # sorgenti dell'orologio dal GPS
        if self.gps is not None:
            o = self.gps.clock_offset()
            self.clock.clear_source("gps"); self.clock.clear_source("gps-pps")
            if o:
                self.clock.set_source("gps-pps" if o[2] else "gps", o[0], o[1])
            g = self.gps
            if g.error:
                self.lbl_gps.configure(text=f"GPS: errore {g.error}")
            else:
                pos = g.position()
                loc = geo.maidenhead(pos[0], pos[1]) if pos else "—"
                note = ""
                if g.rollover:
                    note += " | data GPS corretta (rollover di 1024 settimane)"
                if g.rejected:
                    note += f" | {g.rejected} ore GPS scartate (data non credibile: {timesync.fmt_utc(g.last_rejected, ms=False)})"
                self.lbl_gps.configure(text=(f"GPS: {'FIX' if g.fix else 'nessun fix'}, {g.sats} satelliti, HDOP {g.hdop if g.hdop is not None else '—'}, "
                                             f"{pos[0]:.5f}, {pos[1]:.5f} ({loc}), {g.lines} frasi, orologio da {'PPS' if o and o[2] else ('NMEA con ritardo tarato' if g.calibrated else 'NMEA')}" if pos else
                                             f"GPS: {'FIX' if g.fix else 'nessun fix'}, {g.sats} satelliti, {g.lines} frasi ricevute") + note)
        info = self.clock.info()
        self.lbl_utc.configure(text=timesync.fmt_utc(info["utc"], ms=False))
        diff = self.clock.differences()
        extra = ""
        if ("gps", "ntp") in diff or ("gps-pps", "ntp") in diff:
            d = diff.get(("gps", "ntp"), diff.get(("gps-pps", "ntp")))
            extra = f"  |  GPS-NTP {d * 1000:+.0f} ms"
        self.lbl_src.configure(text=f"sorgente: {info['sorgente']}, incertezza ±{info['incertezza_s'] * 1000:.0f} ms{extra}")
        # distanza fra le stazioni
        me, rem = self.my_position(), self._parse_pos(self.rem_pos.get())
        if me and rem:
            self.lbl_dist.configure(text=f"Distanza {geo.haversine_km(me[0], me[1], rem[0], rem[1]):.2f} km, direzione {geo.bearing_deg(me[0], me[1], rem[0], rem[1]):.0f}° "
                                         f"(la mia posizione: {me[2]}, {geo.maidenhead(me[0], me[1])})")
        elif me:
            self.lbl_dist.configure(text=f"Mia posizione: {me[0]:.5f}, {me[1]:.5f} ({geo.maidenhead(me[0], me[1])}, da {me[2]}). Manca la posizione del collega.")
        else:
            self.lbl_dist.configure(text="Manca la mia posizione (collega il GPS o scrivila a mano).")
        # conto alla rovescia
        s = self.sched
        if s is not None:
            rest = s["start"] - self.clock.now()
            if s["state"] == "attesa":
                self.lbl_count.configure(text=f"{'Ricevo' if s['role'] == 'RX' else 'Trasmetto'}: partenza fra {max(0.0, rest):.1f} s (T0 {timesync.fmt_utc(s['t0'], ms=False)})")
            elif s["state"] == "in corso":
                self.lbl_count.configure(text="Prova in corso…")
        self.root.after(250, self._tick_field)

    # ----- appuntamento
    def field_board(self):
        a, b = self.pa.board, self.pb.board
        sel = self.field_board_sel.get()
        board = a if sel == "A" else b
        return board if board is not None else (a or b)

    def plan_text(self):
        p = self._params()
        if not p:
            return ""
        return (f"PROVA VoLoRa: T0 {self.t0_var.get().strip()} UTC, modo {p['code']}, {p['freq']} MHz, {p['power']} dBm, pacchetto {p['payload']} B, "
                f"{p['count']} pacchetti ogni {p['interval']} ms. Chi riceve parte {self.lead_rx.get()} s prima.")

    def copy_plan(self):
        txt = self.plan_text()
        if txt:
            self.root.clipboard_clear(); self.root.clipboard_append(txt)
            self.set_status("Condizioni copiate: " + txt)

    def program_run(self):
        if self.sched is not None and self.sched["state"] != "fine":
            self.set_status("C'e' gia' un appuntamento: Annulla prima.")
            return
        board, p = self.field_board(), self._params()
        c = self.call.get().strip().upper()
        if board is None:
            messagebox.showinfo("Scheda", "Collega prima la scheda (scheda Misure).")
            return
        if not p or not c:
            self.set_status("Scrivi il nominativo (scheda Misure) e controlla i parametri.")
            return
        try:
            t0 = timesync.parse_utc(self.t0_var.get())
            lead = float(self.lead_rx.get())
            att = float(self.field_att.get() or 0)
        except ValueError:
            messagebox.showwarning("Appuntamento", "Controlla T0 (UTC, per esempio 2026-11-22 10:30:00 oppure 10:30:00), l'anticipo e l'attenuatore.")
            return
        role = self.role.get()
        plan = timesync.plan_run(t0, p["count"], p["interval"], lead_rx=lead)
        start = plan["rx_start"] if role == "RX" else plan["tx_start"]
        if start - self.clock.now() < 5:
            messagebox.showwarning("Appuntamento", "L'orario e' troppo vicino o gia' passato: servono almeno 5 secondi per configurare la scheda.")
            return
        self.sched_stop.clear()
        self.sched = {"state": "attesa", "role": role, "t0": t0, "start": start}
        pos = self.my_position()
        info0 = self.clock.info()
        self.set_status(f"Prova programmata: {'ricezione' if role == 'RX' else 'trasmissione'} alle {timesync.fmt_utc(start, ms=False)}.")
        def job():
            try:
                runner.configure([board], p["code"], p["power"], p["freq"], p["payload"], c)
                if role == "RX":
                    cmd, prefix, timeout = f"RX {plan['rx_window_s']}", "RXSUM", plan["rx_window_s"] + 30
                else:
                    cmd, prefix, timeout = f"TX {p['count']} {p['interval']}", "TXSUM", p["count"] * p["interval"] / 1000.0 + 30
                waiter = board.expect(prefix, timeout)
                err = timesync.wait_until(self.clock, start, stop=self.sched_stop)
                if err is None:
                    waiter.cancel()
                    self.post(lambda: self._sched_end("Appuntamento annullato."))
                    return
                inf = self.clock.info()
                board.send(cmd)
                self.sched["state"] = "in corso"
                line = waiter.wait()
                if line is None or line.startswith("ERR"):
                    self.post(lambda: self._sched_end(f"Prova non riuscita: {line or 'nessuna risposta della scheda'}"))
                    return
                kind, d = core.parse_line(line)
                run = {"t0": t0, "role": role, "mode": p["code"], "freq_mhz": p["freq"], "power_dbm": p["power"], "att_db": att, "my_call": c,
                       "clock_src": inf["sorgente"], "clock_unc_s": inf["incertezza_s"], "start_err_ms": err * 1000.0}
                if pos:
                    run.update(my_lat=pos[0], my_lon=pos[1], my_loc=geo.maidenhead(pos[0], pos[1]))
                if self.gps is not None and self.gps.alt is not None:
                    run["my_alt"] = self.gps.alt
                if role == "TX":
                    run["sent"] = int(d.get("sent", 0))
                    run["toa_mean_us"], run["toa_calc_us"] = d.get("toa_mean_us"), d.get("calc_us")
                else:
                    run.update(rx_ok=int(d.get("ok", 0)), rx_bad=int(d.get("bad", 0)), rssi=d.get("rssi"), snr=d.get("snr"), fei_hz=d.get("fei_hz"))
                self.post(lambda: (self.add_field_run(run), self._sched_end("Prova conclusa.")))
            except runner.RunError as e:
                self.post(lambda: self._sched_end(f"Errore: {e}"))
        threading.Thread(target=job, daemon=True).start()

    def _sched_end(self, msg):
        self.sched = None
        self.lbl_count.configure(text=msg)
        self.set_status(msg)

    def cancel_run(self):
        if self.sched is not None:
            self.sched_stop.set()
            for b in self.boards():
                b.send("STOP")

    # ----- risultati
    def add_field_run(self, run):
        self.field_runs.append(run)
        self.ftree.insert("", "end", iid=str(len(self.field_runs) - 1), values=self._field_values(run))
        self.ftree.yview_moveto(1)

    @staticmethod
    def _field_values(r):
        def f(v, nd=1):
            return "" if v in (None, "") or (isinstance(v, float) and v != v) else (f"{v:.{nd}f}" if isinstance(v, float) else v)
        return (timesync.fmt_utc(r["t0"], ms=False).replace(" UTC", ""), r["role"], r["mode"], f(r.get("distance_km"), 2), f(r.get("sent")), f(r.get("rx_ok")),
                f(r.get("loss_pct")), f(r.get("rssi")), f(r.get("snr")), f(r.get("start_err_ms"), 0), r.get("clock_src", ""))

    def _selected_run(self):
        sel = self.ftree.selection()
        i = int(sel[0]) if sel else len(self.field_runs) - 1
        return i if 0 <= i < len(self.field_runs) else None

    def copy_mine(self):
        i = self._selected_run()
        if i is None:
            self.set_status("Non c'e' ancora nessuna prova.")
            return
        txt = field.export_line(self.field_runs[i])
        self.root.clipboard_clear(); self.root.clipboard_append(txt)
        self.set_status("Copiato: " + txt)

    def paste_remote(self):
        i = self._selected_run()
        if i is None:
            self.set_status("Non c'e' ancora nessuna prova da unire.")
            return
        win = tk.Toplevel(self.root)
        win.title("Dati del collega")
        ttk.Label(win, text="Incolla qui la riga che comincia con VOLORA-PROVA:").pack(anchor="w", padx=8, pady=4)
        box = tk.Text(win, width=100, height=5)
        box.pack(padx=8)
        try:
            box.insert("1.0", self.root.clipboard_get())
        except tk.TclError:
            pass
        def ok():
            self.merge_remote_text(box.get("1.0", "end"), i)
            win.destroy()
        ttk.Button(win, text="Unisci", command=ok).pack(pady=6)

    def merge_remote_text(self, text, i=None):
        i = self._selected_run() if i is None else i
        try:
            rem = field.import_line(text)
        except ValueError as e:
            messagebox.showwarning("Dati del collega", str(e))
            return None
        merged, warn = field.merge(self.field_runs[i], rem)
        self.field_runs[i] = merged
        self.ftree.item(str(i), values=self._field_values(merged))
        self.rem_call.set(rem["call"])
        if "lat" in rem:
            self.rem_pos.set(f"{rem['lat']:.5f},{rem['lon']:.5f}")
        elif rem.get("loc"):
            self.rem_pos.set(rem["loc"])
        self.set_status("Dati uniti: " + (f"perdita {merged['loss_pct']} %, " if "loss_pct" in merged else "") + (f"distanza {merged['distance_km']:.2f} km" if "distance_km" in merged else "senza distanza"))
        if warn:
            messagebox.showwarning("Controlla", "\n".join(warn))
        return merged, warn

    def save_field_csv(self):
        if not self.field_runs:
            self.set_status("Non ci sono ancora prove.")
            return
        p = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"{time.strftime('%Y-%m-%d')}-{core.safe_name(self.call.get() or 'campo')}-campo.csv",
                                         filetypes=[("CSV", "*.csv")])
        if not p:
            return
        x = {k: v.get() for k, v in self.f_extra.items()}
        import csv as _csv
        with open(p, "w", newline="", encoding="utf-8") as fh:
            w = _csv.DictWriter(fh, field.RILIEVO_FIELDS)
            w.writeheader()
            for r in self.field_runs:
                extra = {"percorso": x["percorso"], "meteo": x["meteo"], "note": x["note"]}
                mine_tx = r["role"] == "TX"
                extra["scheda_A" if mine_tx else "scheda_B"] = x["scheda"]
                extra["antenna_A" if mine_tx else "antenna_B"] = x["antenna"]
                w.writerow(field.to_rilievo_row(r, extra))
        self.set_status(f"Salvato {p}")

    def _build_images(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="Immagini")
        ttk.Label(f, text="Immagini fittizie per le prove di trasferimento (protocollo immagini, docs/protocollo-immagini.md).\n"
                          "L'invio via radio non c'è ancora (fase 3): qui si preparano i file e si vede il tempo stimato per ogni gradino.",
                  justify="left").pack(anchor="w", padx=8, pady=6)
        r = ttk.Frame(f); r.pack(fill="x", padx=8)
        self.img_kind = tk.StringVar(value="blob")
        for v, t in (("blob", "Blocco di prova (byte)"), ("png", "Schema di prova PNG"), ("jpg", "JPEG progressivo (serve Pillow)")):
            ttk.Radiobutton(r, text=t, variable=self.img_kind, value=v).pack(side="left", padx=4)
        r2 = ttk.Frame(f); r2.pack(fill="x", padx=8, pady=6)
        self.img_size = tk.StringVar(value="5000"); self.img_w = tk.StringVar(value="160"); self.img_h = tk.StringVar(value="120")
        for label, var, w in (("Dimensione (byte)", self.img_size, 8), ("Larghezza px", self.img_w, 6), ("Altezza px", self.img_h, 6)):
            ttk.Label(r2, text=label).pack(side="left")
            ttk.Entry(r2, textvariable=var, width=w).pack(side="left", padx=(2, 10))
        ttk.Button(r2, text="Genera e salva", command=self.gen_image).pack(side="left", padx=4)
        ttk.Label(f, text="Scheda radio per la stima:").pack(anchor="w", padx=8)
        self.img_chip = ttk.Combobox(f, state="readonly", values=["SX1278", "SX1262"], width=10)
        self.img_chip.current(0); self.img_chip.pack(anchor="w", padx=8)
        self.img_info = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.img_info).pack(anchor="w", padx=8, pady=4)
        self.est = ttk.Treeview(f, columns=("g", "t"), show="headings", height=15)
        self.est.heading("g", text="Gradino"); self.est.heading("t", text="Tempo stimato")
        self.est.column("g", width=220); self.est.column("t", width=140, anchor="center")
        self.est.pack(anchor="w", padx=8, pady=4)

    def _build_github(self, nb):
        f = ttk.Frame(nb)
        self.tab_github = f
        nb.add(f, text="GitHub")
        ttk.Label(f, text="Invio dei risultati. Il pulsante 1 salva CSV e note in una cartella; poi scegli 2a o 2b.", justify="left").pack(anchor="w", padx=8, pady=6)
        g = ttk.Frame(f); g.pack(fill="x", padx=8)
        self.gh_repo = tk.StringVar(value=self.cfg.get("repo", core.DEFAULT_REPO))
        self.gh_token = tk.StringVar(value=self.cfg.get("token", ""))
        self.gh_remember = tk.BooleanVar(value=bool(self.cfg.get("token")))
        self.gh_a = tk.StringVar(value=self.cfg.get("board_a", "")); self.gh_b = tk.StringVar(value=self.cfg.get("board_b", ""))
        for i, (label, var, show) in enumerate((("Repository", self.gh_repo, ""), ("Scheda A (tipo)", self.gh_a, ""), ("Scheda B (tipo)", self.gh_b, ""),
                                                ("Token (facoltativo)", self.gh_token, "•"))):
            ttk.Label(g, text=label).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Entry(g, textvariable=var, width=44, show=show).grid(row=i, column=1, sticky="w", padx=6)
        ttk.Checkbutton(g, text="Ricorda il token su questo computer (testo semplice, file con permessi ristretti)", variable=self.gh_remember).grid(row=4, column=1, sticky="w")
        ttk.Label(f, text="Note per chi legge (strumenti, antenna, meteo, cosa non ha funzionato):").pack(anchor="w", padx=8, pady=(8, 0))
        self.notes = tk.Text(f, height=6, width=90)
        self.notes.pack(anchor="w", padx=8, pady=2)
        b = ttk.Frame(f); b.pack(anchor="w", padx=8, pady=6)
        ttk.Button(b, text="1. Salva CSV e note", command=self.save_bundle).pack(side="left", padx=2)
        ttk.Button(b, text="2a. Apri segnalazione su GitHub (senza token)", command=self.open_issue).pack(side="left", padx=2)
        ttk.Button(b, text="2b. Carica con il token (ramo e PR)", command=self.upload).pack(side="left", padx=2)
        ttk.Label(f, text="2a apre la pagina 'nuova segnalazione' già compilata: allega tu il CSV (trascinalo nella casella).\n"
                          "2b serve un token con permesso di scrittura sul repository: crea un ramo, carica i file in docs/misure/ e apre una richiesta di modifica.\n"
                          "Se non sei collaboratore usa 2a.", justify="left").pack(anchor="w", padx=8)

    def _build_help(self, nb):
        f = ttk.Frame(nb)
        nb.add(f, text="Aiuto")
        txt = ("REGOLE FERME\n- Antenna o carico da 50 ohm collegati prima di alimentare o trasmettere.\n- Solo con il proprio nominativo.\n"
               "- Il firmware di misura non è il V3.\n\nTASTI RAPIDI\n")
        txt += "\n".join(f"{k:8} {t:14} {h}" for k, t, h in SHORTCUTS)
        txt += ("\n\nUSO\n1. Collega le schede A e B (porte seriali, 921600 baud) e premi F1.\n2. Scrivi il nominativo e premi F2.\n"
                "3. Scegli il modo e premi F3.\n4. Metti l'attenuazione misurata col NanoVNA e premi F4: una riga di risultato.\n"
                "5. F8 salva il CSV; scheda GitHub per inviarlo.\n\nSenza schede: avvia con --simulate (schede finte).")
        t = tk.Text(f, wrap="word"); t.insert("1.0", txt); t.configure(state="disabled"); t.pack(fill="both", expand=True, padx=8, pady=8)

    # ----- tasti -----
    def _bind_keys(self):
        r = self.root
        for i, key in enumerate(("F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9"), 1):
            r.bind(f"<{key}>", lambda e, k=key: self.action(k))
        r.bind("<Escape>", lambda e: self.action("Esc"))
        r.bind("<Control-l>", lambda e: self.action("Ctrl+L"))

    def action(self, key):
        {"F1": self.a_info, "F2": self.a_call, "F3": self.a_apply, "F4": self.a_measure, "F5": self.a_tx, "F6": self.a_rx, "F7": self.a_cw,
         "Esc": self.a_stop, "F8": self.save_csv, "F9": lambda: self.nb.select(self.tab_github), "Ctrl+L": self.a_clear}[key]()

    # ----- schede -----
    def boards(self):
        return [p.board for p in (self.pa, self.pb) if p.board is not None]

    def connect(self, pane, port):
        if not port or port == "(finta)":
            messagebox.showinfo("Porta", "Scegli prima la porta seriale della scheda (l'elenco si aggiorna con il pulsante ⟳).")
            return
        pane.set_state("… apro la porta", "#b8860b")
        self.root.update_idletasks()
        try:
            board = serialio.SerialBoard(pane.name, port)
        except Exception as e:  # noqa
            pane.set_state("✗ errore", "#c0392b")
            pane.show("err", f"[sistema] non riesco ad aprire {port}: {e}")
            messagebox.showerror("Porta", f"Non riesco ad aprire {port}: {e}\n(serve pyserial: pip install pyserial; su Linux serve anche il gruppo dialout)")
            return
        pane.board = board
        pane.btn.configure(text="Scollega")
        pane.set_state("● collegata", "#1b8a3c")
        board.inbox.put(("sys", f"[sistema] collegata a {port} a 921600 baud: la scheda si riavvia, attendo l'avvio…"))
        self.set_status(f"Scheda {pane.name} collegata su {port}. Chiedo INFO tra un attimo.")
        # l'apertura della porta riavvia la scheda: dopo l'avvio si chiede INFO, cosi' compaiono subito il chip e la versione
        self.root.after(1800, lambda p=pane, b=board: b.send("INFO") if p.board is b and b.connected else None)

    def disconnect(self, pane):
        if pane.board:
            pane.board.inbox.put(("sys", "[sistema] scollegata"))
            pane.board.close()
        pane.board = None
        pane.btn.configure(text="Collega")
        pane.set_state("○ scollegata", "#888888")
        pane.chip.configure(text="—")
        self.set_status(f"Scheda {pane.name} scollegata.")

    def set_status(self, s):
        self.status.set(s)

    def post(self, fn):
        self.ui.put(fn)

    def _pump(self):
        while True:
            try:
                self.ui.get_nowait()()
            except queue.Empty:
                break
        for pane in (self.pa, self.pb):
            if pane.board is None:
                continue
            n = 0
            while n < 200:
                try:
                    kind, text = pane.board.inbox.get_nowait()
                except queue.Empty:
                    break
                pane.show(kind, text)
                if kind == "sys" and text.startswith("porta chiusa"):
                    pane.set_state("✗ porta persa", "#c0392b")
                    self.set_status(f"Scheda {pane.name}: la porta si e' chiusa (cavo scollegato?).")
                if kind == "rx" and text.startswith(("INFO", "misura ")):
                    parts = text.split()
                    for chip in ("SX1278", "SX1262"):
                        if chip in parts:
                            pane.board.chip = chip
                            pane.chip.configure(text=chip)
                n += 1
        self.root.after(80, self._pump)

    # ----- azioni -----
    def _need(self, n=1):
        b = self.boards()
        if len(b) < n:
            messagebox.showinfo("Schede", "Collega prima " + ("le due schede." if n == 2 else "una scheda."))
            return None
        return b

    def a_info(self):
        for b in self.boards():
            b.send("INFO")

    def a_call(self):
        c = self.call.get().strip().upper()
        if not (3 <= len(c) <= 8 and c.isalnum()):
            messagebox.showwarning("Nominativo", "Il nominativo deve avere da 3 a 8 lettere o cifre (il tuo, senza /).")
            return
        self.cfg["call"] = c
        for b in self.boards():
            b.send(f"CALL {c}")

    def _params(self):
        try:
            return dict(code=self.mode.get().split()[0], freq=float(self.vars["freq"].get()), power=int(self.vars["power"].get()),
                        payload=int(self.vars["payload"].get()), count=int(self.vars["count"].get()), interval=int(self.vars["interval"].get()),
                        att=float(self.vars["att"].get()))
        except ValueError:
            messagebox.showwarning("Parametri", "Controlla i campi numerici.")
            return None

    def _threaded(self, fn):
        if self.busy.is_set():
            self.set_status("Una prova è già in corso: Esc per fermarla.")
            return
        self.busy.set()
        def run():
            try:
                fn()
            except runner.RunError as e:
                self.post(lambda: self.set_status(f"Errore: {e}"))
            finally:
                self.busy.clear()
        threading.Thread(target=run, daemon=True).start()

    def a_apply(self):
        b, p = self._need(2), self._params()
        c = self.call.get().strip().upper()
        if not b or not p or not c:
            if not c:
                self.set_status("Scrivi il nominativo.")
            return
        self._threaded(lambda: (runner.configure(b, p["code"], p["power"], p["freq"], p["payload"], c),
                                self.post(lambda: self.set_status(f"Modo {p['code']} impostato su entrambe."))))

    def a_measure(self):
        b, p = self._need(2), self._params()
        c = self.call.get().strip().upper()
        if not b or not p or not c:
            return
        tx, rx = (self.pa.board, self.pb.board) if self.txsel.get() == "A" else (self.pb.board, self.pa.board)
        def job():
            self.post(lambda: self.set_status(f"Misura {p['code']} a {p['att']:g} dB in corso…"))
            runner.configure([tx, rx], p["code"], p["power"], p["freq"], p["payload"], c)
            if self.fake_link is not None:
                self.fake_link.att_db = p["att"]
            row = runner.run_point(tx, rx, p["code"], p["count"], p["interval"], p["power"], p["att"], p["freq"])
            self.post(lambda: self.add_row(row))
        self._threaded(job)

    def add_row(self, row):
        self.rows.append(row)
        self.tree.insert("", "end", values=(row["mode"], f"{row['att_db']:g}", f"{row['p_rx_dbm']:g}", row["sent"], row["rx_ok"], f"{row['loss_pct']:g}",
                                           f"{row['rssi']:.1f}", f"{row['snr']:.1f}", f"{row['fei_hz']:.0f}", f"{row['toa_mean_us']:.0f}/{row['toa_calc_us']:.0f}"))
        self.tree.yview_moveto(1)
        self.set_status(f"{row['mode']} a {row['att_db']:g} dB: {row['rx_ok']}/{row['sent']} ricevuti, perdita {row['loss_pct']:g} %.")

    def _tx_rx(self):
        a, b = self.pa.board, self.pb.board
        if a is not None and b is None:       # una scheda sola: fa da trasmettitore e da ricevitore, a seconda del tasto
            return a, a
        if b is not None and a is None:
            return b, b
        if self.txsel.get() == "A":
            return self.pa.board, self.pb.board
        return self.pb.board, self.pa.board

    def a_tx(self):
        if not self._need(1):
            return
        p = self._params()
        tx, _ = self._tx_rx()
        if p and tx:
            tx.send(f"TX {p['count']} {p['interval']}")

    def a_rx(self):
        if not self._need(1):
            return
        _, rx = self._tx_rx()
        if rx:
            rx.send("RX 60")

    def a_cw(self):
        tx, _ = self._tx_rx()
        if tx:
            tx.send("CW 10")

    def a_stop(self):
        for b in self.boards():
            b.send("STOP")
        self.set_status("STOP mandato.")

    def a_clear(self):
        self.pa.clear(); self.pb.clear()

    # ----- risultati e GitHub -----
    def save_csv(self):
        if not self.rows:
            self.set_status("Non ci sono ancora risultati.")
            return None
        p = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"{time.strftime('%Y-%m-%d')}-{core.safe_name(self.call.get() or 'misure')}.csv",
                                         filetypes=[("CSV", "*.csv")])
        if p:
            core.save_csv(p, self.rows)
            self.set_status(f"Salvato {p}")
        return p

    def _bundle(self):
        call = (self.call.get() or "N0CALL").strip().upper()
        stem = f"{time.strftime('%Y-%m-%d')}-{core.safe_name(call)}"
        md = core.results_markdown(self.rows, call, self.gh_a.get() or "?", self.gh_b.get() or "?", "misura 0.1.0", self.notes.get("1.0", "end").strip())
        import io, csv as _csv
        buf = io.StringIO()
        w = _csv.DictWriter(buf, core.FIELDS); w.writeheader()
        for r in self.rows:
            w.writerow({k: r.get(k, "") for k in core.FIELDS})
        return stem, call, md, buf.getvalue().encode()

    def save_bundle(self):
        if not self.rows:
            self.set_status("Non ci sono ancora risultati.")
            return
        d = filedialog.askdirectory(title="Cartella dove salvare CSV e note")
        if not d:
            return
        stem, call, md, csvb = self._bundle()
        open(os.path.join(d, stem + ".csv"), "wb").write(csvb)
        open(os.path.join(d, stem + ".md"), "w", encoding="utf-8").write(md)
        self.set_status(f"Salvati {stem}.csv e {stem}.md in {d}")

    def open_issue(self):
        if not self.rows:
            self.set_status("Non ci sono ancora risultati.")
            return
        stem, call, md, _ = self._bundle()
        url = core.issue_url(self.gh_repo.get().strip(), f"Misure - {call} - {time.strftime('%Y-%m-%d')}", md)
        webbrowser.open(url)
        self.set_status("Aperta la pagina su GitHub: allega il CSV e invia.")

    def upload(self):
        if not self.rows:
            self.set_status("Non ci sono ancora risultati.")
            return
        token = self.gh_token.get().strip()
        if not token:
            messagebox.showinfo("Token", "Serve un token con permesso di scrittura sul repository. Se non lo hai usa 2a.")
            return
        stem, call, md, csvb = self._bundle()
        repo = self.gh_repo.get().strip()
        def job():
            try:
                url = core.upload_to_github(token, repo, "main", {stem + ".csv": csvb, stem + ".md": md.encode()}, call, core.urllib_http)
                self.post(lambda: (self.set_status(f"Caricato: {url}"), webbrowser.open(url)))
            except Exception as e:  # noqa
                self.post(lambda: messagebox.showerror("GitHub", str(e)))
        threading.Thread(target=job, daemon=True).start()
        self.set_status("Caricamento su GitHub in corso…")

    def gen_image(self):
        kind = self.img_kind.get()
        try:
            size, w, h = int(self.img_size.get()), int(self.img_w.get()), int(self.img_h.get())
            if kind == "blob":
                data, ext = core.make_blob(size, seed=size), "bin"
            elif kind == "png":
                data, ext = core.make_test_png(w, h), "png"
            else:
                data, ext = core.make_test_jpeg(w, h), "jpg"
                if data is None:
                    messagebox.showinfo("JPEG", "Serve Pillow: pip install pillow")
                    return
        except ValueError as e:
            messagebox.showwarning("Immagini", str(e))
            return
        name = f"prova-{kind}-{len(data)}B.{ext}"
        folder = os.path.join(os.path.expanduser("~"), "volora-immagini")
        os.makedirs(folder, exist_ok=True)
        open(os.path.join(folder, name), "wb").write(data)
        self.img_info.set(f"Creato {os.path.join(folder, name)}: {len(data)} byte")
        for i in self.est.get_children():
            self.est.delete(i)
        for g, t in core.estimate_rows(len(data), self.img_chip.get()):
            self.est.insert("", "end", values=(g, t))

    def close(self):
        core.save_config({**self.cfg, "call": self.call.get(), "repo": self.gh_repo.get(), "board_a": self.gh_a.get(), "board_b": self.gh_b.get(),
                          "token": self.gh_token.get(), "ntp": self.ntp_server.get(), "man_pos": self.man_pos.get(),
                          "gps_sel": self.gps_port.get(), "gps_auto": self.gps_auto.get(), "gps_baud": self.gps_baud.get(),
                          **{"f_" + k: v.get() for k, v in self.f_extra.items()}}, self.gh_remember.get())
        if self.gps is not None:
            self.gps.stop()
        for b in self.boards():
            b.close()
        self.root.destroy()


def main(simulate=False):
    root = tk.Tk()
    App(root, simulate)
    root.mainloop()
