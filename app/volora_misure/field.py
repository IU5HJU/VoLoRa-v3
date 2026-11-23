"""Prove sul campo con una scheda per stazione: righe di scambio fra i due colleghi, unione dei risultati e CSV di rilievo.
Provato in tests/app/test_field.py."""
import math

from . import geo, timesync

RILIEVO_FIELDS = ["data_ora", "nominativo_A", "locatore_A", "altezza_A_m", "nominativo_B", "locatore_B", "altezza_B_m", "distanza_km", "percorso",
                  "scheda_A", "scheda_B", "firmware", "antenna_A", "antenna_B", "ros_A", "ros_B", "freq_mhz", "modo", "potenza_impostata_dbm",
                  "potenza_misurata_dbm", "attenuatore_db", "meteo", "inviati", "ricevuti", "rovinati", "rssi_medio", "snr_medio", "fei_hz", "note"]

MAGIC = "VOLORA-PROVA"


def _f(v, nd=2):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    return f"{v:.{nd}f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def export_line(run):
    """Riga di testo con i dati della mia stazione e della mia prova, da mandare al collega (a voce, per radio o per messaggio)."""
    parts = [MAGIC, "1", f"call={run.get('my_call', '')}", f"loc={run.get('my_loc', '')}"]
    if run.get("my_lat") is not None:
        parts += [f"lat={run['my_lat']:.5f}", f"lon={run['my_lon']:.5f}"]
    parts += [f"t0={timesync.fmt_utc(run['t0'], ms=False).replace(' UTC', '').replace(' ', 'T')}Z", f"role={run['role']}", f"mode={run.get('mode', '')}",
              f"freq={_f(run.get('freq_mhz'), 4)}", f"power={_f(run.get('power_dbm'))}", f"att={_f(run.get('att_db'))}"]
    for k, key in (("sent", "sent"), ("ok", "rx_ok"), ("bad", "rx_bad"), ("rssi", "rssi"), ("snr", "snr"), ("fei", "fei_hz")):
        if run.get(key) not in (None, ""):
            v = run[key]
            if isinstance(v, float) and math.isnan(v):
                continue
            parts.append(f"{k}={_f(v, 1) if isinstance(v, float) else v}")
    if run.get("clock_src"):
        parts.append(f"clock={run['clock_src']}/{_f(run.get('clock_unc_s'), 3)}")
    return " ".join(parts)


def import_line(text):
    """Legge una riga di export_line del collega. Ritorna un dizionario con i campi (numeri convertiti) o solleva ValueError."""
    t = text.strip().replace("\n", " ")
    if MAGIC not in t:
        raise ValueError("non e' una riga di dati del collega (manca " + MAGIC + ")")
    t = t[t.index(MAGIC):]
    toks = t.split()
    if len(toks) < 3 or toks[1] != "1":
        raise ValueError("versione del formato non riconosciuta")
    d = {}
    for tok in toks[2:]:
        if "=" in tok:
            k, v = tok.split("=", 1)
            d[k] = v
    if "role" not in d or d["role"] not in ("TX", "RX") or "call" not in d:
        raise ValueError("mancano nominativo o ruolo")
    out = {"call": d["call"], "loc": d.get("loc", ""), "role": d["role"], "mode": d.get("mode", "")}
    for k in ("lat", "lon", "freq", "power", "att", "rssi", "snr", "fei"):
        if k in d and d[k] != "":
            try:
                out[k] = float(d[k])
            except ValueError:
                raise ValueError(f"valore non numerico: {k}={d[k]}")
    for k in ("sent", "ok", "bad"):
        if k in d and d[k] != "":
            out[k] = int(float(d[k]))
    if "t0" in d:
        out["t0"] = timesync.parse_utc(d["t0"])
    if "clock" in d:
        out["clock"] = d["clock"]
    return out


def import_lines(text):
    """Piu' righe VOLORA-PROVA incollate insieme -> lista di dizionari (le righe non valide sono ignorate)."""
    out = []
    for ln in text.replace(MAGIC, "\n" + MAGIC).splitlines():
        if MAGIC in ln:
            try:
                out.append(import_line(ln))
            except ValueError:
                pass
    return out


def find_match(runs, remote, tol_s=5.0):
    """Indice della mia prova a cui appartiene la riga del collega: stesso modo, T0 entro `tol_s`, ruolo opposto e non ancora unita; None se non c'e'."""
    for i, r in enumerate(runs):
        if r.get("remote_call"):
            continue
        if r.get("role") == remote["role"]:
            continue
        if remote.get("mode") and r.get("mode") != remote["mode"]:
            continue
        if "t0" in remote and abs(remote["t0"] - r["t0"]) > tol_s:
            continue
        return i
    return None


def my_position(run_or_pos):
    return run_or_pos.get("my_lat"), run_or_pos.get("my_lon")


def merge(run, remote):
    """Unisce la riga del collega alla mia prova. Ritorna (prova_unita, avvisi). Non modifica `run`."""
    r = dict(run)
    warn = []
    if remote["role"] == run["role"]:
        warn.append(f"anche il collega ha il ruolo {remote['role']}: una stazione deve trasmettere e l'altra ricevere")
    r["remote_call"] = remote["call"]
    r["remote_loc"] = remote.get("loc", "")
    rl, rn = remote.get("lat"), remote.get("lon")
    if rl is None and remote.get("loc"):
        try:
            rl, rn = geo.from_maidenhead(remote["loc"])
            warn.append("posizione del collega ricavata dal locatore (centro del quadrato): la distanza e' approssimata")
        except ValueError:
            pass
    r["remote_lat"], r["remote_lon"] = rl, rn
    if r.get("my_lat") is not None and rl is not None:
        r["distance_km"] = geo.haversine_km(r["my_lat"], r["my_lon"], rl, rn)
        r["bearing_deg"] = geo.bearing_deg(r["my_lat"], r["my_lon"], rl, rn)
    if "t0" in remote and abs(remote["t0"] - run["t0"]) > 5.0:
        warn.append(f"gli orari di partenza differiscono di {abs(remote['t0'] - run['t0']):.1f} s: e' la stessa prova?")
    if remote.get("mode") and run.get("mode") and remote["mode"] != run["mode"]:
        warn.append(f"modi diversi: tu {run['mode']}, collega {remote['mode']}")
    if remote.get("freq") is not None and run.get("freq_mhz") is not None and abs(remote["freq"] - run["freq_mhz"]) > 0.0005:
        warn.append(f"frequenze diverse: tu {run['freq_mhz']}, collega {remote['freq']}")
    if run["role"] == "TX" and remote["role"] == "RX":
        r["rx_ok"], r["rx_bad"] = remote.get("ok", 0), remote.get("bad", 0)
        for a, b in (("rssi", "rssi"), ("snr", "snr"), ("fei_hz", "fei")):
            if b in remote:
                r[a] = remote[b]
    elif run["role"] == "RX" and remote["role"] == "TX":
        if "sent" in remote:
            r["sent"] = remote["sent"]
        if "att" in remote and r.get("att_db") in (None, ""):
            r["att_db"] = remote["att"]
    sent, ok = r.get("sent"), r.get("rx_ok")
    if sent and ok is not None:
        r["loss_pct"] = round(100.0 * (1 - min(ok, sent) / sent), 1)
        if ok > sent:
            warn.append("il collega ha ricevuto piu' pacchetti di quanti ne hai inviati: controlla i conteggi")
    elif sent is None or ok is None:
        warn.append("mancano i pacchetti inviati o quelli ricevuti: la perdita non si puo' calcolare")
    r["merged"] = True
    return r, warn


def to_rilievo_row(run, extra=None):
    """Riga del CSV di rilievo (docs/misure/modello-rilievo.csv). A = stazione che trasmette, B = stazione che riceve."""
    extra = extra or {}
    me_tx = run["role"] == "TX"
    mine = {"call": run.get("my_call", ""), "loc": run.get("my_loc", ""), "alt": run.get("my_alt")}
    other = {"call": run.get("remote_call", ""), "loc": run.get("remote_loc", ""), "alt": extra.get("remote_alt")}
    a, b = (mine, other) if me_tx else (other, mine)
    row = {"data_ora": timesync.fmt_utc(run["t0"], ms=False).replace(" UTC", "Z").replace(" ", "T"),
           "nominativo_A": a["call"], "locatore_A": a["loc"], "altezza_A_m": _f(a["alt"], 1),
           "nominativo_B": b["call"], "locatore_B": b["loc"], "altezza_B_m": _f(b["alt"], 1),
           "distanza_km": _f(run.get("distance_km"), 3), "percorso": extra.get("percorso", ""),
           "scheda_A": extra.get("scheda_A", ""), "scheda_B": extra.get("scheda_B", ""), "firmware": extra.get("firmware", "misura 0.1.0"),
           "antenna_A": extra.get("antenna_A", ""), "antenna_B": extra.get("antenna_B", ""), "ros_A": extra.get("ros_A", ""), "ros_B": extra.get("ros_B", ""),
           "freq_mhz": _f(run.get("freq_mhz"), 4), "modo": run.get("mode", ""), "potenza_impostata_dbm": _f(run.get("power_dbm")),
           "potenza_misurata_dbm": extra.get("potenza_misurata", ""), "attenuatore_db": _f(run.get("att_db")), "meteo": extra.get("meteo", ""),
           "inviati": _f(run.get("sent")), "ricevuti": _f(run.get("rx_ok")), "rovinati": _f(run.get("rx_bad")), "rssi_medio": _f(run.get("rssi"), 1),
           "snr_medio": _f(run.get("snr"), 1), "fei_hz": _f(run.get("fei_hz"), 0),
           "note": (extra.get("note", "") + (" | " if extra.get("note") else "") + f"orologio {run.get('clock_src', '?')} +-{_f(run.get('clock_unc_s'), 3)} s, "
                    f"errore di partenza {_f(run.get('start_err_ms'), 0)} ms").strip()}
    return row
