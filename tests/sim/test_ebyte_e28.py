"""Prove dei parametri del modulo Ebyte E28-2G4T27SX: python3 -I tests/sim/test_ebyte_e28.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import ebyte_e28 as eb  # noqa: E402

fails = 0


def check(c, m):
    global fails
    print(("ok: " if c else "FALLITO: ") + m)
    if not c:
        fails += 1


ex = bytes.fromhex("C000001318" "04")                     # esempio di risposta del manuale (pag. 11): C0 00 00 13 18 04
cfg = eb.parse_config(ex)
check(cfg == {"addr": 0, "parity": "8N1", "baud": 9600, "air_code": 3, "chan": 0x18, "fixed": False, "lbt": False, "push_pull": True, "power_dbm": 27},
      f"esempio del manuale C0 00 00 13 18 04: {eb.describe(cfg)}")
check(eb.build_config() == ex, "build_config con i valori di fabbrica ricostruisce esattamente l'esempio del manuale")
c2 = eb.build_config(addr=0x1234, parity="8E1", baud=115200, air_code=6, chan=7, fixed=True, lbt=True, push_pull=False, power_dbm=20, save=False)
p = eb.parse_config(c2)
check(c2[0] == 0xC2 and p == {"addr": 0x1234, "parity": "8E1", "baud": 115200, "air_code": 6, "chan": 7, "fixed": True, "lbt": True, "push_pull": False, "power_dbm": 20},
      "andata e ritorno di tutti i campi (parita', baud, FLRC 1M, canale, trasmissione fissa, LBT, 20 dBm, non salvare)")
check(eb.channel_mhz(0x18, 3) == 2424 and eb.channel_mhz(10, 1) == 2410 and eb.channel_mhz(10, 4) == 2420 and eb.channel_mhz(10, 6) == 2430 and eb.channel_mhz(10, 7) == 2450,
      "canale: 2400 + CHAN x passo (1 MHz a 1k/5k/10k, 2 a 50k/100k, 3 a 1M, 5 a 2M); il canale di fabbrica 0x18 e' 2424 MHz")
check(eb.max_channel(3) == 100 and eb.max_channel(7) == 20, "l'ultimo canale resta dentro 2400-2500 MHz")
check(eb.channel_step_mhz(0, 9600) == 2 and eb.channel_step_mhz(0, 115200) == 4 and eb.channel_step_mhz(0, 921600) == 5, "trasmissione continua: il passo dipende dal baud")
check(eb.contains_forbidden(b"abc\xe2\xe2\xe2z") and eb.contains_forbidden(b"\xe3\xe3\xe3") and not eb.contains_forbidden(b"\xe2\xe2\xe3\xe3\xe2"), "le sequenze E2 E2 E2 e E3 E3 E3 si riconoscono")
for bad in (dict(baud=12345), dict(parity="7E1"), dict(air_code=9), dict(power_dbm=10)):
    try:
        eb.build_config(**bad)
        check(False, f"parametro non valido {bad}: errore")
    except ValueError:
        pass
check(True, "parametri non validi: errore")
try:
    eb.parse_config(b"\x00" * 6)
    check(False, "risposta non valida: errore")
except ValueError:
    check(True, "risposta non valida: errore")
print("modulo Ebyte: tutte le prove passate" if not fails else f"{fails} prove fallite")
sys.exit(1 if fails else 0)
