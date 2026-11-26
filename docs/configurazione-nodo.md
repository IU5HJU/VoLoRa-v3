# Configurazione di un nodo (scelta del sysop)

> **Principio (26/11/2026).** Un nodo V3 si può usare **come un nodo v2, con le solite funzioni**; in più ha una **capacità maggiore di relazionarsi con gli altri nodi e con le radio mobili** grazie alle caratteristiche del protocollo V3 (beacon, polling, ripetizione a gruppo, voto, immagini, cambio di banda).

> **Stato (26/11/2026): schema e regole scritti e provati sul PC** ([`tools/config_nodo.py`](../tools/config_nodo.py), `tests/sim/test_config_nodo.py`). **Non c'è ancora un firmware V3 né una pagina di configurazione**: la scelta si farà con le spunte del firmware (e della pagina di installazione). Nessuna parte è provata su schede.

Il nodo deve rispettare la **v2** (l'infrastruttura v2 non si modifica) e fare quello che il **V3** chiede. Il sysop decide, secondo l'installazione e la necessità di ogni nodo, **due cose indipendenti**.

## 1. Il ruolo, per protocollo (v2 e V3 si scelgono separatamente)
| | Gateway | Pappagallo |
|---|---|---|
| **v2** (voce, messaggio vocale, testo) | Con Internet si comporta **esattamente come un nodo v2**: la voce che arriva dalla rete la trasmette, quella che arriva via radio la manda a Internet (reflector v2) | Solo radio: memorizza il messaggio e lo ripete a fine trasmissione |
| **V3** (immagini, mesh, richieste ai nodi) | Con Internet manda la comunicazione al **reflector V3**; **senza Internet ripete nella rete mesh** verso gli altri nodi | Solo radio: memorizza e ripete in locale, senza usare la mesh |

Quattro combinazioni possibili: **gateway v2 e V3**, **gateway solo v2** (V3 pappagallo), **gateway solo V3** (v2 pappagallo), **isolato** (pappagallo per entrambi). Un gateway **senza Internet ripiega da solo** (v2: pappagallo; V3: mesh): Internet è solo un aiuto. Il **reflector V3 non esiste ancora**: da definire (il reflector v2 non si modifica).

| Ruolo v2 / V3 | Con Internet: v2, V3 | Senza Internet: v2, V3 |
|---|---|---|
| gateway / gateway | gateway v2, reflector V3 | pappagallo, mesh |
| gateway / pappagallo | gateway v2, pappagallo | pappagallo, pappagallo |
| pappagallo / gateway | pappagallo, reflector V3 | pappagallo, mesh |
| pappagallo / pappagallo | pappagallo, pappagallo | pappagallo, pappagallo |

## 2. La topologia (le radio e le frequenze)
| Topologia | Radio | Frequenze |
|---|---|---|
| **Singola** (isofrequenziale, la situazione di partenza) | una scheda | **una**: la frequenza del nodo (di partenza 433,700 MHz) |
| **Doppia** | due schede: nodo + radio del **voto** | frequenza del nodo e frequenza del **voto** (144,900 MHz con SX1278 e una sola antenna, oppure 433,850 MHz con qualunque chip) |
| **Tripla** | tre radio: nodo + voto + **2,4 GHz** per le immagini ad alta velocità | nodo, voto e 2,4 GHz (modulo Ebyte; frequenza sulla griglia del modulo, dentro 2400-2450 MHz) |

**Cosa controlla la configurazione** (`validate`): nominativo valido; frequenze nel campo del chip (l'SX1262 non fa il voto a 144,900 MHz); la frequenza del voto diversa da quella del nodo; **singola** senza voto né 2,4 GHz; **doppia** con il voto e senza 2,4 GHz; **tripla** con tutte e tre; il 2,4 GHz sulla griglia del modulo e dentro la banda.

**Avvisi:** scheda singola con la voce dal vivo della v2 (profilo range o standard): la radio ascolta **un profilo alla volta**, quindi i beacon V3 a R10 (profilo messaggio) non si sentono contemporaneamente; gateway v2 senza reflector configurato: lavora da pappagallo; gateway V3: il reflector V3 non esiste ancora.

## 3. Cosa annuncia il nodo (frame NODO)
La configurazione diventa le **capacità** del frame NODO (un byte, [mesh-v3.md](mesh-v3.md), punto 8c): bit 0 voto a 2 m, bit 1 voto a 70 cm, bit 2 collegamento a 2,4 GHz, bit 3 gateway v2, bit 4 gateway V3. Sono **informazioni per i vicini**, non promesse: nulla dipende da Internet.

## 4. Esempio di file di configurazione (JSON)
```json
{
  "nominativo": "IU5HJU",
  "attesa_fine_qso_min": 10,
  "lock_v2": false,
  "forza_v3_da": 0,
  "chiave_sysop_hex": "00112233445566778899aabbccddeeff",
  "v2_ruolo": "gateway",
  "v3_ruolo": "pappagallo",
  "topologia": "singola",
  "chip": "SX1278",
  "freq_nodo_khz": 433700,
  "profilo_v2": "messaggio",
  "reflector_v2": "reflector.example.org"
}
```

## 5. L'ascolto della scheda singola (deciso il 26/11/2026)
Una radio ascolta **un profilo alla volta**: la voce dal vivo della v2 (Range, SF8/250 kHz) e i beacon V3 a R10 (SF12/125 kHz, uguale al profilo Messaggio v2) non si sentono insieme. Regole decise dall'autore (codice in [`tools/ascolto_nodo.py`](../tools/ascolto_nodo.py), prove in `tests/sim/test_ascolto_nodo.py`):

1. **A riposo** (nessuna trasmissione radio e nessun flusso dalla rete) la radio **alterna v2 e V3 a turni dall'orologio** (di partenza 2 s + 2 s).
2. **Quando c'è voce v2** (dalla radio o da Internet) il nodo **resta in modo v2** fino alla fine del QSO (3 s di silenzio o END, come la v2) **più un'attesa impostabile da 1 a 255 minuti**; poi torna ai turni.
3. **Lock:** il nodo resta in v2 **senza limite di tempo** finché non lo sblocca l'**interfaccia seriale**, l'**interfaccia web** o un **comando SYSOP via radio**.
4. **Comando di una mobile V3 o di un altro nodo:** se la configurazione lo consente (`forza_v3_da`: 1 = mobile V3, 2 = altro nodo V3, 3 = entrambi, 0 = nessuno), il comando **forza il nodo a trasmettere immagini** anche in modo v2, anche con il lock; poi il nodo torna in v2. Il frame è `FORZA_IMG` (sottotipo 9 del frame 14, 11 byte) con l'origine (mobile o nodo). *(Assunto da me: mai mentre c'è un QSO in corso, cioè una trasmissione v2 negli ultimi 3 s.)*

**Comando SYSOP via radio (frame V3 firmato).** La v2 non si modifica, quindi il comando di sblocco **non può essere un comando della v2**: è un frame V3 **SYSOP** (sottotipo 70 del frame 14, 23 byte) con **firma HMAC-SHA256 troncata a 8 byte** e **contatore anti-ripetizione**, come i comandi del sysop della v2. Comandi: **1 blocca in v2**, **2 sblocca**, **3 imposta l'attesa a fine QSO** (1-255 minuti), **4 consente il comando forzato** (argomento: bit 0 mobile V3, bit 1 altro nodo V3). È l'unico frame V3 **firmato** per ora; per gli altri la firma resta un'opzione prevista e non attiva. La chiave (16 byte) la tiene il sysop.

## 6. La pagina di configurazione (site/nodo.html)
**Decisa il 26/11/2026:** la configurazione si fa con una **pagina web nella pagina di installazione** (GitHub Pages): [`site/nodo.html`](../site/nodo.html), raggiungibile dalla pagina di installazione del firmware. Un modulo con le spunte (ruolo gateway/pappagallo per v2 e V3, topologia, radio e frequenze, profilo, attesa, lock, comando forzato da mobile e/o nodo, chiave SYSOP) **controlla** la configurazione con le stesse regole di `tools/config_nodo.py` e produce `nodo.json`. Tutto resta nel browser; **la chiave SYSOP si genera nel browser** (16 byte casuali) e non viene inviata a nessuno. **Non scrive ancora sulla scheda**: manca il firmware V3 che legga il file; la scrittura per seriale dal browser (Web Serial) si farà quando il firmware esiste. Provata con Playwright (`tests/page/run_nodo.js`) e con un controllo incrociato in `tests/sim/test_config_nodo.py`.

## 7. Punti aperti
- ~~**"Nodo con gateway con seconda scheda":**~~ **Deciso il 26/11/2026:** la seconda scheda è la **radio del voto** (topologia doppia); il gateway Internet lo fa la scheda principale con il suo Wi-Fi.
- ~~**Una radio ascolta un profilo alla volta:**~~ **Deciso il 26/11/2026:** ascolto a turni dall'orologio, modo v2 durante il QSO e con lock (punto 5).
- **Il reflector V3:** deciso che **sostituirà il reflector v2**; **progettato** in [reflector-v3.md](reflector-v3.md). Il gateway V3 si dichiara nei HELLO e KEEPALIVE e manda l'annuncio delle stazioni sentite; il lato nodo (firmware) è da scrivere.
- ~~**Pagina di configurazione**~~ **Fatta** (punto 6), senza scrittura sulla scheda.
- ~~**Gestione delle chiavi** del sysop~~ **Deciso il 26/11/2026: una chiave per nodo** (16 byte, generata dalla pagina, scritta nella configurazione); cambio con la pagina e riscrittura via seriale o web. Resta da definire come si cambia la chiave via radio senza ripetere la vecchia.
- ~~**Comando forzato che interrompe un QSO**~~ **Deciso il 26/11/2026: mai.**
- **Da verificare con le schede:** durata dei turni (quanti pacchetti v2 si perdono all'ingresso in modo v2), tempo di commutazione della radio fra i due profili.
