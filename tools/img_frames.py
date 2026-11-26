"""Frame del protocollo immagini V3 (docs/protocollo-immagini.md): costanti, codificatori e decodificatore. Separato dal simulatore (tools/sim_immagini.py) e dal protocollo
(tools/img_proto.py) perche' e' la parte che il firmware C++ riprende identica (firmware/v3/src/frames.h)."""
import struct
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frame_mesh as fm  # noqa: E402
import protocollo_immagini as pi  # noqa: F401,E402

VERSION = 3
PROBE_BYTES = 32          # frame di PROBE
T = dict(HELLO=0, PROBE=1, PROBE_REPORT=2, MODE_SET=3, MODE_ACK=4, OFFER=5, ACCEPT=6, DATA=7, STATUS=8, PARITY=9, DONE=10, ABORT=11, ID=12,
         TEST=15)
TNAME = {v: k for k, v in T.items()}
F_LAST_WINDOW, F_RETX, F_LAST_OBJECT, F_LAYER_END = 1, 2, 4, 8
OBJ_BLOCK = 0


# ----------------------------------------------------------------------------------------------------------------- frame
def _hdr(tipo, sess, flags=0):
    return struct.pack(">BHB", (VERSION << 4) | tipo, sess & 0xFFFF, flags & 0xFF)


def _call(c):
    b = c.encode("ascii")
    return bytes([len(b)]) + b


def _s8(v):
    return struct.pack("b", max(-128, min(127, int(round(v)))))


F_POS = 16    # HELLO e OFFER: in coda la posizione (7 byte, vedi frame_mesh.pack_pos)
F_OPT = fm.F_OPT   # HELLO e OFFER: in coda opzioni TLV (revisione, profili fisici, identificativo a 32 bit, firma riservata)


def enc_hello(sess, call, chip, rung_mask, max_frame, mem_kb, reply=False, rssi=None, snr=None, pos=None, opts=None):
    """Con `rssi` e `snr` la risposta (reply) porta anche la misura del HELLO appena sentito (flag 2): il mittente puo' scegliere il gradino senza raffica di PROBE.
    Con `pos` (locatore o GPS) in coda la posizione (flag 16). Al primo contatto puo' mancare: la regola del progetto ammette il solo nominativo."""
    flags = (1 if reply else 0) | (2 if rssi is not None else 0) | (F_POS if pos is not None else 0) | (F_OPT if opts else 0)
    b = _hdr(T["HELLO"], sess, flags) + _call(call) + bytes([1 if chip == "SX1262" else 0]) + struct.pack(">HBH", rung_mask, max_frame, mem_kb)
    if rssi is not None:
        b += _s8(rssi) + _s8(snr)
    if pos is not None:
        b += fm.pack_pos(pos)
    if opts:
        b += fm.pack_opts(opts)
    return b


def enc_probe(sess, rung, idx, count, filler=PROBE_BYTES - 7):
    return _hdr(T["PROBE"], sess) + bytes([rung, idx, count]) + bytes(max(0, filler))


def enc_probe_report(sess, rung, expected, received, rssi, snr):
    return _hdr(T["PROBE_REPORT"], sess) + bytes([rung, expected, received]) + _s8(rssi) + _s8(snr)


def enc_mode_set(sess, rung, k, repeat):
    return _hdr(T["MODE_SET"], sess) + bytes([rung, k, repeat])


def enc_mode_ack(sess, rung):
    return _hdr(T["MODE_ACK"], sess) + bytes([rung])


def enc_offer(sess, call, objtype, size, piece, npieces, w, h, layer_ends, crc, pos=None, opts=None):
    """Con `pos` in coda la posizione del mittente (flag 16): nelle trasmissioni vere e' obbligatoria (docs/regole-radioamatoriali.md)."""
    return (_hdr(T["OFFER"], sess, (F_POS if pos is not None else 0) | (F_OPT if opts else 0)) + _call(call) + bytes([objtype]) + size.to_bytes(3, "big") + bytes([piece]) + struct.pack(">HHH", npieces, w, h) +
            bytes([len(layer_ends)]) + b"".join(struct.pack(">H", e) for e in layer_ends) + struct.pack(">I", crc) +
            (fm.pack_pos(pos) if pos is not None else b"") + (fm.pack_opts(opts) if opts else b""))


def enc_accept(sess, layers, window, k):
    return _hdr(T["ACCEPT"], sess) + bytes([layers, window, k])


def enc_data(sess, offset, payload, flags=0, widx=0):
    """Il campo del primo pezzo e' di 16 bit: 12 bit di indice (oggetti fino a 4096 pezzi da 16 byte = 64 kB, il tetto del progetto) e 4 bit con l'INDICE DEL FRAME NELLA FINESTRA
    (0-15, la finestra ha al massimo 16 frame): cosi' il ricevitore sa quanti frame sono partiti anche se gli ultimi si perdono, senza allungare l'intestazione."""
    if not 0 <= offset < 4096 or not 0 <= widx < 16:
        raise ValueError("primo pezzo da 0 a 4095, indice di finestra da 0 a 15")
    return _hdr(T["DATA"], sess, flags) + struct.pack(">H", offset | widx << 12) + payload


def enc_status(sess, base, bitmap64, rssi, snr, loss_pct, layers_done, flags=0):
    return _hdr(T["STATUS"], sess, flags) + struct.pack(">HQ", base, bitmap64) + _s8(rssi) + _s8(snr) + bytes([min(100, int(loss_pct)), layers_done])


def enc_done(sess, call, layers_delivered, nbytes, crc_prefix):
    return _hdr(T["DONE"], sess) + _call(call) + bytes([layers_delivered]) + nbytes.to_bytes(3, "big") + struct.pack(">I", crc_prefix)


def enc_abort(sess, reason):
    return _hdr(T["ABORT"], sess) + bytes([reason])


def decode(b):
    """Decodifica un frame; ritorna un dizionario con 'tipo' e i campi, o None se non e' un frame V3 valido."""
    if len(b) < 4 or (b[0] >> 4) != VERSION:
        return None
    tipo = b[0] & 0x0F
    d = {"tipo": tipo, "nome": TNAME.get(tipo, "?"), "sess": struct.unpack(">H", b[1:3])[0], "flags": b[3], "len": len(b)}
    body = b[4:]
    try:
        if tipo == T["HELLO"]:
            n = body[0]
            d.update(call=body[1:1 + n].decode(), chip="SX1262" if body[1 + n] else "SX1278", reply=bool(d["flags"] & 1))
            d["rung_mask"], d["max_frame"], d["mem_kb"] = struct.unpack(">HBH", body[2 + n:7 + n])
            o = 7 + n
            if d["flags"] & 2:
                d["rssi"], d["snr"] = struct.unpack("bb", body[o:o + 2])
                o += 2
            if d["flags"] & F_POS:
                if len(body) < o + 7:
                    return None                         # posizione troncata: frame non valido
                d["pos"] = fm.unpack_pos(body[o:o + 7])
                d["pos_raw"] = bytes(body[o:o + 7])
                o += 7
            if d["flags"] & F_OPT:
                d["opts"] = fm.unpack_opts(body[o:])
                d["opts_raw"] = bytes(body[o:])
        elif tipo == T["PROBE"]:
            d.update(rung=body[0], idx=body[1], count=body[2])
        elif tipo == T["PROBE_REPORT"]:
            d.update(rung=body[0], expected=body[1], received=body[2], rssi=struct.unpack("b", body[3:4])[0], snr=struct.unpack("b", body[4:5])[0])
        elif tipo == T["MODE_SET"]:
            d.update(rung=body[0], k=body[1], repeat=body[2])
        elif tipo == T["MODE_ACK"]:
            d.update(rung=body[0])
        elif tipo == T["OFFER"]:
            n = body[0]
            o = 1 + n
            d["call"] = body[1:o].decode()
            d["objtype"] = body[o]
            d["size"] = int.from_bytes(body[o + 1:o + 4], "big")
            d["piece"] = body[o + 4]
            d["npieces"], d["w"], d["h"] = struct.unpack(">HHH", body[o + 5:o + 11])
            nl = body[o + 11]
            d["layer_ends"] = [struct.unpack(">H", body[o + 12 + 2 * i:o + 14 + 2 * i])[0] for i in range(nl)]
            d["crc"] = struct.unpack(">I", body[o + 12 + 2 * nl:o + 16 + 2 * nl])[0]
            e = o + 16 + 2 * nl
            if d["flags"] & F_POS:
                if len(body) < e + 7:
                    return None
                d["pos"] = fm.unpack_pos(body[e:e + 7])
                d["pos_raw"] = bytes(body[e:e + 7])
                e += 7
            if d["flags"] & F_OPT:
                d["opts"] = fm.unpack_opts(body[e:])
                d["opts_raw"] = bytes(body[e:])
        elif tipo == T["ACCEPT"]:
            d.update(layers=body[0], window=body[1], k=body[2])
        elif tipo == T["DATA"]:
            v = struct.unpack(">H", body[:2])[0]
            d["offset"], d["widx"] = v & 0x0FFF, v >> 12
            d.update(relayed=bool(d["flags"] & fm.F_RELAYED), hops=d["flags"] >> fm.HOP_SHIFT)
            d["payload"] = body[2:]
        elif tipo == T["STATUS"]:
            d["base"], d["bitmap"] = struct.unpack(">HQ", body[:10])
            d["rssi"], d["snr"] = struct.unpack("bb", body[10:12])
            d["loss_pct"], d["layers_done"] = body[12], body[13]
        elif tipo == T["DONE"]:
            n = body[0]
            d["call"] = body[1:1 + n].decode()
            d["layers"] = body[1 + n]
            d["nbytes"] = int.from_bytes(body[2 + n:5 + n], "big")
            d["crc"] = struct.unpack(">I", body[5 + n:9 + n])[0]
        elif tipo == T["ABORT"]:
            d["reason"] = body[0]
    except (IndexError, struct.error, ValueError):      # ValueError comprende UnicodeDecodeError, la posizione di tipo sconosciuto e le opzioni troncate
        return None
    return d


