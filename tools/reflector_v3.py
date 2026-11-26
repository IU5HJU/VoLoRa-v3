"""Reflector V3: sostituto compatibile del reflector v2 (docs/reflector-v3.md). Riferimento in Python: la LOGICA (ReflectorCore, senza socket) e un piccolo server UDP.

Compatibilita' con la v2 (la v2 non si modifica):
  - stesso collegamento VoLoRa-IP (tools/nodelink.py), stesso file dei client (id, chiave, nominativo, nome), un solo modo voce, testo sempre, chi parla per primo tiene il
    canale fino a END o 3 s, flag RELAYED, mai al mittente, id sconosciuto ignorato senza risposta;
  - un client v2 non vede mai un frame V3.
Estensione V3, solo per i client che la dichiarano nei loro HELLO e KEEPALIVE (dopo i 9 byte di stato: 'V3', revisione, capacita'):
  - REFL_ANNUNCIO: il gateway dice quali stazioni sente (elenco della zona radio);
  - REFL_INOLTRO: busta per far arrivare un frame V3 a una stazione attraverso il gateway che la sente; il reflector risponde REFL_ESITO.
Provato in tests/sim/test_reflector_v3.py e contro il vero vlnode della v2 in tests/interop/test_reflector_vs_vlnode.py."""
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frame_mesh as fm  # noqa: E402
import nodelink as nl  # noqa: E402

V2_VERSION, V3_VERSION = 2, 3
MODE_TEXT = 7
FLAG_START, FLAG_END, FLAG_PARITY, FLAG_CALLSIGN, FLAG_POSITION, FLAG_TOTAL, FLAG_RELAYED = 1, 2, 4, 8, 32, 64, 128
TALK_HANG_MS = 3000
V3_MAGIC = b"V3"
REVISION = 1
CAP_FRAMES, CAP_DIRECTORY = 1, 2           # il client vuole i frame V3; il client manda gli annunci
DIR_LIFE_S = 600


def parse_v2(p):
    """Controllo minimo di un pacchetto radio v2 (docs/protocollo.md della v2). Ritorna un dizionario o None."""
    if len(p) < 5 or (p[0] >> 4) != V2_VERSION:
        return None
    flags = p[4]
    d = {"mode": p[0] & 15, "session": (p[1] << 8) | p[2], "seq": p[3], "flags": flags, "callsign": ""}
    if d["seq"] >= 128:
        return None
    pos = 5
    if flags & FLAG_CALLSIGN:
        if pos >= len(p):
            return None
        n = p[pos]
        pos += 1
        if not 1 <= n <= 8 or pos + n > len(p):
            return None
        d["callsign"] = p[pos:pos + n].decode("ascii", "replace")
        pos += n
    if flags & FLAG_POSITION:
        if not flags & FLAG_CALLSIGN or pos + 7 > len(p):
            return None
        pos += 7
    if flags & FLAG_TOTAL:
        if not flags & FLAG_START or pos >= len(p):
            return None
        pos += 1
    d["parity"] = bool(flags & FLAG_PARITY)
    return d


class Client:
    def __init__(self, cid, key, name, callsign, link):
        self.id, self.key, self.name, self.callsign, self.link = cid, key, name, callsign, link
        self.endpoint = None
        self.last_seen = 0
        self.was_up = False
        self.v3 = False
        self.caps = 0
        self.packets_in = self.packets_out = 0
        self.directory = {}          # nominativo -> istante (ms) in cui il gateway lo ha sentito


class ReflectorCore:
    def __init__(self, reflector_id, voice_mode, boot, rng, log=None):
        self.id, self.voice_mode, self.boot, self.rng, self.log = reflector_id, voice_mode, boot, rng, log or (lambda s: None)
        self.clients = {}
        self.talking = False
        self.talker = 0
        self.talk_session = 0
        self.talk_last = 0
        self.stats = dict(datagrams=0, unknown_client=0, bad_signature=0, replays=0, voice_forwarded=0, text_forwarded=0, voice_blocked=0, bad_mode=0, bad_packet=0, talks=0,
                          v3_forwarded=0, v3_refused=0, v3_announces=0)

    # --- client
    def add_client(self, cid, key, name="", callsign=""):
        if cid == 0 or cid == self.id or cid in self.clients:
            return False
        link = nl.NodeLink(self.id, cid, key, self.boot + len(self.clients) + 1, self.rng)
        self.clients[cid] = Client(cid, key, name, callsign, link)
        return True

    def remove_client(self, cid):
        return self.clients.pop(cid, None) is not None

    def set_client_key(self, cid, key):
        c = self.clients.get(cid)
        if not c:
            return False
        c.key, c.endpoint, c.was_up, c.v3 = key, None, False, False
        c.link = nl.NodeLink(self.id, cid, key, self.boot + cid + 0x1000, self.rng)
        return True

    # --- datagrammi
    def on_datagram(self, frm, d, now):
        out = []
        self.stats["datagrams"] += 1
        if len(d) < nl.HEADER + nl.SIG or d[0:2] != b"VL":
            self.stats["unknown_client"] += 1
            return out
        c = self.clients.get(int.from_bytes(d[5:9], "big"))
        if not c:
            self.stats["unknown_client"] += 1
            return out
        rx = c.link.on_datagram(d, now)
        if rx.kind == nl.BAD_SIGNATURE:
            self.stats["bad_signature"] += 1
            return out
        if rx.kind == nl.REPLAY:
            self.stats["replays"] += 1
            return out
        out += [(frm, r) for r in rx.replies]
        typ = d[3]
        fresh = rx.kind in (nl.PACKET_OK, nl.CONTROL) and typ != nl.CHALLENGE
        if fresh and c.link.peer_auth:
            c.endpoint, c.last_seen = frm, now
            if typ in (nl.HELLO, nl.KEEPALIVE):
                self._learn_v3(c)
        up = c.link.link_up(now)
        if up != c.was_up:
            c.was_up = up
            self.log(f"client {c.name} " + ("collegato" if up else "non piu' collegato"))
        if rx.kind != nl.PACKET_OK:
            return out
        c.packets_in += 1
        pkt = rx.packet
        if pkt and (pkt[0] >> 4) == V3_VERSION:
            return out + self._on_v3(c, pkt, now)
        return out + self._on_v2(c, pkt, now)

    def _learn_v3(self, c):
        e = c.link.peer_ext
        if len(e) >= 4 and e[0:2] == V3_MAGIC:
            if not c.v3:
                self.log(f"client {c.name} dichiara il V3 (revisione {e[2]}, capacita' {e[3]})")
            c.v3, c.caps = True, e[3]
            c.link.ext = V3_MAGIC + bytes([REVISION, CAP_FRAMES | CAP_DIRECTORY])
        else:
            c.v3, c.caps = False, 0
            c.link.ext = b""

    # --- v2: identico al reflector v2
    def _on_v2(self, c, pkt, now):
        p = parse_v2(pkt)
        if p is None:
            self.stats["bad_packet"] += 1
            return []
        voice = p["mode"] == self.voice_mode
        if not voice and p["mode"] != MODE_TEXT:
            self.stats["bad_mode"] += 1
            return []
        if voice:
            hanging = self.talking and now - self.talk_last <= TALK_HANG_MS
            if hanging and self.talker != c.id:
                self.stats["voice_blocked"] += 1
                return []
            if not p["parity"]:
                if not hanging or self.talker != c.id or self.talk_session != p["session"]:
                    self.stats["talks"] += 1
                    self.log(f"parla {p['callsign'] or '-'} ({c.name}), sessione {p['session']:04X}")
                self.talking, self.talker, self.talk_session, self.talk_last = True, c.id, p["session"], now
            elif hanging:
                self.talk_last = now
        wire = bytearray(pkt)
        wire[4] |= FLAG_RELAYED
        out = self._forward(c, bytes(wire), now, voice)
        if voice and (p["flags"] & FLAG_END) and not p["parity"]:
            self.talking = False
            self.log(f"fine trasmissione di {c.name}")
        return out

    def _forward(self, frm, wire, now, voice):
        out = []
        for o in self.clients.values():
            if o.id == frm.id or o.endpoint is None or not o.link.link_up(now):
                continue
            out.append((o.endpoint, o.link.make_packet(wire)))
            o.packets_out += 1
            self.stats["voice_forwarded" if voice else "text_forwarded"] += 1
        return out

    # --- V3
    def _on_v3(self, c, pkt, now):
        if not c.v3:
            self.stats["v3_refused"] += 1            # un client v2 non puo' inserire frame V3
            return []
        d = fm.decode(pkt)
        if d is None or d["nome"] not in ("REFL_ANNUNCIO", "REFL_INOLTRO"):
            self.stats["v3_refused"] += 1
            return []
        if d["nome"] == "REFL_ANNUNCIO":
            self.stats["v3_announces"] += 1
            c.directory = {call: now - age * 1000 for call, age in d["entries"]}
            return []
        # INOLTRO: al gateway che ha sentito la destinazione piu' di recente; l'esito al mittente
        dest = d["dest"]
        best = None
        for o in self.clients.values():
            if o.id == c.id or not o.v3 or o.endpoint is None or not o.link.link_up(now):
                continue
            seen = o.directory.get(dest)
            if seen is not None and now - seen <= DIR_LIFE_S * 1000 and (best is None or seen > best[0]):
                best = (seen, o)
        if d["ttl"] == 0 or best is None:
            code = fm.ESITO_RIFIUTATO if d["ttl"] == 0 else fm.ESITO_NON_TROVATO
            return [(c.endpoint, c.link.make_packet(fm.enc_refl_esito(dest, code)))]
        o = best[1]
        o.packets_out += 1
        self.stats["v3_forwarded"] += 1
        fwd = fm.enc_refl_inoltro(dest, d["src"], d["ttl"] - 1, d["inner"])
        return [(o.endpoint, o.link.make_packet(fwd)), (c.endpoint, c.link.make_packet(fm.enc_refl_esito(dest, fm.ESITO_CONSEGNATO)))]

    # --- tempo
    def tick(self, now):
        out = []
        for c in self.clients.values():
            if c.endpoint is None:
                continue
            if now - c.last_seen >= nl.DEAD_MS:
                c.endpoint = None
                if c.was_up:
                    c.was_up = False
                    self.log(f"client {c.name} non risponde piu'")
                continue
            m = c.link.maintenance(now)
            if m:
                out.append((c.endpoint, m))
            up = c.link.link_up(now)
            if up != c.was_up:
                c.was_up = up
                self.log(f"client {c.name} " + ("collegato" if up else "non piu' collegato"))
        if self.talking and now - self.talk_last > TALK_HANG_MS:
            self.talking = False
            self.log("trasmissione finita (nessun pacchetto)")
        return out


def load_clients(path):
    """File dei client della v2: 'id chiave nominativo [nome]' (righe vuote e con # ignorate)."""
    out = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            t = ln.split(None, 3)
            if len(t) < 3 or len(t[1]) != 32:
                raise ValueError(f"riga non valida: {ln}")
            out.append((int(t[0]), bytes.fromhex(t[1]), t[2], t[3] if len(t) > 3 else ""))
    return out


def serve(config, port=5400, reflector_id=1000, voice_mode=4, duration=None, bind="0.0.0.0", log=print):
    import random
    rng = random.SystemRandom()
    core = ReflectorCore(reflector_id, voice_mode, rng.getrandbits(32), lambda: rng.getrandbits(32), log)
    for cid, key, call, name in load_clients(config):
        core.add_client(cid, key, name or call, call)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((bind, port))
    sock.settimeout(0.2)
    log(f"vlreflector V3 (riferimento Python) id {reflector_id} sulla porta UDP {sock.getsockname()[1]}, modo voce {voice_mode}, {len(core.clients)} client")
    t0 = time.monotonic()
    last = 0
    while duration is None or time.monotonic() - t0 < duration:
        now = int((time.monotonic() - t0) * 1000)
        try:
            data, addr = sock.recvfrom(2048)
            for to, b in core.on_datagram(addr, data, now):
                sock.sendto(b, to)
        except socket.timeout:
            pass
        if now - last >= 500:
            last = now
            for to, b in core.tick(now):
                sock.sendto(b, to)
    return core


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True)
    ap.add_argument("--port", type=int, default=5400)
    ap.add_argument("--id", type=int, default=1000)
    ap.add_argument("--voice-mode", type=int, default=4, choices=(1, 4))
    ap.add_argument("--duration", type=float, default=None)
    a = ap.parse_args()
    serve(a.config, a.port, a.id, a.voice_mode, a.duration)
