"""Logica dell'applicazione, senza interfaccia grafica ne' seriale (provata sul PC: tests/app/test_core.py)."""
import base64
import csv
import json
import os
import random
import struct
import sys
import time
import urllib.parse
import zlib

_TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools")
sys.path.insert(0, os.path.abspath(_TOOLS))
import protocollo_immagini as pi  # noqa: E402
import scala_modi as sm  # noqa: E402

DEFAULT_REPO = "IU5HJU/VoLoRa-v3"
CAPS_RXBW = {"SX1278": 250.0, "SX1262": 467.0}
FIELDS = ["time", "mode", "freq_mhz", "power_dbm", "att_db", "p_rx_dbm", "sent", "rx_ok", "rx_bad", "loss_pct", "rssi", "snr", "fei_hz",
          "toa_mean_us", "toa_calc_us"]


# ---------- Modi ----------
def mode_names():
    """Elenco (codice, descrizione) dei modi L1-L13 e F1-F6 di docs/scala-modi.md."""
    out = []
    for i, (bw, sf) in enumerate(sm.LORA, 1):
        out.append((f"L{i}", f"LoRa BW {bw:g} kHz SF{sf}"))
    for i, (br, dev) in enumerate(sm.FSK, 1):
        out.append((f"F{i}", f"FSK {br:g} kbit/s dev {dev:g} kHz"))
    return out


def mode_command(code, chip="SX1278"):
    """Comando MODE del firmware di misura per un codice (L1-L13, F1-F6)."""
    code = code.strip().upper()
    if code.startswith("L"):
        bw, sf = sm.LORA[int(code[1:]) - 1]
        return f"MODE LORA {bw:g} {sf} 5"
    br, dev = sm.FSK[int(code[1:]) - 1]
    need = br + 2 * dev                  # banda del segnale, doppia banda laterale
    if chip == "SX1278":
        need /= 2                         # il filtro dell'SX1278 e' a banda laterale singola (datasheet, Table 40): il numero e' meta' della banda del segnale
    rxbw = min(need, CAPS_RXBW.get(chip, 250.0))
    return f"MODE FSK {br:g} {dev:g} {rxbw:g}"


# gradini del protocollo immagini -> modi della scala (docs/scala-modi.md): R10 = L9 (125 kHz SF12), R11 = L10 (62,5), R12 = L11 (31,25), R13 = L12 (15,6), R14 = L13 (7,8)
GRADINI_LENTI = {"R10": "L9", "R11": "L10", "R12": "L11", "R13": "L12", "R14": "L13"}


def parse_series(text):
    """'R11, L12 ,F4' -> ['L10', 'L12', 'F4'] (i nomi Rxx si traducono nei modi Lxx). ValueError se un nome non esiste."""
    names = [c for c, _ in mode_names()]
    out = []
    for tok in text.replace(";", ",").replace(" ", ",").split(","):
        tok = tok.strip().upper()
        if not tok:
            continue
        tok = GRADINI_LENTI.get(tok, tok)
        if tok not in names:
            raise ValueError(f"modo sconosciuto: {tok}")
        out.append(tok)
    if not out:
        raise ValueError("serie vuota")
    return out


def interval_ms(code, payload, margin=1.3, minimo=300):
    """Intervallo fra i pacchetti di una serie: il tempo in aria calcolato per un pacchetto di `payload` byte, piu' un margine (LoRa); 300 ms per FSK."""
    code = code.strip().upper()
    if code.startswith("L"):
        bw, sf = sm.LORA[int(code[1:]) - 1]
        toa = sm.lora_toa(sf, bw, payload=payload)
        return max(minimo, int(toa * 1000 * margin) + 200)
    return minimo


def sens_estimate(code):
    code = code.strip().upper()
    if code.startswith("L"):
        bw, sf = sm.LORA[int(code[1:]) - 1]
        return sm.sens_lora(bw, sf)
    br, dev = sm.FSK[int(code[1:]) - 1]
    import math
    return -174 + 10 * math.log10((br + 2 * dev) * 1000) + sm.NF + 12


# ---------- Righe della seriale ----------
def parse_line(line):
    """Riconosce le righe del firmware di misura. Ritorna (tipo, dizionario) oppure (None, {})."""
    line = line.strip()
    if not line:
        return None, {}
    word = line.split(" ", 1)[0]
    if word in ("TXSUM", "RXSUM", "TX", "RX"):
        d = {}
        for tok in line.split()[1:]:
            if "=" in tok:
                k, v = tok.split("=", 1)
                try:
                    d[k] = float(v)
                except ValueError:
                    d[k] = float("nan")
        return word, d
    if word in ("INFO", "MODE", "OK", "ERR", "STOP", "CW"):
        return word, {"text": line}
    return None, {}


def new_row(mode, freq, power, att, txsum, rxsum):
    """Riga di risultato da un TXSUM e un RXSUM (dizionari di parse_line)."""
    sent = int(txsum.get("sent", 0))
    ok = int(rxsum.get("ok", 0))
    bad = int(rxsum.get("bad", 0))
    loss = 100.0 * (1 - ok / sent) if sent else 100.0
    return {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "mode": mode, "freq_mhz": freq, "power_dbm": power, "att_db": att,
            "p_rx_dbm": power - att, "sent": sent, "rx_ok": ok, "rx_bad": bad, "loss_pct": round(loss, 1), "rssi": rxsum.get("rssi", float("nan")),
            "snr": rxsum.get("snr", float("nan")), "fei_hz": rxsum.get("fei_hz", float("nan")), "toa_mean_us": txsum.get("toa_mean_us", 0),
            "toa_calc_us": txsum.get("calc_us", 0)}


# ---------- Risultati ----------
def save_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = []
        for r in csv.DictReader(fh):
            for k in ("freq_mhz", "power_dbm", "att_db", "p_rx_dbm", "loss_pct", "rssi", "snr", "fei_hz", "toa_mean_us", "toa_calc_us"):
                try:
                    r[k] = float(r[k])
                except (KeyError, ValueError):
                    r[k] = float("nan")
            for k in ("sent", "rx_ok", "rx_bad"):
                r[k] = int(float(r.get(k) or 0))
            rows.append(r)
        return rows


def sensitivities(rows, threshold=10.0):
    """Per ogni modo, la potenza ricevuta piu' bassa con perdita <= soglia, e la differenza dalla stima dello studio."""
    best = {}
    for r in rows:
        if r["loss_pct"] <= threshold and (r["mode"] not in best or r["p_rx_dbm"] < best[r["mode"]]):
            best[r["mode"]] = r["p_rx_dbm"]
    return {m: (p, p - sens_estimate(m)) for m, p in best.items()}


def results_markdown(rows, callsign, board_a, board_b, firmware, notes=""):
    """Pagina di note per un invio su GitHub."""
    lines = [f"# Misure di {callsign} del {time.strftime('%Y-%m-%d')}", "",
             f"- Scheda A: {board_a}", f"- Scheda B: {board_b}", f"- Firmware: {firmware}", ""]
    if notes:
        lines += ["## Note", notes, ""]
    lines += ["## Risultati", "", "| modo | att. dB | P rx dBm | inviati | ricevuti | perdita % | RSSI | SNR | fei Hz |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['mode']} | {r['att_db']:g} | {r['p_rx_dbm']:g} | {r['sent']} | {r['rx_ok']} | {r['loss_pct']:g} | {r['rssi']:.1f} | {r['snr']:.1f} | {r['fei_hz']:.0f} |")
    s = sensitivities(rows)
    if s:
        lines += ["", "## Sensibilità (perdita <= 10 %)", ""]
        for m in sorted(s, key=lambda x: (x[0], int(x[1:]))):
            lines.append(f"- {m}: {s[m][0]:.0f} dBm (stima dello studio {sens_estimate(m):.0f} dBm, differenza {s[m][1]:+.0f} dB)")
    return "\n".join(lines) + "\n"


# ---------- GitHub ----------
def issue_url(repo, title, body, max_url=7000):
    """Indirizzo della pagina 'nuova segnalazione' precompilata (nessun token). Il corpo si accorcia se l'indirizzo e' troppo lungo."""
    def make(b):
        return f"https://github.com/{repo}/issues/new?" + urllib.parse.urlencode({"title": title, "body": b}, quote_via=urllib.parse.quote)
    url = make(body)
    cut = False
    while len(url) > max_url and body:
        body = body[: int(len(body) * 0.9)]
        cut = True
        url = make(body + "\n\n(testo accorciato: allega il file CSV)")
    return url


def safe_name(s):
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in s)[:40] or "misure"


def upload_to_github(token, repo, base_branch, files, callsign, http):
    """Carica i file in docs/misure/ su un nuovo ramo e apre una richiesta di modifica (PR). `files` = {nome: bytes}.
    `http(metodo, url, token, dizionario_json) -> (codice, dizionario)` e' iniettato (provato senza rete). Ritorna l'indirizzo della PR."""
    api = f"https://api.github.com/repos/{repo}"
    code, ref = http("GET", f"{api}/git/ref/heads/{base_branch}", token, None)
    if code != 200:
        raise RuntimeError(f"ramo {base_branch} non trovato ({code}): {ref.get('message', '')}")
    sha = ref["object"]["sha"]
    branch = f"misure/{safe_name(callsign)}-{time.strftime('%Y%m%d-%H%M%S')}"
    code, r = http("POST", f"{api}/git/refs", token, {"ref": f"refs/heads/{branch}", "sha": sha})
    if code not in (200, 201):
        raise RuntimeError(f"creazione del ramo non riuscita ({code}): {r.get('message', '')}. Serve un token con permesso di scrittura sul repository.")
    for name, data in files.items():
        code, r = http("PUT", f"{api}/contents/docs/misure/{name}", token,
                       {"message": f"Misure di {callsign}: {name}", "content": base64.b64encode(data).decode(), "branch": branch})
        if code not in (200, 201):
            raise RuntimeError(f"caricamento di {name} non riuscito ({code}): {r.get('message', '')}")
    code, pr = http("POST", f"{api}/pulls", token, {"title": f"Misure di {callsign}", "head": branch, "base": base_branch,
                                                    "body": "Misure caricate dall'applicazione di prova (docs/misure/)."})
    if code not in (200, 201):
        raise RuntimeError(f"apertura della richiesta di modifica non riuscita ({code}): {pr.get('message', '')}")
    return pr["html_url"]


def urllib_http(method, url, token, payload):
    """Implementazione vera dell'accesso a GitHub (non provata senza token e senza rete)."""
    import urllib.error
    import urllib.request
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                                                        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "volora-misure"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except ValueError:
            return e.code, {}


# ---------- Immagini fittizie ----------
def make_blob(size, seed=1):
    """Blocco di prova (oggetto di tipo 0): `size` byte pseudocasuali riproducibili, gli ultimi 4 sono il CRC32 del resto."""
    if size < 8:
        raise ValueError("almeno 8 byte")
    rng = random.Random(seed)
    body = bytes(rng.getrandbits(8) for _ in range(size - 4))
    return body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def check_blob(data):
    return len(data) >= 8 and struct.pack(">I", zlib.crc32(data[:-4]) & 0xFFFFFFFF) == data[-4:]


def _png_chunk(tag, payload):
    return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)


def make_test_png(width, height, label=""):
    """Immagine di prova PNG (scala di grigi 8 bit): gradiente, griglia, cerchio e barre; larghezza e altezza a scelta."""
    if not (8 <= width <= 2048 and 8 <= height <= 2048):
        raise ValueError("larghezza e altezza da 8 a 2048")
    cx, cy, rad = width / 2.0, height / 2.0, min(width, height) / 3.0
    rows = []
    for y in range(height):
        row = bytearray([0])  # filtro nessuno
        for x in range(width):
            v = int(255 * x / max(1, width - 1))
            if x % max(8, width // 8) == 0 or y % max(8, height // 8) == 0:
                v = 255 - v
            if (x - cx) ** 2 + (y - cy) ** 2 <= rad ** 2 and (x - cx) ** 2 + (y - cy) ** 2 >= (rad - 3) ** 2:
                v = 0 if v > 127 else 255
            if y > height - max(4, height // 10):
                v = 255 if (x * 8 // width) % 2 == 0 else 0
            row.append(v)
        rows.append(bytes(row))
    raw = b"".join(rows)
    return (b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)) +
            _png_chunk(b"IDAT", zlib.compress(raw, 9)) + _png_chunk(b"IEND", b""))


def make_test_jpeg(width, height, quality=60):
    """JPEG progressivo di prova (serve Pillow: se manca ritorna None)."""
    try:
        from PIL import Image
    except ImportError:
        return None
    import io
    img = Image.open(io.BytesIO(make_test_png(width, height))).convert("L")
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality, progressive=True)
    return out.getvalue()


def estimate_rows(nbytes, chip="SX1278"):
    """(gradino, tempo stimato in testo) per ogni gradino del protocollo immagini."""
    return [(f"R{rid} {name}", pi.fmt_time(pi.estimate_seconds(nbytes, rid, chip))) for rid, _, _, name in pi.RUNGS]


# ---------- Impostazioni ----------
def config_path():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "volora-misure", "config.json")


def load_config():
    try:
        with open(config_path(), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_config(cfg, token_remember=False):
    cfg = dict(cfg)
    if not token_remember:
        cfg.pop("token", None)
    p = config_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
