# Configurazione di un nodo (scelta del sysop)

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
  "v2_ruolo": "gateway",
  "v3_ruolo": "pappagallo",
  "topologia": "singola",
  "chip": "SX1278",
  "freq_nodo_khz": 433700,
  "profilo_v2": "messaggio",
  "reflector_v2": "reflector.example.org"
}
```

## 5. Punti aperti
- **"Nodo con gateway con seconda scheda":** da precisare se la seconda scheda è la **radio del voto** (come nella topologia doppia) o una **scheda che fa solo da gateway Internet**.
- **Una radio ascolta un profilo alla volta:** il nodo a scheda singola che fa da gateway v2 per la voce dal vivo ascolta il profilo range o standard; per sentire anche il V3 a R10 serve ascolto a turni (calendario di ricerca) o un profilo solo.
- **Il reflector V3** e il suo protocollo.
- **Pagina di configurazione** (e le spunte nella pagina di installazione del firmware).
