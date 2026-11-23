"""Codice a fontana (codice lineare casuale su GF(2)) per il mesh V3.

Ogni simbolo trasmesso ha un numero ESI. Il sottoinsieme dei simboli sorgente che contiene si ricava SOLO da (id oggetto, ESI): chi riceve
rifà lo stesso calcolo senza che serva trasmettere la lista. Il decodificatore e' l'eliminazione di Gauss sui bit.

ESI con piu' sorgenti: ESI = contatore * M + indice del membro (M = membri del gruppo). Due membri non generano mai lo stesso ESI,
quindi non trasmettono mai lo stesso simbolo senza saperlo: i simboli di tutti i membri servono tutti a chi decodifica.

Modalita' sistematica: gli ESI da 0 a K-1 sono i simboli sorgente stessi (chi riceve tutto non decodifica nulla); dopo K, simboli di codice.
Questo e' uno studio sul PC, non e' provato su schede."""
import random


def sottoinsieme(obj_id, esi, k, sistematico=True):
    """Maschera di bit (int) dei simboli sorgente che compongono il simbolo `esi`."""
    if sistematico and esi < k:
        return 1 << esi
    r = random.Random((obj_id << 32) ^ (esi * 0x9E3779B1) ^ 0x5A5A)
    m = r.getrandbits(k)
    return m or 1 << (esi % k)


def codifica(sorgenti, obj_id, esi, sistematico=True):
    """sorgenti: lista di K bytes della stessa lunghezza. Restituisce il simbolo di codice (bytes)."""
    k = len(sorgenti)
    m = sottoinsieme(obj_id, esi, k, sistematico)
    acc = 0
    for i in range(k):
        if m >> i & 1:
            acc ^= int.from_bytes(sorgenti[i], "big")
    return acc.to_bytes(len(sorgenti[0]), "big")


class Decodificatore:
    def __init__(self, k, lung, obj_id, sistematico=True):
        self.k, self.lung, self.obj, self.sis = k, lung, obj_id, sistematico
        self.righe = {}       # bit piu' alto -> (maschera, valore)
        self.ricevuti = 0

    def aggiungi(self, esi, dati):
        """True se il simbolo ha aggiunto informazione."""
        self.ricevuti += 1
        m = sottoinsieme(self.obj, esi, self.k, self.sis)
        v = int.from_bytes(dati, "big")
        while m:
            p = m.bit_length() - 1
            if p in self.righe:
                rm, rv = self.righe[p]
                m ^= rm
                v ^= rv
            else:
                self.righe[p] = (m, v)
                return True
        return False

    @property
    def rango(self):
        return len(self.righe)

    @property
    def completo(self):
        return len(self.righe) == self.k

    def risultato(self):
        if not self.completo:
            return None
        val = {}
        for p in range(self.k):                       # sostituzione all'indietro: la riga p contiene solo bit <= p
            m, v = self.righe[p]
            m &= ~(1 << p)
            while m:
                q = m.bit_length() - 1
                v ^= val[q]
                m ^= 1 << q
            val[p] = v
        return [val[i].to_bytes(self.lung, "big") for i in range(self.k)]


def sovrappiu_medio(k, prove=200, seed=1, sistematico=False, perdita=0.0):
    """Quanti simboli in piu' di K servono (media) per decodificare, con ESI consecutivi e perdita casuale."""
    rng = random.Random(seed)
    tot = 0
    for _ in range(prove):
        obj = rng.getrandbits(16)
        d = Decodificatore(k, 1, obj, sistematico)
        esi = 0
        while not d.completo:
            if rng.random() >= perdita:
                d.aggiungi(esi, b"\x00")
            esi += 1
        tot += d.ricevuti - k
    return tot / prove


if __name__ == "__main__":
    for k in (16, 64, 128):
        print(f"K={k}: sovrapposizione media {sovrappiu_medio(k, 100):.2f} simboli")
