"""Interfaccia grafica (Tkinter): due monitor seriali, tasti rapidi, misure, risultati, immagini di prova e invio su GitHub."""
import os
import queue
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import __version__, core, runner, serialio

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
        ttk.Button(top, text="⟳", width=3, command=self.refresh).pack(side="left", padx=2)
        self.btn = ttk.Button(top, text="Collega", command=self.toggle)
        self.btn.pack(side="left", padx=2)
        self.state = tk.Label(top, text="○ scollegata", fg="#888888", font=("TkDefaultFont", 9, "bold"))
        self.state.pack(side="left", padx=(8, 2))
        self.chip = ttk.Label(top, text="—")
        self.chip.pack(side="left", padx=4)
        self.log = tk.Text(self, height=16, width=58, wrap="none", state="disabled", font=("TkFixedFont", 9))
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

        self._build_images(nb)
        self._build_github(nb)
        self._build_help(nb)

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
         "Esc": self.a_stop, "F8": self.save_csv, "F9": lambda: self.nb.select(2), "Ctrl+L": self.a_clear}[key]()

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
                          "token": self.gh_token.get()}, self.gh_remember.get())
        for b in self.boards():
            b.close()
        self.root.destroy()


def main(simulate=False):
    root = tk.Tk()
    App(root, simulate)
    root.mainloop()
