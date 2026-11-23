"""Formati dei frame del mesh V3 e dei campi nuovi (posizione, identificativo globale, salti). Studio: provato solo con tests/sim/test_frame_mesh.py,
non con le schede. Tutti i numeri sono big endian. Il byte 0 e' 0x30 | tipo (come in docs/protocollo-immagini.md).

Tipi nuovi:  13 = BEACON (7 byte, solo nominativo)   14 = MESH (sottotipo nel byte 1)

POSIZIONE (7 byte, regola fissa del progetto: locatore o GPS assoluta):
  byte 0 = 0 -> locatore: 6 caratteri ASCII (per esempio JN53ab)
  byte 0 = 1 -> GPS: latitudine (3 byte) e longitudine (3 byte), (lat+90)/180 e (lon+180)/360 su 24 bit: risoluzione circa 1,2 m e 2,4 m
NOMINATIVO COMPATTO (6 byte = 8 caratteri da 6 bit): 0 riempimento, 1-10 cifre, 11-36 lettere, 37 '/', 38 '-'.
"""
import struct

VERSION = 3
T_BEACON, T_MESH = 13, 14
SUB = dict(POLL=1, POLL_REPLY=2, REQ_RELAY=3, OFFER_RELAY=4, GROUP=5, GROUP_ACK=6)
SUBNAME = {v: k for k, v in SUB.items()}
ADMIT, EXCLUDE, RESERVE = 0, 1, 2            # stato di un membro nel GRUPPO
CODE_SELECTIVE, CODE_FOUNTAIN = 1, 2          # maschera dei codici supportati
F_RELAYED, HOP_SHIFT = 16, 5                  # flag del frame DATA: bit 4 = ritrasmesso da un ripetitore, bit 5-7 = numero di salti (0-7)

_CH = "\0" + "0123456789" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ" + "/-"


# ---------------------------------------------------------------------------------------------------------------- nominativo compatto
def pack_call(call):
    call = call.upper()
    if not 1 <= len(call) <= 8 or any(c not in _CH[1:] for c in call):
        raise ValueError(f"nominativo non codificabile: {call!r}")
    v = 0
    for i in range(8):
        v = (v << 6) | (_CH.index(call[i]) if i < len(call) else 0)
    return v.to_bytes(6, "big")


def unpack_call(b):
    v = int.from_bytes(b[:6], "big")
    out = []
    for i in range(8):
        k = (v >> (6 * (7 - i))) & 63
        if k == 0:
            break
        if k >= len(_CH):
            raise ValueError("carattere non valido")
        out.append(_CH[k])
    return "".join(out)


# --------------------------------------------------------------------------------------------------------------------- posizione
def pack_pos(pos):
    """pos = {'loc': 'JN53ab'} oppure {'lat': ..., 'lon': ...}. 7 byte."""
    if pos.get("lat") is not None:
        la = round((pos["lat"] + 90.0) / 180.0 * (1 << 24))
        lo = round((pos["lon"] + 180.0) / 360.0 * (1 << 24))
        la, lo = min(max(la, 0), (1 << 24) - 1), min(max(lo, 0), (1 << 24) - 1)
        return b"\x01" + la.to_bytes(3, "big") + lo.to_bytes(3, "big")
    loc = pos["loc"]
    if len(loc) != 6 or not loc.isascii():
        raise ValueError("il locatore deve avere 6 caratteri (per esempio JN53ab)")
    return b"\x00" + loc.encode("ascii")


def unpack_pos(b):
    if b[0] == 1:
        return {"lat": int.from_bytes(b[1:4], "big") / (1 << 24) * 180.0 - 90.0, "lon": int.from_bytes(b[4:7], "big") / (1 << 24) * 360.0 - 180.0}
    if b[0] == 0:
        return {"loc": b[1:7].decode("ascii")}
    raise ValueError("tipo di posizione sconosciuto")


# ------------------------------------------------------------------------------------------------------------ identificativo globale
def crc16(data, crc=0xFFFF):
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def object_id(origin_call, counter):
    """Identificativo globale dell'oggetto: CRC16 di (nominativo di origine + contatore a 16 bit). Lo stesso su tutti i ripetitori e per il destinatario."""
    return crc16(origin_call.upper().encode("ascii") + struct.pack(">H", counter & 0xFFFF))


def data_flags(base, relayed=False, hops=0):
    return (base & 0x0F) | (F_RELAYED if relayed else 0) | ((min(hops, 7) & 7) << HOP_SHIFT)


def split_data_flags(flags):
    return {"base": flags & 0x0F, "relayed": bool(flags & F_RELAYED), "hops": flags >> HOP_SHIFT}


# ---------------------------------------------------------------------------------------------------------------------------- frame
def enc_beacon(call):
    """7 byte: intestazione + nominativo compatto. Solo il nominativo (primo contatto: la regola ammette solo il nominativo)."""
    return bytes([(VERSION << 4) | T_BEACON]) + pack_call(call)


def _mesh(sub, body):
    return bytes([(VERSION << 4) | T_MESH, SUB[sub]]) + body


def _s8(v):
    return struct.pack("b", max(-128, min(127, int(round(v)))))


def enc_poll(caller, target):
    return _mesh("POLL", pack_call(caller) + pack_call(target))


def enc_poll_reply(call, pos, rssi, snr, rung_mask, codes, mem_kb):
    """Livello 2: nominativo, posizione, rapporto di segnale del POLL appena sentito, capacita'."""
    return _mesh("POLL_REPLY", pack_call(call) + pack_pos(pos) + _s8(rssi) + _s8(snr) + struct.pack(">HBH", rung_mask, codes, mem_kb))


def enc_req_relay(obj, origin, dest, size):
    return _mesh("REQ_RELAY", struct.pack(">H", obj) + pack_call(origin) + pack_call(dest) + size.to_bytes(3, "big"))


def enc_offer_relay(obj, call, pos, rung_src, rung_dst, margin_src, margin_dst, codes, mem_kb):
    """Un candidato ripetitore: gradino massimo verso mittente e destinatario (4 bit ciascuno, 15 = non sentito), i due margini in dB, i codici, la memoria."""
    return _mesh("OFFER_RELAY", struct.pack(">H", obj) + pack_call(call) + pack_pos(pos) + bytes([(rung_src & 15) << 4 | (rung_dst & 15)]) +
                 _s8(margin_src) + _s8(margin_dst) + bytes([codes]) + struct.pack(">H", mem_kb))


def enc_group(obj, code, rung, k_symbols, symbol_size, seed, start_utc, members):
    """members = [(nominativo, stato ADMIT/EXCLUDE/RESERVE, turno 0-63)]. start_utc in secondi Unix (32 bit)."""
    b = struct.pack(">HBBHBHI", obj, code, rung, k_symbols, symbol_size, seed, int(start_utc)) + bytes([len(members)])
    for call, state, turn in members:
        b += pack_call(call) + bytes([(turn & 63) << 2 | (state & 3)])
    return _mesh("GROUP", b)


def enc_group_ack(obj, veto_call=None, rung=0):
    """Conferma del destinatario; con veto_call il destinatario non sente quel membro al gradino scelto."""
    if veto_call is None:
        return _mesh("GROUP_ACK", struct.pack(">HBB", obj, 0, rung))
    return _mesh("GROUP_ACK", struct.pack(">HBB", obj, 1, rung) + pack_call(veto_call))


def decode(b):
    """Decodifica BEACON o MESH. Ritorna un dizionario o None."""
    if len(b) < 3 or (b[0] >> 4) != VERSION:
        return None
    t = b[0] & 15
    try:
        if t == T_BEACON:
            if len(b) != 7:
                return None
            return {"nome": "BEACON", "call": unpack_call(b[1:7]), "len": len(b)}
        if t != T_MESH or b[1] not in SUBNAME:
            return None
        d = {"nome": SUBNAME[b[1]], "len": len(b)}
        x = b[2:]
        n = d["nome"]
        if n == "POLL":
            d.update(caller=unpack_call(x[0:6]), target=unpack_call(x[6:12]))
        elif n == "POLL_REPLY":
            d.update(call=unpack_call(x[0:6]), pos=unpack_pos(x[6:13]), rssi=struct.unpack("b", x[13:14])[0], snr=struct.unpack("b", x[14:15])[0])
            d["rung_mask"], d["codes"], d["mem_kb"] = struct.unpack(">HBH", x[15:20])
        elif n == "REQ_RELAY":
            d.update(obj=struct.unpack(">H", x[0:2])[0], origin=unpack_call(x[2:8]), dest=unpack_call(x[8:14]), size=int.from_bytes(x[14:17], "big"))
        elif n == "OFFER_RELAY":
            d.update(obj=struct.unpack(">H", x[0:2])[0], call=unpack_call(x[2:8]), pos=unpack_pos(x[8:15]), rung_src=x[15] >> 4, rung_dst=x[15] & 15,
                     margin_src=struct.unpack("b", x[16:17])[0], margin_dst=struct.unpack("b", x[17:18])[0], codes=x[18], mem_kb=struct.unpack(">H", x[19:21])[0])
        elif n == "GROUP":
            d["obj"], d["code"], d["rung"], d["k"], d["symbol_size"], d["seed"], d["start"] = struct.unpack(">HBBHBHI", x[:13])
            cnt = x[13]
            d["members"] = [(unpack_call(x[14 + 7 * i:20 + 7 * i]), x[20 + 7 * i] & 3, x[20 + 7 * i] >> 2) for i in range(cnt)]
            if len(x) < 14 + 7 * cnt:
                return None
        elif n == "GROUP_ACK":
            d.update(obj=struct.unpack(">H", x[0:2])[0], veto=bool(x[2]), rung=x[3])
            if x[2]:
                d["veto_call"] = unpack_call(x[4:10])
    except (IndexError, struct.error, ValueError, UnicodeDecodeError):
        return None
    return d


if __name__ == "__main__":
    oid = object_id("IU5HJU", 1)
    pos = {"loc": "JN53ab"}
    esempi = [("BEACON", enc_beacon("IU5HJU")), ("POLL", enc_poll("IU5HJU", "IK5XYZ")), ("POLL-REPLY", enc_poll_reply("IK5XYZ", pos, -118, -7, 0x7FFF, 3, 100)),
              ("RICHIESTA-RIPETITORI", enc_req_relay(oid, "IU5HJU", "IZ5AAA", 20000)), ("OFFERTA", enc_offer_relay(oid, "IK5XYZ", pos, 4, 5, 9, -3, 3, 100)),
              ("GRUPPO (2 membri)", enc_group(oid, CODE_FOUNTAIN, 6, 128, 16, 1, 1795000000, [("IK5XYZ", ADMIT, 0), ("IZ5AAA", ADMIT, 1)])),
              ("CONFERMA", enc_group_ack(oid, rung=6)), ("VETO", enc_group_ack(oid, "IK5XYZ", 6))]
    for nome, f in esempi:
        print(f"{nome:22s} {len(f):3d} byte  {f.hex()}")
