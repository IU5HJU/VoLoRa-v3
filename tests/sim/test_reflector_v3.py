"""Prove del reflector V3 (logica, senza socket): python3 -I tests/sim/test_reflector_v3.py"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import frame_mesh as fm  # noqa: E402
import nodelink as nl  # noqa: E402
import reflector_v3 as rv  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


class Rete:
    """Un reflector e i suoi client collegati con una rete finta (consegna immediata)."""

    def __init__(self, voice_mode=4, specs=None):
        self.r = random.Random(7)
        self.now = 0
        self.core = rv.ReflectorCore(1000, voice_mode, 5000, lambda: self.r.getrandbits(32))
        self.cl = {}
        for cid, v3 in (specs or [(2, False), (3, False), (4, True)]):
            key = bytes([cid]) * 16
            self.core.add_client(cid, key, f"n{cid}", f"CALL{cid}")
            ext = rv.V3_MAGIC + bytes([1, rv.CAP_FRAMES | rv.CAP_DIRECTORY]) if v3 else b""
            link = nl.NodeLink(cid, 1000, key, 100 + cid, lambda: self.r.getrandbits(32), ext=ext)
            self.cl[cid] = {"link": link, "addr": ("127.0.0.1", 40000 + cid), "rx": [], "v3": v3}

    def _deliver_to_client(self, cid, d):
        c = self.cl[cid]
        rx = c["link"].on_datagram(d, self.now)
        if rx.kind == nl.PACKET_OK:
            c["rx"].append(rx.packet)
        for rep in rx.replies:
            self._to_core(cid, rep)

    def _to_core(self, cid, d):
        for to, b in self.core.on_datagram(self.cl[cid]["addr"], d, self.now):
            for k, c in self.cl.items():
                if c["addr"] == to:
                    self._deliver_to_client(k, b)

    def step(self, ms=100, n=1):
        for _ in range(n):
            self.now += ms
            for cid, c in self.cl.items():
                m = c["link"].maintenance(self.now)
                if m:
                    self._to_core(cid, m)
            for to, b in self.core.tick(self.now):
                for k, c in self.cl.items():
                    if c["addr"] == to:
                        self._deliver_to_client(k, b)

    def connect(self):
        self.step(100, 60)

    def send(self, cid, wire):
        self._to_core(cid, self.cl[cid]["link"].make_packet(wire))


def v2pkt(mode, session, seq, flags, call=b"", payload=b""):
    f = flags | (rv.FLAG_CALLSIGN if call else 0)
    return bytes([(2 << 4) | mode, session >> 8, session & 255, seq, f]) + ((bytes([len(call)]) + call) if call else b"") + payload


net = Rete()
net.connect()
check(all(c["link"].link_up(net.now) for c in net.cl.values()) and all(c.was_up for c in net.core.clients.values()), "i tre client si collegano (sfida, firma, attivazione a due vie)")
txt = v2pkt(7, 0x1234, 0, rv.FLAG_START | rv.FLAG_END, b"IU5HJU", b"Prova")
net.send(2, txt)
check(len(net.cl[3]["rx"]) == 1 and len(net.cl[4]["rx"]) == 1 and net.cl[2]["rx"] == [] and net.cl[3]["rx"][0][4] & rv.FLAG_RELAYED, "il testo di un client arriva agli altri con il flag RELAYED, mai a chi l'ha mandato")
check(net.cl[3]["rx"][0][:4] == txt[:4] and net.cl[3]["rx"][0][5:] == txt[5:], "il pacchetto e' identico a parte il flag RELAYED")
# voce: chi parla per primo tiene il canale
for c in net.cl.values():
    c["rx"].clear()
net.send(2, v2pkt(4, 0xAAAA, 0, rv.FLAG_START, b"IU5HJU", b"x" * 20))
net.send(3, v2pkt(4, 0xBBBB, 0, rv.FLAG_START, b"IK5XYZ", b"y" * 20))
check(len(net.cl[3]["rx"]) == 1 and net.cl[2]["rx"] == [] and net.core.stats["voice_blocked"] == 1, "voce: chi parla per primo tiene il canale, quella dell'altro si scarta")
net.send(3, txt)
check(len(net.cl[2]["rx"]) == 1, "il testo passa anche mentre qualcuno parla")
net.send(2, v2pkt(4, 0xAAAA, 1, rv.FLAG_END, b"", b"z" * 20))
check(net.core.talking is False, "il pacchetto di fine libera subito il canale")
net.send(3, v2pkt(4, 0xBBBB, 0, rv.FLAG_START, b"IK5XYZ", b"y" * 20))
check(len(net.cl[2]["rx"]) == 2 and net.core.stats["talks"] == 2, "dopo la fine parla l'altro")
net.send(2, v2pkt(3, 1, 0, rv.FLAG_START | rv.FLAG_END, b"IU5HJU", b"\x00\x01"))
check(net.core.stats["bad_mode"] == 1, "un modo che non e' la voce del reflector o il testo si scarta")
net.step(100, 40)
check(net.core.talking is False, "senza pacchetti per 3 s il canale si libera da solo")
# sicurezza
sconosciuto = nl.NodeLink(99, 1000, b"k" * 16, 1, lambda: 1).make_hello()
check(net.core.on_datagram(("9.9.9.9", 1), sconosciuto, net.now) == [] and net.core.stats["unknown_client"] >= 1, "un id sconosciuto e' ignorato senza risposta (nessuna amplificazione)")
falso = bytearray(net.cl[2]["link"].make_packet(txt))
falso[-1] ^= 1
before = len(net.cl[3]["rx"])
net.core.on_datagram(net.cl[2]["addr"], bytes(falso), net.now)
check(net.core.stats["bad_signature"] == 1 and len(net.cl[3]["rx"]) == before, "una firma sbagliata si scarta")
buono = net.cl[2]["link"].make_packet(txt)
net.core.on_datagram(net.cl[2]["addr"], buono, net.now)
n2 = len(net.cl[3]["rx"])
net.core.on_datagram(net.cl[2]["addr"], buono, net.now)
check(net.core.stats["replays"] == 1 and len(net.cl[3]["rx"]) == n2, "un datagramma ripetuto (contatore) si scarta")
# V3: capacita' e instradamento
check(net.core.clients[4].v3 and not net.core.clients[2].v3 and not net.core.clients[3].v3, "il reflector riconosce il client che dichiara il V3 e solo quello")
net.cl[4]["rx"].clear(); net.cl[2]["rx"].clear(); net.cl[3]["rx"].clear()
inj = fm.enc_refl_annuncio([("IK5XYZ", 5)])
net.send(2, inj)
check(net.core.stats["v3_refused"] == 1 and net.cl[3]["rx"] == [] and net.cl[4]["rx"] == [], "un client v2 non puo' inserire frame V3")
net2 = Rete(specs=[(2, False), (4, True), (5, True)])
net2.connect()
net2.send(5, fm.enc_refl_annuncio([("IK5XYZ", 10), ("IZ5AAA", 20)]))
check(net2.core.stats["v3_announces"] == 1 and "IK5XYZ" in net2.core.clients[5].directory, "l'annuncio del gateway riempie la rubrica del reflector")
inner = fm.enc_poll("IU5HJU", "IK5XYZ")
net2.send(4, fm.enc_refl_inoltro("IK5XYZ", "IU5HJU", 3, inner))
got = [fm.decode(p) for p in net2.cl[5]["rx"]]
esito4 = [fm.decode(p) for p in net2.cl[4]["rx"]]
check(any(g and g["nome"] == "REFL_INOLTRO" and g["inner"] == inner and g["ttl"] == 2 for g in got), "la busta arriva al gateway che sente la destinazione, con il ttl ridotto")
check(any(e and e["nome"] == "REFL_ESITO" and e["code"] == fm.ESITO_CONSEGNATO for e in esito4), "il mittente riceve l'esito 'consegnato'")
check(net2.cl[2]["rx"] == [], "il client v2 non vede mai nulla del V3")
net2.cl[4]["rx"].clear()
net2.send(4, fm.enc_refl_inoltro("N0BODY", "IU5HJU", 3, inner))
check(any(fm.decode(p)["code"] == fm.ESITO_NON_TROVATO for p in net2.cl[4]["rx"]), "destinazione sconosciuta: esito 'non trovato'")
net2.cl[4]["rx"].clear()
net2.send(4, fm.enc_refl_inoltro("IK5XYZ", "IU5HJU", 0, inner))
check(any(fm.decode(p)["code"] == fm.ESITO_RIFIUTATO for p in net2.cl[4]["rx"]), "ttl esaurito: rifiutato")
net2.step(1000, 700)
net2.cl[4]["rx"].clear()
net2.send(4, fm.enc_refl_inoltro("IK5XYZ", "IU5HJU", 3, inner))
check(net2.core.clients[4].link.link_up(net2.now) and any(fm.decode(p) and fm.decode(p).get("code") == fm.ESITO_NON_TROVATO for p in net2.cl[4]["rx"]), "la rubrica scade dopo 10 minuti senza un nuovo annuncio: esito 'non trovato'")
# il V3 non sposta il comportamento del v2: stesso esito con e senza client V3
net3 = Rete(specs=[(2, False), (3, False)])
net3.connect()
net3.send(2, txt)
check(len(net3.cl[3]["rx"]) == 1, "con soli client v2 il reflector si comporta come il reflector v2")
# file dei client
import tempfile  # noqa: E402
with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as f:
    f.write("# id chiave nominativo [nome]\n2 000102030405060708090a0b0c0d0e0f IU5HJU casa\n\n3 101112131415161718191a1b1c1d1e1f IK5XYZ\n")
cc = rv.load_clients(f.name)
os.unlink(f.name)
check(len(cc) == 2 and cc[0][0] == 2 and cc[0][2] == "IU5HJU" and cc[0][3] == "casa" and cc[1][3] == "", "il file dei client e' quello della v2")
print("reflector V3: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
