"""Incapsulamento dei frame V3 su un flusso seriale trasparente (moduli radio UART come l'Ebyte E28-2G4T27SX).

Un modulo UART a trasmissione trasparente spezzetta il flusso di byte a modo suo: i confini dei frame non si conservano e un pacchetto perso lascia un
buco nel flusso. Ogni frame viene quindi codificato con COBS (nessuno zero nei dati), con CRC16 in coda e uno zero come delimitatore: chi riceve si
risincronizza al delimitatore successivo, scarta i frame rovinati e li conta.
Costo: 1 byte di delimitatore, 2 di CRC e circa 1 byte ogni 254 di COBS. Provato in tests/sim/test_uart_frame.py, NON con un modulo vero."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frame_mesh import crc16  # noqa: E402

DELIM = 0
MAX_FRAME = 1024      # oltre questa lunghezza senza delimitatore si scarta il buffer (rumore)


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


def encode_frame(payload):
    body = bytes(payload) + crc16(bytes(payload)).to_bytes(2, "big")
    return cobs_encode(body) + bytes([DELIM])


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
            if len(body) < 3 or crc16(body[:-2]) != int.from_bytes(body[-2:], "big"):
                self.bad += 1
                continue
            self.ok += 1
            out.append(body[:-2])
        return out


def overhead(payload_len):
    """Byte in piu' di un payload di payload_len byte sul flusso."""
    return len(encode_frame(bytes(range(1, 256)) * (payload_len // 255) + bytes(range(1, 1 + payload_len % 255)))) - payload_len
