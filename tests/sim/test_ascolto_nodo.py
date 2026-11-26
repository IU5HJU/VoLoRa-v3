"""Prove dell'ascolto del nodo a scheda singola: python3 -I tests/sim/test_ascolto_nodo.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import ascolto_nodo as an  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


a = an.Ascolto(slot_v2_s=2.0, slot_v3_s=2.0, attesa_min=10)
seq = [a.modo(t) for t in (0.0, 1.9, 2.0, 3.9, 4.0, 6.1)]
check(seq == ["turni_v2", "turni_v2", "turni_v3", "turni_v3", "turni_v2", "turni_v3"], f"a riposo l'ascolto alterna v2 e V3 a turni dall'orologio: {seq}")
check(a.profilo(1.0) == "v2" and a.profilo(3.0) == "v3", "profilo radio da ascoltare nei due turni")
a.on_v2_voce(100.0)
check(a.modo(101.0) == "v2" and a.qso_in_corso(101.0) and not a.qso_in_corso(104.0), "con voce v2 il nodo resta in modo v2; il QSO e' finito dopo 3 s di silenzio")
check(a.modo(100.0 + 3.0 + 600.0) == "v2" and a.modo(100.0 + 3.0 + 600.1) in ("turni_v2", "turni_v3"), "resta in v2 per l'attesa dopo il QSO (10 minuti), poi torna ai turni")
a.on_internet_voce(5000.0)
check(a.modo(5002.0) == "v2", "anche la voce dalla rete tiene il nodo in modo v2")
b = an.Ascolto(attesa_min=1, lock=True)
check(b.modo(10.0) == "v2_lock" and b.modo(100000.0) == "v2_lock", "con il lock il nodo resta in v2 senza limite di tempo")
b.set_lock(False)
check(b.modo(100000.0) in ("turni_v2", "turni_v3"), "sbloccato (seriale, web o comando SYSOP): torna ai turni")
for bad in (0, 256):
    try:
        an.Ascolto(attesa_min=bad)
        check(False, f"attesa {bad} minuti: errore")
    except ValueError:
        pass
check(True, "l'attesa a fine QSO deve stare fra 1 e 255 minuti")
c = an.Ascolto(forza_v3_da=0, lock=True)
check(c.on_comando_v3(10.0, 30.0) is False and c.on_comando_v3(10.0, 30.0, "nodo") is False and c.modo(11.0) == "v2_lock", "senza il consenso della configurazione il comando di una mobile V3 o di un altro nodo non fa nulla")
d = an.Ascolto(forza_v3_da=an.FORZA_MOBILE, lock=True)
check(d.on_comando_v3(10.0, 30.0) is True and d.modo(20.0) == "v3_forzato" and d.profilo(20.0) == "v3" and d.modo(40.1) == "v2_lock", "col consenso la mobile V3 forza l'invio di immagini anche in modo v2 con lock, poi il nodo torna in v2")
check(an.Ascolto(forza_v3_da=an.FORZA_MOBILE).on_comando_v3(1.0, 5.0, "nodo") is False and an.Ascolto(forza_v3_da=an.FORZA_NODO).on_comando_v3(1.0, 5.0, "nodo") is True and an.Ascolto(forza_v3_da=3).on_comando_v3(1.0, 5.0, "nodo") is True,
      "l'origine conta: il consenso alla mobile non vale per un altro nodo, e viceversa; con 3 valgono entrambi")
e = an.Ascolto(forza_v3_da=3)
e.on_v2_voce(50.0)
check(e.on_comando_v3(51.0, 30.0) is False and e.on_comando_v3(60.0, 30.0, "nodo") is True, "mai a QSO in corso: rifiutato con la voce in onda, accettato dopo 3 s di silenzio")
print("ascolto del nodo: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
