"""Configurazione di un nodo scelta dal SYSOP (26/11/2026): due scelte indipendenti.
  1. RUOLO per protocollo: la v2 e il V3 si configurano separatamente come 'gateway' (usa Internet se c'e') o 'pappagallo' (solo radio, memorizza e ripete).
  2. TOPOLOGIA: 'singola' (una scheda, una frequenza), 'doppia' (seconda scheda con la radio del voto), 'tripla' (nodo + voto + 2,4 GHz per le immagini veloci).
Internet e' solo un aiuto: un gateway senza Internet ripiega da solo (v2: pappagallo; V3: rete mesh). Provato sul PC: tests/sim/test_config_nodo.py."""
import json
import os
import sys
from dataclasses import asdict, dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import canali as ch  # noqa: E402

RUOLI = ("gateway", "pappagallo")
TOPOLOGIE = ("singola", "doppia", "tripla")
PROFILI_V2 = ("range", "standard", "messaggio")          # profili voce della v2 (SF8/250, SF7/250, SF12/125)
CAP_FAST_2G4, CAP_GW_V2, CAP_GW_V3 = 4, 8, 16              # bit di capacita' del frame NODO (1 e 2 sono il canale di voto)


@dataclass
class NodeConfig:
    nominativo: str
    v2_ruolo: str = "gateway"
    v3_ruolo: str = "gateway"
    topologia: str = "singola"
    chip: str = "SX1278"                     # radio principale (a 433 MHz)
    freq_nodo_khz: int = 433700              # frequenza di incontro/nodo
    profilo_v2: str = "messaggio"            # profilo radio ascoltato dalla scheda principale per la v2
    chip_servizio: str = "SX1278"            # radio del voto (seconda scheda)
    freq_voto_khz: int = 0                   # 0 = nessun voto
    freq_veloce_khz: int = 0                 # 0 = nessun collegamento a 2,4 GHz
    air_code_veloce: int = 3                 # codice velocita' d'aria del modulo Ebyte
    reflector_v2: str = ""                   # indirizzo del reflector v2 (infrastruttura esistente, non si modifica)
    reflector_v3: str = ""                   # indirizzo del reflector V3 (da definire)
    attesa_fine_qso_min: int = 10            # minuti da 1 a 255 in modo v2 dopo la fine del QSO, prima di tornare ai turni
    lock_v2: bool = False                    # blocca il nodo in v2 finche' non lo sblocca la seriale, il web o un comando SYSOP firmato
    forza_v3_da: int = 0                     # maschera: 1 = una mobile V3, 2 = un altro nodo V3 possono forzare l'invio di immagini anche in modo v2 (mai a QSO in corso)
    slot_v2_s: float = 2.0                   # turni dell'ascolto a riposo (scheda singola)
    slot_v3_s: float = 2.0
    note: str = field(default="", repr=False)


def validate(cfg):
    """Ritorna (errori, avvisi)."""
    err, warn = [], []
    n = cfg.nominativo.strip().upper()
    if not 3 <= len(n) <= 8 or not all(c.isalnum() or c in "/-" for c in n):
        err.append("nominativo: da 3 a 8 caratteri (lettere, cifre, / e -)")
    if cfg.v2_ruolo not in RUOLI or cfg.v3_ruolo not in RUOLI:
        err.append("ruolo: gateway o pappagallo")
    if cfg.topologia not in TOPOLOGIE:
        err.append("topologia: singola, doppia o tripla")
        return err, warn
    if cfg.profilo_v2 not in PROFILI_V2:
        err.append("profilo v2: range, standard o messaggio")
    if not 1 <= cfg.attesa_fine_qso_min <= 255:
        err.append("attesa a fine QSO: da 1 a 255 minuti")
    if not 0 <= cfg.forza_v3_da <= 3:
        err.append("forza_v3_da: 0 nessuno, 1 mobile, 2 nodo, 3 entrambi")
    if cfg.slot_v2_s <= 0 or cfg.slot_v3_s <= 0:
        err.append("i turni dell'ascolto devono durare piu' di zero secondi")
    if cfg.chip not in ch.CHIP_RANGES_KHZ or not ch.valid_frequency(cfg.chip, cfg.freq_nodo_khz):
        err.append(f"frequenza del nodo {cfg.freq_nodo_khz} kHz fuori dal campo del chip {cfg.chip}")
    if cfg.topologia == "singola":
        if cfg.freq_voto_khz or cfg.freq_veloce_khz:
            err.append("topologia singola: niente frequenza del voto ne' del 2,4 GHz (scegli doppia o tripla)")
        if cfg.profilo_v2 != "messaggio":
            warn.append("scheda singola: ascolta un profilo alla volta; con la voce dal vivo della v2 (range o standard) i beacon V3 a R10 (profilo messaggio) non si sentono: il V3 funziona a turni o non funziona")
    else:
        if not cfg.freq_voto_khz:
            err.append("topologia doppia/tripla: serve la frequenza del voto (144,900 MHz o 433,850 MHz)")
        elif cfg.chip_servizio not in ch.CHIP_RANGES_KHZ or not ch.valid_frequency(cfg.chip_servizio, cfg.freq_voto_khz):
            err.append(f"frequenza del voto {cfg.freq_voto_khz} kHz fuori dal campo del chip {cfg.chip_servizio} (l'SX1262 parte da 150 MHz: niente 144,900 MHz)")
        elif cfg.freq_voto_khz == cfg.freq_nodo_khz:
            err.append("la frequenza del voto deve essere diversa da quella del nodo")
        if cfg.topologia == "doppia" and cfg.freq_veloce_khz:
            err.append("topologia doppia: niente 2,4 GHz (scegli tripla)")
    if cfg.topologia == "tripla":
        if not cfg.freq_veloce_khz:
            err.append("topologia tripla: serve la frequenza a 2,4 GHz")
        else:
            try:
                ch.chan_for_frequency_2g4(cfg.freq_veloce_khz, cfg.air_code_veloce)
            except ValueError as e:
                err.append(f"2,4 GHz: {e}")
    if cfg.v2_ruolo == "gateway" and not cfg.reflector_v2:
        warn.append("gateway v2 senza reflector: senza Internet configurato il nodo lavora da pappagallo")
    if cfg.v3_ruolo == "gateway":
        warn.append("gateway V3: il reflector V3 non esiste ancora (da definire); senza reflector il nodo ripiega sulla rete mesh" if not cfg.reflector_v3 else "gateway V3: il reflector V3 e' da definire")
    return err, warn


def ascolto(cfg):
    """L'ascolto a turni del nodo a scheda singola secondo la configurazione (tools/ascolto_nodo.py)."""
    import ascolto_nodo as an
    return an.Ascolto(cfg.slot_v2_s, cfg.slot_v3_s, cfg.attesa_fine_qso_min, cfg.forza_v3_da, cfg.lock_v2)


def caps(cfg):
    m = 0
    if cfg.freq_voto_khz:
        m |= ch.CAP_SERVICE_2M if cfg.freq_voto_khz < 200000 else ch.CAP_SERVICE_70CM
    if cfg.freq_veloce_khz:
        m |= CAP_FAST_2G4
    if cfg.v2_ruolo == "gateway":
        m |= CAP_GW_V2
    if cfg.v3_ruolo == "gateway":
        m |= CAP_GW_V3
    return m


def azione(cfg, protocollo, internet):
    """Cosa fa il nodo con il traffico di un protocollo ('v2' o 'v3').
    gateway_v2   : come un nodo v2: voce dalla rete -> RF e voce RF -> Internet (infrastruttura v2 invariata)
    reflector_v3 : il V3 va al reflector V3
    mesh         : ripete nella rete mesh verso gli altri nodi (gateway V3 senza Internet)
    pappagallo   : memorizza e ripete in RF a fine trasmissione (nodo isolato)"""
    ruolo = cfg.v2_ruolo if protocollo == "v2" else cfg.v3_ruolo
    if protocollo == "v2":
        return "gateway_v2" if ruolo == "gateway" and internet else "pappagallo"
    if ruolo == "gateway":
        return "reflector_v3" if internet else "mesh"
    return "pappagallo"


def to_json(cfg):
    return json.dumps(asdict(cfg), indent=2, ensure_ascii=False)


def from_json(text):
    return NodeConfig(**json.loads(text))


if __name__ == "__main__":
    c = NodeConfig("IU5HJU")
    print(to_json(c))
    print(validate(c))
