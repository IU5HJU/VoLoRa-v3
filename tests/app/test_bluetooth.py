"""Prove del collegamento Bluetooth con socket e processi finti: python3 -I tests/app/test_bluetooth.py"""
import errno
import os
import socket
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "app"))
from volora_misure import bluetooth as bt  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


# elenco dei dispositivi
class R:
    def __init__(self, out, rc=0):
        self.stdout, self.returncode = out, rc


out = "Device 00:02:76:C7:59:63 Nokia LD-3W\nDevice 30:7F:10:06:D6:94 IU5HJU\nDevice EC:47:0C:C0:69:49 BRC1H C0:69:49\nrumore\n"
dev = bt.list_paired(run=lambda a, **k: R(out))
check(dev[0] == ("00:02:76:C7:59:63", "Nokia LD-3W") and len(dev) == 3 and dev[2][1] == "BRC1H C0:69:49", "elenco dei dispositivi da bluetoothctl")
calls = []


def run_old(args, **k):
    calls.append(args)
    return R("Invalid command", 0) if "Paired" in args else R(out)


check(len(bt.list_paired(run=run_old)) == 3 and len(calls) == 2, "BlueZ vecchio senza 'Paired': ripiega su 'devices'")


def boom(*a, **k):
    raise FileNotFoundError("bluetoothctl")


check(bt.list_paired(run=boom) == [], "bluetoothctl assente: elenco vuoto, nessun errore")
check(bt.parse_choice(bt.label("00:02:76:C7:59:63", "Nokia LD-3W")) == ("bt", "00:02:76:C7:59:63"), "voce dell'elenco -> indirizzo")
check(bt.parse_choice("bt:00:02:76:c7:59:63") == ("bt", "00:02:76:C7:59:63") and bt.parse_choice("/dev/ttyACM0") == ("serial", "/dev/ttyACM0") and bt.parse_choice("  ") == (None, ""), "scelta: Bluetooth, seriale, vuota")


# socket finto
class FakeSock:
    def __init__(self, chunks=(), connect_errno=None):
        self.chunks, self.connect_errno, self.closed, self.tm = list(chunks), connect_errno, False, None
        self.connected_to = None

    def settimeout(self, t):
        self.tm = t

    def connect(self, addr):
        self.connected_to = addr
        if self.connect_errno:
            raise OSError(self.connect_errno, os.strerror(self.connect_errno))

    def recv(self, n):
        if not self.chunks:
            return b""
        c = self.chunks.pop(0)
        if c == "timeout":
            raise socket.timeout()
        return c

    def close(self):
        self.closed = True


s = FakeSock([b"$GPGGA,1,2", b"3*00\r\n$GPRM", "timeout", b"C,x*11\r\n", b""])
ser = bt.BtSerial(s)
check(ser.readline() == b"$GPGGA,1,23*00\r\n", "riga ricomposta da due pezzi")
check(ser.readline() == b"", "riga a meta' e nessun altro dato: riga vuota, il pezzo resta in memoria")
check(ser.readline() == b"$GPRMC,x*11\r\n", "la riga a meta' si completa al pezzo successivo")
try:
    ser.readline()
    check(False, "chiusura del GPS non segnalata")
except OSError as e:
    check("chiuso" in str(e), "collegamento chiuso dal GPS: errore")
s2 = FakeSock(["timeout"])
check(bt.BtSerial(s2).readline() == b"", "nessun dato entro il tempo: riga vuota, senza errore")

# canali
made = []


def factory_refused_then_ok():
    sk = FakeSock([b"x\n"], connect_errno=errno.ECONNREFUSED if not made else None)
    made.append(sk)
    return sk


ser, ch = bt.open_native("00:02:76:C7:59:63", sock_factory=factory_refused_then_ok)
check(ch == 2 and made[0].closed and made[1].connected_to == ("00:02:76:C7:59:63", 2) and made[1].tm == 1.0, "canale 1 rifiutato: prova il 2 e lo usa")
try:
    bt.open_native("00:02:76:C7:59:63", sock_factory=lambda: FakeSock(connect_errno=errno.EHOSTDOWN))
    check(False, "GPS spento: serviva un errore")
except OSError as e:
    check("non raggiungibile" in str(e), "GPS spento o lontano: errore chiaro e subito, senza provare gli altri canali")
n = []
try:
    bt.open_native("00:02:76:C7:59:63", sock_factory=lambda: (n.append(1), FakeSock(connect_errno=errno.ECONNREFUSED))[1])
    check(False, "nessun canale: serviva un errore")
except OSError as e:
    check(len(n) == 5 and "nessun canale" in str(e), "tutti i canali rifiutati: 5 tentativi poi errore")

# ponte con un processo finto
with tempfile.TemporaryDirectory() as td:
    f = os.path.join(td, "nmea.txt")
    open(f, "w").write("$GPGGA,092255.668,,,,,0,00,,,M,0.0,M,,0000*57\r\n$GPRMC,092255.668,V,,,,,,,291006,,,N*40\r\n")
    ser, ch = bt.open_bridge("00:02:76:C7:59:63", python=sys.executable, env={"VOLORA_BT_FAKE": f}, wait_s=10)
    a, b = ser.readline(), ser.readline()
    check(ch == 1 and a.startswith(b"$GPGGA") and b.startswith(b"$GPRMC"), "ponte: righe dal processo figlio")
    try:
        for _ in range(5):
            ser.readline()
        check(False, "ponte chiuso senza errore")
    except OSError as e:
        check("ponte" in str(e), "ponte chiuso: errore")
    ser.close()
check((bt.find_bt_python([sys.executable]) == sys.executable) == bt.have_native(), "ricerca di un Python con il Bluetooth coerente con questo Python")
check(bt.find_bt_python(["/non/esiste"]) is None, "nessun Python adatto: None")
try:
    bt.open_bridge("00:02:76:C7:59:63", python="/non/esiste/python")
    check(False, "serviva un errore")
except (OSError, FileNotFoundError):
    check(True, "ponte con un Python inesistente: errore")

print("bluetooth: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
