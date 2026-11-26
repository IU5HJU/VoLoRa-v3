"""Ascolto di un nodo a scheda singola (26/11/2026): una radio ascolta un profilo alla volta, quindi si alternano il profilo v2 (voce) e il V3 a R10.
Regole decise dall'autore:
  - a riposo (nessuna trasmissione radio e nessun flusso dalla rete) l'ascolto e' a TURNI dall'orologio;
  - quando c'e' voce v2 (dalla radio o da Internet) il nodo resta in modo v2 fino alla fine del QSO piu' un'attesa impostabile da 1 a 255 minuti;
  - il LOCK blocca il nodo in v2 finche' non lo sblocca l'interfaccia seriale o web oppure un comando SYSOP via radio (frame SYSOP firmato);
  - se la configurazione lo consente, un comando di una mobile V3 OPPURE di un altro nodo V3 puo' forzare il nodo a trasmettere immagini anche in modo v2 (mai a QSO in corso).
Le scelte che l'autore non ha precisato (e che ho assunto) sono marcate 'ASSUNTO'. Provato sul PC: tests/sim/test_ascolto_nodo.py."""

FORZA_MOBILE, FORZA_NODO = 1, 2
FINE_QSO_S = 3.0          # la v2 considera finita una sessione dopo 3 s di silenzio o con END (docs/protocollo.md della v2)


class Ascolto:
    def __init__(self, slot_v2_s=2.0, slot_v3_s=2.0, attesa_min=10, forza_v3_da=0, lock=False):
        if not 1 <= attesa_min <= 255:
            raise ValueError("l'attesa a fine QSO va da 1 a 255 minuti")
        self.slot_v2, self.slot_v3 = slot_v2_s, slot_v3_s
        self.attesa_s = attesa_min * 60.0
        self.forza_v3_da = forza_v3_da          # maschera: 1 = una mobile V3, 2 = un altro nodo V3
        self.lock = lock
        self.ultima_v2 = None          # istante dell'ultima attivita' v2 (voce dalla radio o dalla rete)
        self.forzato_fino = None       # fine dell'invio di immagini forzato da una mobile V3

    # eventi
    def on_v2_voce(self, t):
        self.ultima_v2 = t

    def on_internet_voce(self, t):
        self.ultima_v2 = t

    def set_lock(self, v):
        self.lock = bool(v)

    def set_attesa_min(self, minuti):
        if not 1 <= minuti <= 255:
            raise ValueError("l'attesa a fine QSO va da 1 a 255 minuti")
        self.attesa_s = minuti * 60.0

    def qso_in_corso(self, t):
        return self.ultima_v2 is not None and t - self.ultima_v2 < FINE_QSO_S

    def on_comando_v3(self, t, durata_immagine_s, origine="mobile"):
        """Una mobile V3 oppure un altro nodo V3 chiede al nodo di trasmettere un'immagine. Con la configurazione che lo consente per quell'origine il nodo lascia il modo v2
        (anche col lock) per la durata dell'invio; ASSUNTO: mai a QSO in corso (una trasmissione v2 negli ultimi 3 s). Ritorna True se accettato."""
        bit = {"mobile": FORZA_MOBILE, "nodo": FORZA_NODO}[origine]
        if not self.forza_v3_da & bit or self.qso_in_corso(t):
            return False
        self.forzato_fino = t + durata_immagine_s
        return True

    # stato
    def modo(self, t):
        """'v3_forzato', 'v2_lock', 'v2' (a QSO in corso o nell'attesa dopo il QSO), 'turni_v2' o 'turni_v3' (ascolto a turni dall'orologio)."""
        if self.forzato_fino is not None and t < self.forzato_fino:
            return "v3_forzato"
        if self.lock:
            return "v2_lock"
        if self.ultima_v2 is not None and t - self.ultima_v2 <= self.attesa_s + FINE_QSO_S:
            return "v2"
        slot = int(t // (self.slot_v2 + self.slot_v3))
        fase = t - slot * (self.slot_v2 + self.slot_v3)
        return "turni_v2" if fase < self.slot_v2 else "turni_v3"

    def profilo(self, t):
        """Profilo radio da ascoltare in questo istante: 'v2' o 'v3'."""
        m = self.modo(t)
        return "v3" if m in ("turni_v3", "v3_forzato") else "v2"
