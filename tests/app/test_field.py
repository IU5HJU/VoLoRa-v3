"""Prove delle righe di scambio, dell'unione e del CSV di rilievo: python3 -I tests/app/test_field.py"""
import csv
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "app"))
from volora_misure import field, geo, timesync as ts  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


t0 = ts.parse_utc("2026-11-22T10:30:00Z")
tx = dict(role="TX", t0=t0, my_call="IU5HJU", my_loc="JN53ps", my_lat=43.7696, my_lon=11.2558, my_alt=95.0, mode="L4", freq_mhz=433.475,
          power_dbm=2, att_db=0.0, sent=200, clock_src="gps-pps", clock_unc_s=0.005, start_err_ms=3.0)
line = field.export_line(tx)
check(line.startswith("VOLORA-PROVA 1 ") and "call=IU5HJU" in line and "t0=2026-11-22T10:30:00Z" in line and "sent=200" in line and "lat=43.76960" in line, "riga di scambio del trasmettitore: " + line)
back = field.import_line("messaggio del collega:\n" + line + "\nciao")
check(back["call"] == "IU5HJU" and back["role"] == "TX" and back["sent"] == 200 and abs(back["lat"] - 43.7696) < 1e-6 and back["t0"] == t0 and back["mode"] == "L4", "lettura della riga, anche dentro altro testo")
for bad in ("niente", "VOLORA-PROVA 2 call=A role=TX", "VOLORA-PROVA 1 call=A", "VOLORA-PROVA 1 call=A role=TX lat=abc"):
    try:
        field.import_line(bad)
        check(False, "riga non valida accettata: " + bad)
    except ValueError:
        pass
check(True, "righe non valide rifiutate con un errore")

# io ricevo, il collega ha trasmesso
rx = dict(role="RX", t0=t0 + 0.4, my_call="IK5XYZ", my_loc="JN54ab", my_lat=44.0, my_lon=11.9, my_alt=40.0, mode="L4", freq_mhz=433.475, power_dbm=2,
          att_db=None, rx_ok=190, rx_bad=2, rssi=-111.2, snr=-4.5, fei_hz=-35.0, clock_src="ntp", clock_unc_s=0.004, start_err_ms=8.0)
m, w = field.merge(rx, field.import_line(line))
d_exp = geo.haversine_km(44.0, 11.9, 43.7696, 11.2558)
check(m["sent"] == 200 and m["loss_pct"] == 5.0 and abs(m["distance_km"] - d_exp) < 1e-9 and 40 < m["distance_km"] < 70 and not w, f"RX unisce il TX: perdita 5 %, distanza {m['distance_km']:.1f} km, senza avvisi")
check(m["remote_call"] == "IU5HJU" and 0 <= m["bearing_deg"] < 360, "RX: nominativo e direzione del collega")
# io trasmetto, il collega ha ricevuto
rline = field.export_line(rx)
check("ok=190" in rline and "bad=2" in rline and "rssi=-111.2" in rline and "fei=-35" in rline and "clock=ntp/0.004" in rline, "riga del ricevitore: " + rline)
m2, w2 = field.merge(tx, field.import_line(rline))
check(m2["rx_ok"] == 190 and m2["rx_bad"] == 2 and m2["rssi"] == -111.2 and m2["loss_pct"] == 5.0 and not w2, f"TX unisce l'RX: perdita {m2['loss_pct']} %, nessun avviso ({w2})")
check(abs(m2["distance_km"] - d_exp) < 1e-9, "stessa distanza da entrambe le parti")
check("rx_ok" not in tx, "l'unione non modifica la prova originale")
# avvisi
_, w3 = field.merge(tx, field.import_line(line))
check(any("stesso" in x or "ruolo" in x for x in w3), "due trasmettitori: avviso")
other = dict(rx, t0=t0 + 30, mode="L5", freq_mhz=433.9)
_, w4 = field.merge(tx, field.import_line(field.export_line(other)))
check(any("orari" in x for x in w4) and any("modi diversi" in x for x in w4) and any("frequenze" in x for x in w4), f"prove diverse: avvisi su orario, modo e frequenza ({len(w4)})")
over = dict(rx, rx_ok=250)
m5, w5 = field.merge(tx, field.import_line(field.export_line(over)))
check(any("piu' pacchetti" in x for x in w5) and m5["loss_pct"] == 0.0, "ricevuti piu' dei trasmessi: avviso")
noloc = field.import_line("VOLORA-PROVA 1 call=IK5XYZ loc=JN54ab role=RX ok=100 bad=0")
m6, w6 = field.merge(tx, noloc)
check(any("locatore" in x for x in w6) and m6["distance_km"] > 0, f"senza coordinate: distanza dal locatore ({m6['distance_km']:.1f} km) con avviso")
# CSV di rilievo
row = field.to_rilievo_row(m2, {"percorso": "in vista", "meteo": "sereno", "scheda_A": "T3", "scheda_B": "T3", "note": "prova"})
check(row["nominativo_A"] == "IU5HJU" and row["nominativo_B"] == "IK5XYZ" and row["locatore_B"] == "JN54ab", "CSV: A trasmette e B riceve (io TX)")
row2 = field.to_rilievo_row(m)
check(row2["nominativo_A"] == "IU5HJU" and row2["nominativo_B"] == "IK5XYZ" and row2["inviati"] == "200" and row2["ricevuti"] == "190", "CSV: stessa assegnazione se io sono RX")
check(row["data_ora"] == "2026-11-22T10:30:00Z" and row["inviati"] == "200" and row["rssi_medio"] == "-111.2" and "gps-pps" in row["note"], "CSV: orario, conteggi, nota con la sorgente dell'orologio")
check(list(row) == field.RILIEVO_FIELDS, "le colonne sono quelle di docs/misure/modello-rilievo.csv")
hdr = open(os.path.join(HERE, "..", "..", "docs", "misure", "modello-rilievo.csv"), encoding="utf-8").readline().strip().split(",")
check(hdr == field.RILIEVO_FIELDS, "e coincidono con l'intestazione del modello nel repository")
buf = io.StringIO()
w = csv.DictWriter(buf, field.RILIEVO_FIELDS)
w.writeheader(); w.writerow(row)
check(buf.getvalue().count("\n") == 2, "CSV scrivibile")
# piu' righe del collega e abbinamento per modo e T0
mine = [dict(role="TX", t0=1000.0, mode="L10"), dict(role="TX", t0=1100.0, mode="L11")]
rem_txt = field.export_line(dict(role="RX", t0=1100.2, my_call="IK5XYZ", mode="L11", freq_mhz=433.475, rx_ok=4)) + "\n" + field.export_line(dict(role="RX", t0=1000.0, my_call="IK5XYZ", mode="L10", rx_ok=9))
lines = field.import_lines("ciao " + rem_txt + " fine")
check(len(lines) == 2 and field.find_match(mine, lines[0]) == 1 and field.find_match(mine, lines[1]) == 0, "piu' righe: ognuna trova la prova con lo stesso modo e T0")
mine[1]["remote_call"] = "IK5XYZ"
check(field.find_match(mine, lines[0]) is None, "una prova gia' unita non viene riabbinata")
print("prove sul campo: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
