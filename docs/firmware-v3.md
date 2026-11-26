# Firmware V3: piano e stato (26/11/2026)

> **Stato: si è cominciato dal NUCLEO. Nessun codice V3 è mai stato eseguito su una scheda.** Il firmware di misura ([firmware-misura.md](firmware-misura.md)) compila per T3 e T-Beam (la CI lo verifica) ma non è stato provato sulle schede. Questa pagina dice cosa c'è e cosa manca.

## Come è organizzato
Il codice V3 si scrive in due strati, come già fatto per il firmware di misura (`misura_core.h`):
1. **Il nucleo** (`firmware/v3/src/*.h`): C++17 puro, senza dipendenze dalla scheda e **senza memoria dinamica**. Gira anche sul PC e lo si prova lì.
2. **Il guscio** per la scheda (Arduino/PlatformIO): BLE, radio, schermo, che chiamano il nucleo.

La regola che tiene insieme i due mondi: **il nucleo C++ deve riprodurre il riferimento Python byte per byte**. Il riferimento Python è lo studio già provato (simulatori, prove); il nucleo C++ è quello che va sulla scheda.

## Fatto: il nucleo del firmware mobile (telefono ↔ scheda)
| File | Cosa è |
|---|---|
| `firmware/v3/src/ble_bridge.h` | `v3::ble::Bridge`: il ponte del [ble-telefono.md](ble-telefono.md) (comandi, eventi, richieste di blocchi, ripresa dopo l'interruzione, annullamento, errori). Porta di `tools/ble_bridge.py`. RAM: **3 blocchi da 1 kB** più la sessione (circa 3,5 kB), nessun `new`/`malloc`. |
| `firmware/v3/src/estimate.h` | Stime di tempo del protocollo immagini (`estimateSeconds`, `chunkSize`, `frameAirtimeS`, tabella dei 15 gradini). Porta di `tools/protocollo_immagini.py`. |
| `firmware/v3/tests/test_conformance.cpp` | Riproduce i vettori e li confronta con il riferimento. Compilato con `-Wall -Wextra`, **ASan e UBSan**. |
| `firmware/v3/tests/vettori/*.txt` | Vettori generati dal Python (`tools/gen_vettori_firmware.py`): per ogni scenario ingressi e uscite del ponte, riga per riga. |
| `tests/sim/test_vettori_firmware.py` | Controlla che i vettori nel repository siano quelli che il Python genera oggi (se si cambia il riferimento, si rigenerano e si rifa la prova del C++). |

**Conformità provata sul PC:** 30566 controlli, 0 falliti, su 14 scenari: testo, file da 20 kB e da 64 kB, ritrasmissione selettiva, due interruzioni del BLE, telefono sparito oltre 60 s, annullamento, nessuna posizione, radio fallita, SX1262 a R10, FSK a R1, 26 ingressi sbagliati o strani, oggetto dalla radio al telefono, e **4000 frame casuali**: stesse notifiche byte per byte e stesse statistiche (richieste, richieste ripetute, blocchi, RAM massima). Più 210 combinazioni di stima del tempo (chip × gradino × dimensione). Per verificare che la prova sappia accorgersi di una differenza ho cambiato di proposito, uno alla volta, il ritardo delle ritrasmissioni, l'intervallo dell'avanzamento e il tempo di abbandono: la prova li ha trovati tutti.

```bash
make -C firmware/v3 test          # nucleo C++ contro i vettori
python3 tests/sim/test_vettori_firmware.py   # i vettori sono aggiornati
```

**Il modello a tempo della radio.** Nel nucleo la radio è ancora il **modello a tempo** del riferimento (`Bridge::tick`): un blocco "parte" dopo il tempo che la stima dice. Serve per provare il ponte da solo e per far funzionare la scheda con il telefono **prima** che esista il protocollo radio vero. Il callback `Sink::radioBlock` è dove, nel firmware vero, il blocco entra nella radio; la fine di ogni blocco la dirà la radio e sostituirà il tempo.

## Da fare, in ordine
1. **Guscio per la scheda del mobile** (`firmware/v3/src/main.cpp`): servizio BLE (4 caratteristiche, accoppiamento con codice), coda fra il BLE e il ponte, `tick` dall'orologio. Compilato dalla CI; **non si può compilare qui** (il registro di PlatformIO non è raggiungibile da questo ambiente). Vedi sotto.
2. **Codec dei frame del protocollo immagini** in C++ (HELLO, OFFER, ACCEPT, DATA, STATUS, DONE), con vettori dal Python.
3. **Macchina a stati del protocollo immagini** in C++ (porta di `tools/sim_immagini.py`, circa 900 righe): incontro a R10, salita e discesa dei gradini, finestre, ritrasmissione selettiva, budget di tempo.
4. **Driver radio** (RadioLib): modi LoRa e FSK dei 15 gradini, potenza, **BOOST** ([boost.md](boost.md)), maschera dei gradini ([limiti_chip.py](../tools/limiti_chip.py)). Qui servono le **misure** della fase 1 (tempi in aria reali, sensibilità, rendimento delle schede) prima di fidarsi dei numeri.
5. **Ruoli dei nodi e dei ripetitori**: ascolto a turni, configurazione del sysop ([configurazione-nodo.md](configurazione-nodo.md)), microSD (solo nodi e ripetitori), voto, rete mesh.
6. **Gateway Internet** verso il reflector V3 (reflector già pronto in C++).

## Cosa NON è pronto per il firmware
- **Misure su schede vere** (fase 1): senza, i tempi in aria, le sensibilità e la deriva del quarzo sono stime. Il firmware di misura serve proprio a questo ed è ancora da provare.
- **Il protocollo radio V3 in C++** (punti 2 e 3): è tutto nel simulatore Python, non sulla scheda.
- **Ruolo "nodo"**: dipende dal protocollo radio.
