#!/usr/bin/env python3
"""Calcoli sul tempo GPS: numero di settimana, valore trasmesso a 10 bit, date dei rollover e correzione di una data sbagliata.
Spiegazione in docs/gps-tempo.md.

  python3 tools/gps_settimana.py 2026-11-22
  python3 tools/gps_settimana.py --correggi 2007-04-08 --riferimento 2026-11-22
"""
import argparse
import datetime as dt

ORIGINE = dt.date(1980, 1, 6)       # inizio del tempo GPS (domenica)
CICLO_SETTIMANE = 1024              # 10 bit
CICLO = dt.timedelta(weeks=CICLO_SETTIMANE)


def settimana(d):
    """Numero di settimana GPS completo e valore a 10 bit (quello che trasmette il messaggio di navigazione tradizionale)."""
    n = (d - ORIGINE).days // 7
    return n, n % CICLO_SETTIMANE


def rollover(k):
    """Data del k-esimo rollover (k = 1, 2, 3...)."""
    return ORIGINE + CICLO * k


def correggi(data_gps, riferimento, tolleranza_giorni=2):
    """Riporta una data GPS al giro giusto: aggiunge n cicli da 1024 settimane se cosi' arriva entro la tolleranza dal riferimento."""
    diff = (riferimento - data_gps).days
    n = round(diff / CICLO.days)
    if n >= 1 and abs(diff - n * CICLO.days) <= tolleranza_giorni:
        return data_gps + CICLO * n, n
    return data_gps, 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data", nargs="?", help="data AAAA-MM-GG di cui calcolare la settimana GPS")
    ap.add_argument("--correggi", help="data data dal ricevitore (AAAA-MM-GG) da riportare al giro giusto")
    ap.add_argument("--riferimento", help="data certa (di solito quella del computer), per --correggi")
    a = ap.parse_args()
    if a.correggi:
        ref = dt.date.fromisoformat(a.riferimento) if a.riferimento else dt.date.today()
        d, n = correggi(dt.date.fromisoformat(a.correggi), ref)
        print(f"{a.correggi} -> {d} ({n} cicli da 1024 settimane aggiunti)" if n else f"{a.correggi}: nessun rollover da correggere rispetto a {ref}")
        return
    d = dt.date.fromisoformat(a.data) if a.data else dt.date.today()
    n, m = settimana(d)
    print(f"{d} ({d.strftime('%A')}): settimana GPS {n}, trasmessa (mod 1024) = {m}")
    print("rollover: " + ", ".join(f"{k}o {rollover(k)}" for k in (1, 2, 3)))
    print(f"stesso valore trasmesso, un giro prima: {d - CICLO} ({(d - CICLO).strftime('%A')}), un giro dopo: {d + CICLO}")


if __name__ == "__main__":
    main()
