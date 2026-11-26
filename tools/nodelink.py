"""Collegamento VoLoRa-IP fra due nodi (porting in Python di lib/voicecore/node_link.* della v2, versione 1): datagramma UDP firmato con HMAC-SHA256 troncato a 8 byte,
anti-ripetizione con contatore, sfida dopo un riavvio, collegamento attivo solo quando i due si sono autenticati a vicenda. SERVE AL REFLECTOR V3 (tools/reflector_v3.py),
che deve parlare lo stesso protocollo della v2 senza cambiarlo. Provato contro il vero `vlnode` della v2 in tests/interop/test_reflector_vs_vlnode.py.

Datagramma: 'V' 'L' | versione (1) | tipo (1) | canale (1) | id nodo (4) | id di avvio (4) | contatore (4) | lunghezza (1) | contenuto | firma (8)."""
import hashlib
import hmac
import struct

VERSION = 1
HEADER, SIG, MAX_PAYLOAD, NONCE = 18, 8, 255, 8
HELLO, CHALLENGE, RESPONSE, PACKET, KEEPALIVE = 1, 2, 3, 4, 5
HELLO_MS, KEEPALIVE_MS, DEAD_MS, CHALLENGE_GAP_MS, CHALLENGE_LIFE_MS = 2000, 20000, 60000, 1000, 10000

IGNORED, BAD_SIGNATURE, REPLAY, UNKNOWN, CONTROL, PACKET_OK = "ignored", "bad_signature", "replay", "unknown", "control", "packet"


class Rx:
    def __init__(self):
        self.kind = IGNORED
        self.packet = b""
        self.replies = []


class NodeLink:
    def __init__(self, node_id, peer_id, key, boot, rng, channel=0, ext=b""):
        """peer_id 0 = qualunque nodo con la chiave giusta. rng() ritorna un intero a 32 bit. ext = byte aggiunti ai HELLO e KEEPALIVE dopo i 9 di stato
        (estensione V3: i client v2 leggono solo i primi 9 byte e la ignorano)."""
        self.node_id, self.peer_id, self.key, self.boot, self.rng, self.channel, self.ext = node_id, peer_id, bytes(key), boot, rng, channel, ext
        self.counter = 0
        self.peer_auth = False
        self.peer_accepts_me = False
        self.peer_boot = 0
        self.peer_seen_id = 0
        self.peer_last_counter = 0
        self.peer_public = 0
        self.public_addr = 0
        self.peer_ext = b""
        self.challenge_pending = False
        self.nonce = b""
        self.challenge_ms = 0
        self.have_challenge_ms = False
        self.last_challenge_ms = 0
        self.have_status_reply_ms = False
        self.last_status_reply_ms = 0
        self.have_rx = False
        self.last_rx_ms = 0
        self.have_sent = False
        self.last_send_ms = 0
        self.stats = dict(sent=0, received=0, bad_signature=0, replays=0, unknown=0, ignored=0, challenges=0, authenticated=0)

    def _sign(self, msg):
        return hmac.new(self.key, msg, hashlib.sha256).digest()[:SIG]

    def build(self, typ, payload=b""):
        if len(payload) > MAX_PAYLOAD:
            return b""
        self.counter += 1
        head = b"VL" + bytes([VERSION, typ, self.channel]) + struct.pack(">III", self.node_id, self.boot, self.counter) + bytes([len(payload)])
        msg = head + payload
        self.stats["sent"] += 1
        return msg + self._sign(msg)

    def _status(self, typ):
        p = bytes([(1 if self.peer_auth else 0) | (2 if (self.peer_auth and self.peer_accepts_me) else 0)]) + struct.pack(">I", self.peer_boot if self.peer_auth else 0)
        if self.public_addr or self.ext:
            p += struct.pack(">I", self.public_addr) + self.ext
        return self.build(typ, p)

    def make_hello(self):
        return self._status(HELLO)

    def make_keepalive(self):
        return self._status(KEEPALIVE)

    def make_packet(self, wire):
        return self.build(PACKET, wire)

    def link_up(self, now_ms):
        return self.peer_auth and self.peer_accepts_me and self.have_rx and now_ms - self.last_rx_ms < DEAD_MS

    def maintenance(self, now_ms):
        every = KEEPALIVE_MS if self.link_up(now_ms) else HELLO_MS
        if self.have_sent and now_ms - self.last_send_ms < every:
            return b""
        self.have_sent, self.last_send_ms = True, now_ms
        return self.make_keepalive() if self.link_up(now_ms) else self.make_hello()

    def _challenge(self, now_ms):
        self.nonce = b"".join(struct.pack(">I", self.rng() & 0xFFFFFFFF) for _ in range(NONCE // 4))
        self.challenge_pending, self.challenge_ms = True, now_ms
        self.have_challenge_ms, self.last_challenge_ms = True, now_ms
        self.stats["challenges"] += 1
        return self.build(CHALLENGE, self.nonce)

    def on_datagram(self, d, now_ms):
        rx = Rx()
        if len(d) < HEADER + SIG or d[0:2] != b"VL" or d[2] != VERSION:
            self.stats["ignored"] += 1
            return rx
        ln = d[17]
        if len(d) != HEADER + ln + SIG:
            self.stats["ignored"] += 1
            return rx
        if not hmac.compare_digest(self._sign(d[:HEADER + ln]), d[HEADER + ln:]):
            self.stats["bad_signature"] += 1
            rx.kind = BAD_SIGNATURE
            return rx
        typ, channel = d[3], d[4]
        nid, boot, counter = struct.unpack(">III", d[5:17])
        payload = d[HEADER:HEADER + ln]
        if channel != self.channel or nid == self.node_id or (self.peer_id != 0 and nid != self.peer_id):
            self.stats["ignored"] += 1
            return rx
        if typ == CHALLENGE:
            if ln != NONCE:
                self.stats["ignored"] += 1
                return rx
            rx.replies.append(self.build(RESPONSE, payload))
            known = self.peer_auth and boot == self.peer_boot and nid == self.peer_seen_id
            if not known and (not self.have_challenge_ms or now_ms - self.last_challenge_ms >= CHALLENGE_GAP_MS):
                rx.replies.append(self._challenge(now_ms))
            rx.kind = CONTROL
            self.stats["received"] += 1
            return rx
        if typ == RESPONSE:
            if self.challenge_pending and ln == NONCE and payload == self.nonce and now_ms - self.challenge_ms < CHALLENGE_LIFE_MS:
                self.challenge_pending = False
                self.peer_auth, self.peer_seen_id, self.peer_boot, self.peer_last_counter = True, nid, boot, counter
                self.peer_accepts_me = False
                self.peer_public = 0
                self.peer_ext = b""
                self.have_rx, self.last_rx_ms = True, now_ms
                self.stats["authenticated"] += 1
                self.stats["received"] += 1
                rx.kind = CONTROL
                rx.replies.append(self._status(KEEPALIVE))
            else:
                self.stats["ignored"] += 1
            return rx
        if not (self.peer_auth and boot == self.peer_boot and nid == self.peer_seen_id):
            self.stats["unknown"] += 1
            rx.kind = UNKNOWN
            if not self.have_challenge_ms or now_ms - self.last_challenge_ms >= CHALLENGE_GAP_MS:
                rx.replies.append(self._challenge(now_ms))
            return rx
        if counter <= self.peer_last_counter:
            self.stats["replays"] += 1
            rx.kind = REPLAY
            return rx
        self.peer_last_counter = counter
        self.have_rx, self.last_rx_ms = True, now_ms
        self.stats["received"] += 1
        if typ == PACKET:
            rx.kind, rx.packet = PACKET_OK, payload
        else:
            rx.kind = CONTROL
            if typ in (HELLO, KEEPALIVE) and ln >= 5:
                self.peer_accepts_me = bool(payload[0] & 1) and struct.unpack(">I", payload[1:5])[0] == self.boot
                if ln >= 9:
                    self.peer_public = struct.unpack(">I", payload[5:9])[0]
                self.peer_ext = bytes(payload[9:])
                if not (payload[0] & 2) and (not self.have_status_reply_ms or now_ms - self.last_status_reply_ms >= CHALLENGE_GAP_MS):
                    self.have_status_reply_ms, self.last_status_reply_ms = True, now_ms
                    rx.replies.append(self._status(KEEPALIVE))
        return rx
