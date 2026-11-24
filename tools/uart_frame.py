"""Incapsulamento dei frame V3 su un flusso seriale trasparente (moduli radio UART come l'Ebyte E28-2G4T27SX).

Un modulo UART a trasmissione trasparente spezzetta il flusso di byte a modo suo: i confini dei frame non si conservano e un pacchetto perso lascia un
buco nel flusso. Ogni frame viene quindi codificato con COBS (nessuno zero nei dati), con CRC16 in coda e uno zero come delimitatore: chi riceve si
risincronizza al delimitatore successivo, scarta i frame rovinati e li conta.
Un modulo Ebyte E28 apre una finestra di configurazione di 10 secondi se nei dati trova tre byte E2 (o E3) di fila: ogni frame ha quindi un byte di "seme" e,
se serve, i dati si mescolano con una sequenza pseudocasuale finche' quelle sequenze non compaiono piu' (provato in tests/sim/test_uart_frame.py).
Costo: 1 byte di delimitatore, 1 di seme, 2 di CRC e 1 di COBS (fino a 254 byte): 5 byte in piu' per frame. Provato in tests/sim/test_uart_frame.py, NON con un modulo vero."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frame_mesh import crc16  # noqa: E402
from ebyte_e28 import FORBIDDEN_IN_DATA, MAX_PACKET  # noqa: E402

DELIM = 0
MAX_FRAME = 1024      # oltre questa lunghezza senza delimitatore si scarta il buffer (rumore)
OVERHEAD = 5          # seme (1), CRC (2), COBS (1), delimitatore (1)
MAX_PAYLOAD = MAX_PACKET - OVERHEAD   # 116: il frame intero entra in un pacchetto d'aria da 121 byte del modulo


def cobs_encode(data):
    out = bytearray([0])
    code_pos, code = 0, 1
    for b in data:
        if b == 0:
            out[code_pos] = code
            code_pos, code = len(out), 1
            out.append(0)
        else:
            out.append(b)
            code += 1
            if code == 0xFF:
                out[code_pos] = code
                code_pos, code = len(out), 1
                out.append(0)
    out[code_pos] = code
    return bytes(out)


def cobs_decode(data):
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        code = data[i]
        if code == 0 or i + code > n:
            raise ValueError("COBS non valido")
        out += data[i + 1:i + code]
        i += code
        if i < n and code < 0xFF:
            out.append(0)
    return bytes(out)


def _keystream(seed, n):
    s = (seed * 2654435761 + 1) & 0xFFFFFFFF
    out = bytearray()
    for _ in range(n):
        s = (s * 1664525 + 1013904223) & 0xFFFFFFFF
        out.append(s >> 24)
    return bytes(out)


def _whiten(data, seed):
    if seed == 0:
        return bytes(data)
    ks = _keystream(seed, len(data))
    return bytes(a ^ b for a, b in zip(data, ks))


def encode_frame(payload):
    """Frame sul filo: COBS(seme + payload e CRC mescolati col seme) + delimitatore. Il seme e' il piu' piccolo per cui nel risultato non compare E2E2E2 o E3E3E3."""
    body = bytes(payload) + crc16(bytes(payload)).to_bytes(2, "big")
    for seed in range(256):
        enc = cobs_encode(bytes([seed]) + _whiten(body, seed)) + bytes([DELIM])
        if not any(f in enc for f in FORBIDDEN_IN_DATA):
            return enc
    raise ValueError("nessun seme evita le sequenze riservate del modulo")


class Decoder:
    """Riceve byte a pezzi qualsiasi (feed) e restituisce i frame completi e validi. Conta quelli scartati."""

    def __init__(self, max_frame=MAX_FRAME):
        self.buf = bytearray()
        self.max_frame = max_frame
        self.ok = 0
        self.bad = 0

    def feed(self, data):
        out = []
        for b in data:
            if b != DELIM:
                self.buf.append(b)
                if len(self.buf) > self.max_frame:
                    self.buf.clear()
                    self.bad += 1
                continue
            if not self.buf:
                continue
            chunk = bytes(self.buf)
            self.buf.clear()
            try:
                body = cobs_decode(chunk)
            except ValueError:
                self.bad += 1
                continue
            if len(body) < 4:
                self.bad += 1
                continue
            data = _whiten(body[1:], body[0])
            if crc16(data[:-2]) != int.from_bytes(data[-2:], "big"):
                self.bad += 1
                continue
            self.ok += 1
            out.append(data[:-2])
        return out


def max_pieces(piece=16, data_header=6):
    """Pezzi per frame DATA che entrano in un pacchetto d'aria del modulo (121 byte): (116 - 6) // 16 = 6."""
    return (MAX_PAYLOAD - data_header) // piece


def overhead(payload_len):
    """Byte in piu' di un payload di payload_len byte sul flusso."""
    return len(encode_frame(bytes(range(1, 256)) * (payload_len // 255) + bytes(range(1, 1 + payload_len % 255)))) - payload_len
