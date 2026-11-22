"""Collegamento automatico a un GPS Bluetooth (profilo seriale RFCOMM): elenco dei dispositivi accoppiati, socket diretto o ponte con il Python di
sistema. Niente `rfcomm`, niente `sudo`, niente terminali. Provato con socket e processi finti (tests/app/test_bluetooth.py): il Bluetooth vero no."""
import errno
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading

MAC_RE = re.compile(r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}")
CHANNELS = (1, 2, 3, 4, 5)
PREFIX = "Bluetooth: "


def list_paired(run=subprocess.run):
    """[(indirizzo, nome)] dei dispositivi Bluetooth noti a BlueZ (accoppiati se `bluetoothctl devices Paired` esiste)."""
    r = None
    for args in (["bluetoothctl", "devices", "Paired"], ["bluetoothctl", "devices"]):
        try:
            r = run(args, capture_output=True, text=True, timeout=4)
        except (OSError, subprocess.TimeoutExpired):
            return []
        if r.returncode == 0 and "Device" in r.stdout:
            break
    else:
        return []
    out = []
    for line in r.stdout.splitlines():
        m = re.match(r"Device\s+(\S+)\s+(.*)", line.strip())
        if m and MAC_RE.fullmatch(m.group(1)):
            out.append((m.group(1).upper(), m.group(2)))
    return out


def label(mac, name):
    return f"{PREFIX}{name} ({mac})"


def parse_choice(text):
    """('bt', indirizzo) per una voce Bluetooth, ('serial', porta) per il resto, (None, '') se vuota."""
    text = text.strip()
    if not text:
        return None, ""
    if text.startswith(PREFIX) or text.lower().startswith("bt:"):
        m = MAC_RE.search(text)
        if m:
            return "bt", m.group(0).upper()
    return "serial", text


class BtSerial:
    """Aspetto di una seriale (readline, close, cd) su un socket RFCOMM."""
    cd = False

    def __init__(self, sock):
        self.sock = sock
        self.buf = b""

    def readline(self):
        while b"\n" not in self.buf:
            try:
                data = self.sock.recv(1024)
            except socket.timeout:
                return b""
            if not data:
                raise OSError("collegamento Bluetooth chiuso dal GPS")
            self.buf += data
        line, _, self.buf = self.buf.partition(b"\n")
        return line + b"\n"

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def have_native():
    return hasattr(socket, "AF_BLUETOOTH") and hasattr(socket, "BTPROTO_RFCOMM")


def _make_socket():
    return socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)


def open_native(mac, channels=CHANNELS, sock_factory=None, timeout=10.0):
    """Collega il socket RFCOMM provando i canali: `Connection refused` = canale sbagliato (si passa al successivo); ogni altro errore
    (spento, fuori portata, chiave non valida) si segnala subito. Ritorna (BtSerial, canale)."""
    last = None
    for ch in channels:
        s = (sock_factory or _make_socket)()
        s.settimeout(timeout)
        try:
            s.connect((mac, ch))
        except OSError as e:
            last = e
            s.close()
            if e.errno == errno.ECONNREFUSED:
                continue
            raise OSError(f"GPS {mac} non raggiungibile: {e} (acceso, vicino, non gia' collegato a un altro apparecchio?)")
        s.settimeout(1.0)
        return BtSerial(s), ch
    raise OSError(f"nessun canale RFCOMM {list(channels)} ha risposto su {mac}: {last}")


class BridgeSerial:
    """Legge le righe dal processo `bt_bridge.py` (lanciato con un Python che ha il Bluetooth)."""
    cd = False

    def __init__(self, proc):
        self.proc = proc
        self.q = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in iter(self.proc.stdout.readline, b""):
            self.q.put(line)
        self.q.put(None)

    def readline(self):
        try:
            line = self.q.get(timeout=1.0)
        except queue.Empty:
            return b""
        if line is None:
            raise OSError("il ponte Bluetooth si e' chiuso")
        return line

    def close(self):
        try:
            self.proc.terminate()
        except OSError:
            pass


def find_bt_python(candidates=None):
    """Un Python (di sistema) con il supporto Bluetooth, o None."""
    for exe in candidates or ["/usr/bin/python3", shutil.which("python3"), "/usr/bin/python3.12", "/usr/bin/python3.10", "/usr/bin/python3.8"]:
        if not exe or not os.path.exists(exe):
            continue
        try:
            r = subprocess.run([exe, "-c", "import socket;print(hasattr(socket,'AF_BLUETOOTH') and hasattr(socket,'BTPROTO_RFCOMM'))"],
                               capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.stdout.strip() == "True":
            return exe
    return None


def open_bridge(mac, channels=CHANNELS, python=None, env=None, wait_s=20.0):
    exe = python or find_bt_python()
    if not exe:
        raise OSError("nessun Python con il supporto Bluetooth: usa il Python di sistema (/usr/bin/python3) per lanciare l'applicazione")
    bridge = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bt_bridge.py")
    e = dict(os.environ, **(env or {}))
    proc = subprocess.Popen([exe, bridge, mac, ",".join(map(str, channels))], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=e)
    first = []
    t = threading.Thread(target=lambda: first.append(proc.stderr.readline()), daemon=True)
    t.start()
    t.join(wait_s)
    msg = first[0].decode(errors="replace").strip() if first else ""
    if not msg.startswith("CONNECTED"):
        proc.terminate()
        raise OSError(msg[6:].strip() if msg.startswith("ERROR") else "il ponte Bluetooth non ha risposto in tempo")
    return BridgeSerial(proc), int(msg.split()[1])


def open_bt(mac, channels=CHANNELS):
    """Apre il GPS Bluetooth: socket diretto se questo Python lo permette, altrimenti il ponte. Ritorna (oggetto tipo seriale, descrizione)."""
    if have_native():
        ser, ch = open_native(mac, channels)
        return ser, f"Bluetooth {mac} canale {ch} (socket diretto)"
    ser, ch = open_bridge(mac, channels)
    return ser, f"Bluetooth {mac} canale {ch} (ponte con il Python di sistema)"
