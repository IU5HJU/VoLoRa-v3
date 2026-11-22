"""Ponte Bluetooth RFCOMM -> uscita standard, solo libreria standard. Serve quando il Python dell'applicazione (per esempio quello di conda) non ha
il supporto Bluetooth ma il Python di sistema si': l'applicazione lancia questo file con il Python di sistema e legge le frasi NMEA dalla pipe.

  python3 bt_bridge.py INDIRIZZO CANALI      (CANALI: per esempio 1,2,3)
Scrive su stderr 'CONNECTED <canale>' o 'ERROR <testo>'; poi i dati ricevuti su stdout. Con VOLORA_BT_FAKE=<file> legge le righe da quel file
(solo per le prove)."""
import errno
import os
import socket
import sys
import time


def main():
    mac = sys.argv[1]
    channels = [int(c) for c in sys.argv[2].split(",")] if len(sys.argv) > 2 else [1]
    fake = os.environ.get("VOLORA_BT_FAKE")
    out = sys.stdout.buffer
    if fake:
        sys.stderr.write("CONNECTED 1\n")
        sys.stderr.flush()
        for line in open(fake, "rb"):
            out.write(line)
            out.flush()
            time.sleep(0.02)
        return 0
    if not hasattr(socket, "AF_BLUETOOTH"):
        sys.stderr.write("ERROR questo Python non ha il supporto Bluetooth (AF_BLUETOOTH)\n")
        return 2
    last = None
    s = None
    for ch in channels:
        s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        s.settimeout(10.0)
        try:
            s.connect((mac, ch))
        except OSError as e:
            last = e
            s.close()
            s = None
            if e.errno == errno.ECONNREFUSED:
                continue            # canale sbagliato: prova il successivo
            break                   # GPS spento, fuori portata o chiave non valida: inutile provare gli altri
        sys.stderr.write(f"CONNECTED {ch}\n")
        sys.stderr.flush()
        break
    if s is None:
        sys.stderr.write(f"ERROR {last}\n")
        return 3
    s.settimeout(None)
    while True:
        data = s.recv(1024)
        if not data:
            return 4
        out.write(data)
        out.flush()


if __name__ == "__main__":
    sys.exit(main())
