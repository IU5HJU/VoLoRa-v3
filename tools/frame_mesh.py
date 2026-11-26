"""Formati dei frame del mesh V3 e dei campi nuovi (posizione, identificativo globale, salti). Studio: provato solo con tests/sim/test_frame_mesh.py,
non con le schede. Tutti i numeri sono big endian. Il byte 0 e' 0x30 | tipo (come in docs/protocollo-immagini.md).

Tipi nuovi:  13 = BEACON (7 byte, solo nominativo)   14 = MESH (sottotipo nel byte 1)

POSIZIONE (7 byte, regola fissa del progetto: locatore o GPS assoluta):
  byte 0 = 0 -> locatore: 6 caratteri ASCII (per esempio JN53ab)
  byte 0 = 1 -> GPS: latitudine (3 byte) e longitudine (3 byte), (lat+90)/180 e (lon+180)/360 su 24 bit: risoluzione circa 1,2 m e 2,4 m
NOMINATIVO COMPATTO (6 byte = 8 caratteri da 6 bit): 0 riempimento, 1-10 cifre, 11-36 lettere, 37 '/', 38 '-'.
"""
import struct
import zlib

VERSION = 3
REVISION = 2                                   # revisione 0.2 dei frame (23/11/2026): opzioni TLV, profili, banda, id a 32 bit
T_BEACON, T_MESH = 13, 14
# Sottotipi del frame 14: 1-63 mesh, 64-127 collegamento e cambio di banda, 128-255 riservati (spazio per le funzioni future)
SUB = dict(POLL=1, POLL_REPLY=2, REQ_RELAY=3, OFFER_RELAY=4, GROUP=5, GROUP_ACK=6, VOTE=7, NODE_INFO=8, BAND_SET=64, BAND_ACK=65, BAND_BACK=66, BAND_SET_FREQ=67, BAND_ACK_FREQ=68)
SUBNAME = {v: k for k, v in SUB.items()}
ADMIT, EXCLUDE, RESERVE = 0, 1, 2            # stato di un membro nel GRUPPO
CODE_SELECTIVE, CODE_FOUNTAIN = 1, 2          # maschera dei codici supportati
PROFILE_SUBGHZ, PROFILE_2G4, PROFILE_2G4_UART = 0, 1, 2   # profilo fisico: 0 = 430-440 MHz (R0-R14, SX1278/SX1262), 1 = 2,4 GHz con radio SPI (SX1280/SX1281; scala da definire), 2 = 2,4 GHz con modulo UART trasparente (tubo opaco, es. Ebyte E28-2G4T27SX)
BAND_AT_ACK, BAND_AT_UTC = 0, 1               # BAND-SET: il cambio avviene alla fine del BAND-ACK oppure all'ora UTC indicata
BACK_PROBE_FAILED, BACK_TIMEOUT, BACK_USER = 1, 2, 3
F_OPT = 128                                   # flag dei frame di controllo: in coda ci sono opzioni TLV
OPT_REV, OPT_PROFILES, OPT_SIGN, OPT_ID32 = 1, 2, 3, 4    # tipi di opzione (OPT_SIGN: riservata alla firma di autenticita', formato da definire)
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
    """Identificativo globale dell'oggetto a 32 bit: CRC32 di (nominativo di origine + contatore a 16 bit). Lo stesso su tutti i ripetitori e per il destinatario.
    Nel DATA e nei frame brevi si usa la forma corta a 16 bit (short_id); l'identificativo intero sta in OFFER e RICHIESTA-RIPETITORI."""
    return zlib.crc32(origin_call.upper().encode("ascii") + struct.pack(">H", counter & 0xFFFF))


def short_id(obj32):
    """Parte bassa a 16 bit dell'identificativo: e' la sessione dei frame DATA."""
    return obj32 & 0xFFFF


# ----------------------------------------------------------------------------------------------------------------------------- opzioni TLV
def pack_opts(opts):
    """opts = [(tipo, bytes), ...] -> byte 'tipo, lunghezza, valore' uno dopo l'altro, fino alla fine del frame."""
    out = b""
    for t, v in opts:
        if not 0 < t < 256 or len(v) > 255:
            raise ValueError("opzione non valida")
        out += bytes([t, len(v)]) + v
    return out


def unpack_opts(b):
    """Legge le opzioni fino alla fine; un tipo sconosciuto si salta (e' il modo di non rompere le versioni future). ValueError se troncate."""
    d, i = {}, 0
    while i < len(b):
        if i + 2 > len(b) or i + 2 + b[i + 1] > len(b):
            raise ValueError("opzioni troncate")
        d[b[i]] = b[i + 2:i + 2 + b[i + 1]]
        i += 2 + b[i + 1]
    return d


def opt_revision(rev=REVISION):
    return (OPT_REV, bytes([rev]))


def opt_profiles(profiles):
    """profiles = [(id_profilo, maschera_gradini_16bit), ...]: i profili fisici supportati e, per ognuno, i gradini."""
    return (OPT_PROFILES, b"".join(struct.pack(">BH", p, m) for p, m in profiles))


def parse_profiles(v):
    return [struct.unpack(">BH", v[i:i + 3]) for i in range(0, len(v) - len(v) % 3, 3)]


def opt_id32(obj32):
    return (OPT_ID32, struct.pack(">I", obj32))


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
    return _mesh("REQ_RELAY", struct.pack(">I", obj) + pack_call(origin) + pack_call(dest) + size.to_bytes(3, "big"))


NOT_HEARD = 255


def enc_offer_relay(obj, call, pos, rung_src, rung_dst, margin_src, margin_dst, codes, mem_kb):
    """Un candidato ripetitore: gradino massimo verso mittente e destinatario (un byte ciascuno, 255 = non sentito: lo spazio per altri gradini e profili c'e'),
    i due margini in dB, i codici, la memoria. `obj` e' l'identificativo (si usa la parte a 16 bit)."""
    return _mesh("OFFER_RELAY", struct.pack(">H", short_id(obj)) + pack_call(call) + pack_pos(pos) + bytes([rung_src & 255, rung_dst & 255]) +
                 _s8(margin_src) + _s8(margin_dst) + bytes([codes]) + struct.pack(">H", mem_kb))


def enc_node_info(call, node_id, service_khz, caps):
    """NODO (identificazione di un nodo fisso): nominativo, identificativo (0-255, quello del VOTO), frequenza del suo canale di servizio in kHz e capacita'
    (bit 0: puo' votare a 2 m, bit 1: puo' votare a 70 cm). Servono a sapere con quali vicini si vota: due nodi votano solo sullo stesso canale. 14 byte."""
    return _mesh("NODE_INFO", pack_call(call) + struct.pack(">BIB", node_id & 0xFF, int(service_khz), caps & 0xFF))


def enc_group(obj, code, rung, k_symbols, symbol_size, seed, start_utc, members):
    """members = [(nominativo, stato ADMIT/EXCLUDE/RESERVE, turno 0-63)]. start_utc in secondi Unix (32 bit)."""
    b = struct.pack(">HBBHBHI", short_id(obj), code, rung, k_symbols, symbol_size, seed, int(start_utc)) + bytes([len(members)])
    for call, state, turn in members:
        b += pack_call(call) + bytes([(turn & 63) << 2 | (state & 3)])
    return _mesh("GROUP", b)


def enc_group_ack(obj, veto_call=None, rung=0):
    """Conferma del destinatario; con veto_call il destinatario non sente quel membro al gradino scelto."""
    if veto_call is None:
        return _mesh("GROUP_ACK", struct.pack(">HBB", short_id(obj), 0, rung))
    return _mesh("GROUP_ACK", struct.pack(">HBB", short_id(obj), 1, rung) + pack_call(veto_call))


def enc_vote(call, session, margin_db, node_id):
    """VOTO (isofrequenza, vedi docs/voting-isofrequenza.md): un nodo che ha decodificato la prima trasmissione di `call` (sessione `session`) dichiara il proprio margine
    in dB e il proprio identificativo (0-255). Va sul canale di servizio fra i nodi, in uno slot per nodo. 12 byte."""
    return _mesh("VOTE", pack_call(call) + struct.pack(">H", session & 0xFFFF) + _s8(margin_db) + bytes([node_id & 0xFF]))


def enc_band_set(session, profile, channel, rung, k, repeat, mode=BAND_AT_ACK, start_utc=0):
    """Proposta di cambio di banda (come il MODE-SET, ma verso un altro profilo fisico, per esempio 2,4 GHz). Si manda sulla banda attuale, ripetuta.
    profile = profilo fisico, channel = indice nella tabella dei canali del profilo, rung = gradino nel profilo, k = pezzi per frame DATA, mode/start_utc = quando."""
    return _mesh("BAND_SET", struct.pack(">HBBBBBBI", session & 0xFFFF, profile, channel, rung, k, repeat, mode, int(start_utc)))


def enc_band_set_freq(session, profile, freq_khz, rung, k, repeat, mode=BAND_AT_ACK, start_utc=0):
    """Come BAND-SET, ma con la FREQUENZA in kHz al posto dell'indice del canale: serve quando le due stazioni hanno tabelle dei canali diverse
    (le frequenze sono liberamente configurabili nel firmware). 17 byte."""
    return _mesh("BAND_SET_FREQ", struct.pack(">HBIBBBBI", session & 0xFFFF, profile, int(freq_khz), rung, k, repeat, mode, int(start_utc)))


RSSI_UNKNOWN = -128


def enc_band_ack_freq(session, profile, freq_khz, rssi_dbm=RSSI_UNKNOWN):
    """Conferma del BAND-SET con frequenza esplicita, oppure CONTROPROPOSTA: il ricevitore, che ha scansionato i canali (modo RSSI del modulo), mette la frequenza che preferisce
    e l'RSSI misurato su di essa (-128 = non misurato). Se la frequenza e' diversa da quella proposta, il mittente la conferma con un nuovo BAND-SET-FREQ. 10 byte."""
    return _mesh("BAND_ACK_FREQ", struct.pack(">HBIb", session & 0xFFFF, profile, int(freq_khz), max(-128, min(127, int(rssi_dbm)))))


def enc_band_ack(session, profile, channel):
    """Conferma sulla banda attuale: l'altra stazione ha il profilo e prova il canale."""
    return _mesh("BAND_ACK", struct.pack(">HBB", session & 0xFFFF, profile, channel))


def enc_band_back(session, reason):
    """Ritorno alla banda base (informativo: chi non sente piu' nulla ci torna da solo allo scadere del timer)."""
    return _mesh("BAND_BACK", struct.pack(">HB", session & 0xFFFF, reason))


def vote_winner(votes):
    """votes = [(margine_dB, id_nodo)]: vince il margine piu' alto; a parita' l'identificativo piu' basso. Ritorna l'id vincente."""
    return min(votes, key=lambda v: (-v[0], v[1]))[1]


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
            d.update(obj=struct.unpack(">I", x[0:4])[0], origin=unpack_call(x[4:10]), dest=unpack_call(x[10:16]), size=int.from_bytes(x[16:19], "big"))
        elif n == "OFFER_RELAY":
            d.update(obj=struct.unpack(">H", x[0:2])[0], call=unpack_call(x[2:8]), pos=unpack_pos(x[8:15]), rung_src=x[15], rung_dst=x[16],
                     margin_src=struct.unpack("b", x[17:18])[0], margin_dst=struct.unpack("b", x[18:19])[0], codes=x[19], mem_kb=struct.unpack(">H", x[20:22])[0])
        elif n == "GROUP":
            d["obj"], d["code"], d["rung"], d["k"], d["symbol_size"], d["seed"], d["start"] = struct.unpack(">HBBHBHI", x[:13])
            cnt = x[13]
            d["members"] = [(unpack_call(x[14 + 7 * i:20 + 7 * i]), x[20 + 7 * i] & 3, x[20 + 7 * i] >> 2) for i in range(cnt)]
            if len(x) < 14 + 7 * cnt:
                return None
        elif n == "NODE_INFO":
            d["call"] = unpack_call(x[0:6])
            d["node"], d["service_khz"], d["caps"] = struct.unpack(">BIB", x[6:12])
        elif n == "VOTE":
            d.update(call=unpack_call(x[0:6]), session=struct.unpack(">H", x[6:8])[0], margin=struct.unpack("b", x[8:9])[0], node=x[9])
        elif n == "BAND_SET":
            d["session"], d["profile"], d["channel"], d["rung"], d["k"], d["repeat"], d["mode"], d["start"] = struct.unpack(">HBBBBBBI", x[:12])
        elif n == "BAND_SET_FREQ":
            d["session"], d["profile"], d["freq_khz"], d["rung"], d["k"], d["repeat"], d["mode"], d["start"] = struct.unpack(">HBIBBBBI", x[:15])
        elif n == "BAND_ACK_FREQ":
            d["session"], d["profile"], d["freq_khz"], d["rssi_dbm"] = struct.unpack(">HBIb", x[:8])
        elif n == "BAND_ACK":
            d["session"], d["profile"], d["channel"] = struct.unpack(">HBB", x[:4])
        elif n == "BAND_BACK":
            d["session"], d["reason"] = struct.unpack(">HB", x[:3])
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
