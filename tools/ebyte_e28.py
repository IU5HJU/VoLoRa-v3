"""Modulo Ebyte E28-2G4T27SX (UART, 2,4 GHz): parametri e comandi, secondo il manuale ufficiale v1.0 del 19/08/2020 (docs/modulo-2g4-uart.md).
Provato sul PC con l'esempio del manuale (tests/sim/test_ebyte_e28.py); NON provato con un modulo vero.

Comando di configurazione: 6 byte `C0` (salva) o `C2` (non salva), ADDH, ADDL, SPED, CHAN, OPTION.
  SPED   bit 7-6 parita' (00 8N1, 01 8O1, 10 8E1, 11 8N1), bit 5-3 baud (1200, 4800, 9600, 19200, 57600, 115200, 460800, 921600), bit 2-0 velocita' d'aria
  OPTION bit 7 trasmissione fissa, bit 3 LBT (ascolto prima di trasmettere), bit 2 uscite push-pull, bit 1-0 potenza (27, 23, 20, 17 dBm)"""

BAUDS = (1200, 4800, 9600, 19200, 57600, 115200, 460800, 921600)
PARITIES = ("8N1", "8O1", "8E1", "8N1")
AIR_RATES = (None, 1000, 5000, 10000, 50000, 100000, 1000000, 2000000)         # 0 = autoadattiva (trasmissione continua)
AIR_NAMES = ("autoadattiva (continua)", "1k", "5k", "10k", "50k", "100k", "1M (FLRC)", "2M (FSK)")
POWERS_DBM = (27, 23, 20, 17)
HEAD_SAVE, HEAD_TEMP = 0xC0, 0xC2
CMD_READ = bytes([0xC1]) * 3
CMD_VERSION = bytes([0xC3]) * 3
CMD_RESET = bytes([0xC4]) * 3
WINDOW_E2, WINDOW_E3 = bytes([0xE2]) * 3, bytes([0xE3]) * 3     # in trasmissione trasparente aprono una finestra di configurazione di 10 s
FORBIDDEN_IN_DATA = (WINDOW_E2, WINDOW_E3)                       # non devono mai comparire nei dati da trasmettere
MAX_PACKET = 121                                                  # byte per pacchetto d'aria (FIFO, modo a sotto-pacchetti); 221 in trasmissione continua


def build_config(addr=0, parity="8N1", baud=9600, air_code=3, chan=0x18, fixed=False, lbt=False, push_pull=True, power_dbm=27, save=True):
    if parity not in ("8N1", "8O1", "8E1") or baud not in BAUDS or not 0 <= air_code <= 7 or power_dbm not in POWERS_DBM or not 0 <= chan <= 255:
        raise ValueError("parametro non valido")
    sped = (("8N1", "8O1", "8E1").index(parity) << 6) | (BAUDS.index(baud) << 3) | air_code
    opt = (0x80 if fixed else 0) | (0x08 if lbt else 0) | (0x04 if push_pull else 0) | POWERS_DBM.index(power_dbm)
    return bytes([HEAD_SAVE if save else HEAD_TEMP, (addr >> 8) & 255, addr & 255, sped, chan, opt])


def parse_config(b):
    if len(b) != 6 or b[0] not in (HEAD_SAVE, HEAD_TEMP):
        raise ValueError("non e' una risposta di configurazione (C0 + 5 byte)")
    sped, opt = b[3], b[5]
    return {"addr": (b[1] << 8) | b[2], "parity": PARITIES[sped >> 6], "baud": BAUDS[(sped >> 3) & 7], "air_code": sped & 7, "chan": b[4],
            "fixed": bool(opt & 0x80), "lbt": bool(opt & 0x08), "push_pull": bool(opt & 0x04), "power_dbm": POWERS_DBM[opt & 3]}


def channel_step_mhz(air_code, baud=9600):
    """Passo del canale in MHz: dipende dalla velocita' d'aria (trasmissione normale) o dal baud (trasmissione continua, air_code 0).
    NB: il manuale scrive 'baud 1200, 9600 o 9200' per i 2 MHz: 9200 e' un refuso, qui si assume 19200."""
    if air_code == 0:
        return 2 if baud in (1200, 9600, 19200) else 4 if baud in (4800, 57600, 115200) else 5
    return {1: 1, 2: 1, 3: 1, 4: 2, 5: 2, 6: 3, 7: 5}[air_code]


def channel_mhz(chan, air_code, baud=9600):
    return 2400 + chan * channel_step_mhz(air_code, baud)


def max_channel(air_code, baud=9600):
    """Ultimo canale che resta dentro 2400-2500 MHz (campo dichiarato dal manuale)."""
    return 100 // channel_step_mhz(air_code, baud)


def describe(cfg):
    ac = cfg["air_code"]
    return (f"indirizzo {cfg['addr']:04X}, seriale {cfg['baud']} {cfg['parity']}, velocità d'aria {AIR_NAMES[ac]}, canale {cfg['chan']} "
            f"({channel_mhz(cfg['chan'], ac, cfg['baud'])} MHz), potenza {cfg['power_dbm']} dBm, LBT {'sì' if cfg['lbt'] else 'no'}, "
            f"{'trasmissione fissa' if cfg['fixed'] else 'trasparente'}")


def contains_forbidden(data):
    return any(f in data for f in FORBIDDEN_IN_DATA)
