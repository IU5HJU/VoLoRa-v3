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
print("interfaccia: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
