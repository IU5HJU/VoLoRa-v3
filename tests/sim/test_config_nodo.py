"""Prove della configurazione del nodo: python3 -I tests/sim/test_config_nodo.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import canali as ch  # noqa: E402
import config_nodo as cn  # noqa: E402
import frame_mesh as fm  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


base = cn.NodeConfig("IU5HJU", reflector_v2="reflector.example.org")
e, w = cn.validate(base)
check(e == [] and any("reflector V3" in x for x in w), f"nodo di partenza (scheda singola, gateway v2 e V3): valido, avvisi: {len(w)}")
check(cn.validate(cn.NodeConfig("IU5HJU", topologia="singola", freq_voto_khz=144900))[0] != [], "scheda singola con la frequenza del voto: errore")
check(any("un profilo alla volta" in x for x in cn.validate(cn.NodeConfig("IU5HJU", profilo_v2="range"))[1]), "scheda singola con la voce dal vivo v2: avviso sull'ascolto di un solo profilo")
d = cn.NodeConfig("IU5HJU", topologia="doppia", freq_voto_khz=144900, reflector_v2="x")
check(cn.validate(d)[0] == [], "doppia con voto a 144,900 MHz e SX1278: valida")
check(cn.validate(cn.NodeConfig("IU5HJU", topologia="doppia", freq_voto_khz=144900, chip_servizio="SX1262"))[0] != [], "voto a 144,900 MHz con SX1262: errore (parte da 150 MHz)")
check(cn.validate(cn.NodeConfig("IU5HJU", topologia="doppia", freq_voto_khz=433850, chip_servizio="SX1262", reflector_v2="x"))[0] == [], "voto a 433,850 MHz con SX1262: valida")
check(cn.validate(cn.NodeConfig("IU5HJU", topologia="doppia"))[0] != [] and cn.validate(cn.NodeConfig("IU5HJU", topologia="doppia", freq_voto_khz=433700))[0] != [], "doppia senza voto o con il voto sulla frequenza del nodo: errore")
t = cn.NodeConfig("IU5HJU", topologia="tripla", freq_voto_khz=144900, freq_veloce_khz=2424000, air_code_veloce=3, reflector_v2="x")
check(cn.validate(t)[0] == [], "tripla con 2424 MHz a 10k: valida")
check(cn.validate(cn.NodeConfig("IU5HJU", topologia="tripla", freq_voto_khz=144900, freq_veloce_khz=2450500))[0] != [] and cn.validate(cn.NodeConfig("IU5HJU", topologia="tripla", freq_voto_khz=144900, freq_veloce_khz=2423500))[0] != [], "tripla con 2 4 GHz fuori banda o fuori dalla griglia del modulo: errore")
check(cn.validate(cn.NodeConfig("IU5HJU", topologia="doppia", freq_voto_khz=144900, freq_veloce_khz=2424000))[0] != [], "doppia con il 2,4 GHz: errore (serve la tripla)")
check(cn.caps(base) == cn.CAP_GW_V2 | cn.CAP_GW_V3 and cn.caps(t) == ch.CAP_SERVICE_2M | cn.CAP_FAST_2G4 | cn.CAP_GW_V2 | cn.CAP_GW_V3 and cn.caps(cn.NodeConfig("X1X", v2_ruolo="pappagallo", v3_ruolo="pappagallo")) == 0,
      "capacita' annunciate nel frame NODO (voto, 2,4 GHz, gateway v2, gateway V3)")
check(len(fm.enc_node_info("IU5HJU", 1, 144900, cn.caps(t))) == 14, "le capacita' entrano nel frame NODO (un byte)")
tab = {(r2, r3, i): (cn.azione(cn.NodeConfig("IU5HJU", v2_ruolo=r2, v3_ruolo=r3), "v2", i), cn.azione(cn.NodeConfig("IU5HJU", v2_ruolo=r2, v3_ruolo=r3), "v3", i))
       for r2 in cn.RUOLI for r3 in cn.RUOLI for i in (True, False)}
check(tab[("gateway", "gateway", True)] == ("gateway_v2", "reflector_v3"), "gateway + Internet: v2 come un nodo v2, V3 al reflector V3")
check(tab[("gateway", "gateway", False)] == ("pappagallo", "mesh"), "gateway senza Internet: v2 pappagallo, V3 nella rete mesh")
check(tab[("gateway", "pappagallo", True)] == ("gateway_v2", "pappagallo"), "gateway solo per la v2: il V3 resta pappagallo")
check(tab[("pappagallo", "gateway", True)] == ("pappagallo", "reflector_v3"), "gateway solo per il V3: la v2 resta pappagallo")
check(tab[("pappagallo", "pappagallo", True)] == ("pappagallo", "pappagallo") and tab[("pappagallo", "pappagallo", False)] == ("pappagallo", "pappagallo"), "nodo isolato: sempre pappagallo, con o senza Internet")
check(cn.from_json(cn.to_json(t)) == t, "la configurazione si salva e si rilegge (JSON)")
check(cn.validate(cn.NodeConfig("IU5HJU", attesa_fine_qso_min=0))[0] != [] and cn.validate(cn.NodeConfig("IU5HJU", attesa_fine_qso_min=256))[0] != [] and cn.validate(cn.NodeConfig("IU5HJU", attesa_fine_qso_min=255))[0] == [], "attesa a fine QSO: da 1 a 255 minuti")
cl = cn.NodeConfig("IU5HJU", lock_v2=True, consenti_forza_v3=True, attesa_fine_qso_min=30)
asc = cn.ascolto(cl)
check(asc.modo(10.0) == "v2_lock" and asc.consenti_forza_v3 and asc.attesa_s == 1800.0, "la configurazione del nodo comanda l'ascolto (lock, comando della mobile V3, attesa)")
print("configurazione del nodo: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
