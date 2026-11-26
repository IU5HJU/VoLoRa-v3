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
| `firmware/v3/src/main.cpp`, `platformio.ini` | Il guscio per la scheda mobile: BLE, coda, orologio, seriale. Compilato dalla CI; radio simulata. |
| `firmware/v3/src/frames.h` | **Codec dei frame del protocollo immagini** (HELLO, PROBE, PROBE_REPORT, MODE_SET, MODE_ACK, OFFER, ACCEPT, DATA, STATUS, DONE, ABORT): codifica e decodifica, senza memoria dinamica. Porta di `tools/sim_immagini.py` (`enc_*`, `decode`). |
| `firmware/v3/src/limits.h` | Limiti dei chip dai datasheet e **maschera dei gradini** (`rungMask`, `commonMask`): R0 solo SX1278, R12-R14 solo con TCXO, R3 tolto se i chip differiscono. Porta di `tools/limiti_chip.py`. |
| `firmware/v3/tests/test_frames.cpp`, `test_limits.cpp` | Conformità di codec e limiti al riferimento Python. |
| `tests/sim/test_vettori_firmware.py` | Controlla che i vettori nel repository siano quelli che il Python genera oggi (se si cambia il riferimento, si rigenerano e si rifa la prova del C++). |

**Conformità provata sul PC (ponte):** 30566 controlli, 0 falliti, su 14 scenari: testo, file da 20 kB e da 64 kB, ritrasmissione selettiva, due interruzioni del BLE, telefono sparito oltre 60 s, annullamento, nessuna posizione, radio fallita, SX1262 a R10, FSK a R1, 26 ingressi sbagliati o strani, oggetto dalla radio al telefono, e **4000 frame casuali**: stesse notifiche byte per byte e stesse statistiche (richieste, richieste ripetute, blocchi, RAM massima). Più 210 combinazioni di stima del tempo (chip × gradino × dimensione). Per verificare che la prova sappia accorgersi di una differenza ho cambiato di proposito, uno alla volta, il ritardo delle ritrasmissioni, l'intervallo dell'avanzamento e il tempo di abbandono: la prova li ha trovati tutti.

**Codec dei frame:** 207 frame codificati dal C++ (tutti i tipi, con e senza misura, posizione e opzioni, DATA con salti e ritrasmissione, STATUS con mappa a 64 bit) **identici byte per byte** al Python; **12197 frame decodificati** (tutti i frame validi, ogni loro troncamento, 8000 mutazioni casuali e 1500 frame casuali: 6999 non validi) con lo **stesso riassunto** del Python. Per ottenere questa uguaglianza ho reso più rigoroso anche il decodificatore Python (`sim_immagini.decode`): ora rifiuta posizioni troncate e non lancia più eccezioni su posizioni di tipo sconosciuto o opzioni troncate. **Divergenze dichiarate:** il C++ accetta nominativi fino a 31 byte e al massimo 16 livelli nell'OFFER (il Python di più); un frame oltre questi limiti è "non valido".

**Limiti dei chip:** 425 controlli (maschere per chip, TCXO e frequenza; 408 combinazioni gradino × chip × errore di quarzo; maschere comuni) uguali al Python, più le decisioni scritte in chiaro (`0x0FFF`, `0x0FFE`, `0x7FFF`, R3 tolto).

```bash
make -C firmware/v3 test          # nucleo C++ contro i vettori
python3 tests/sim/test_vettori_firmware.py   # i vettori sono aggiornati
```

**Il modello a tempo della radio.** Nel nucleo la radio è ancora il **modello a tempo** del riferimento (`Bridge::tick`): un blocco "parte" dopo il tempo che la stima dice. Serve per provare il ponte da solo e per far funzionare la scheda con il telefono **prima** che esista il protocollo radio vero. Il callback `Sink::radioBlock` è dove, nel firmware vero, il blocco entra nella radio; la fine di ogni blocco la dirà la radio e sostituirà il tempo.

## Fatto: il guscio per la scheda del mobile (compila, non provato)
`firmware/v3/src/main.cpp` e `platformio.ini`: servizio BLE con le quattro caratteristiche di [ble-telefono.md](ble-telefono.md) (NimBLE-Arduino 1.4.2), **accoppiamento con codice a 6 cifre** (LE Secure Connections con bonding, niente "Just Works"; il codice per ora esce sulla **seriale**, lo schermo OLED non è collegato), coda fra i callback del BLE e il ponte (24 frame), `tick` dall'orologio, ripubblicazione della pubblicità dopo ogni disconnessione, nominativo salvato in memoria permanente. **Compila per T3 (SX1278) e T-Beam (SX1262)** nella CI (`pio run -e t3`, `-e tbeam1262`): flash circa 604 kB su 1,31 MB (46%), RAM statica circa 42 kB su 328 kB (13%), comprese le librerie BLE.

**La radio è simulata.** I blocchi "partono" con il modello a tempo del nucleo e si vedono sulla seriale (`[radio simulata] oggetto 7 blocco 3`): il telefono vede comunque consegna, avanzamento e tempi come con la radio vera. Serve a **provare per prima la pagina del telefono con una scheda vera**, senza aspettare il protocollo radio.

Seriale a 115200 baud: `CALL IU5HJU` (salva il nominativo; senza, la scheda risponde NO_CALL), `STATO` (nominativo, BLE, oggetto in corso, RAM, richieste, blocchi, pacchetti scartati).

**Primo passo sulla scheda vera (da fare):** caricare il firmware, scrivere `CALL`, aprire `telefono.html` con Chrome su Android, accoppiare con il codice che compare sulla seriale e mandare un testo e un file. Cosa si guarda: l'accoppiamento funziona? Chrome vede il servizio? Le notifiche arrivano intere (serve MTU almeno 64)? La scrittura senza risposta regge i 240 byte (la pagina scende da sola a 100 e a 15 se serve)? La RAM libera resta alta durante un file da 64 kB (il nucleo ne usa 3 kB)?

## Da fare, in ordine
1. ~~**Guscio per la scheda del mobile**~~ **Scritto e compilato dalla CI** (vedi la sezione sotto). Non provato su una scheda.
2. ~~**Codec dei frame del protocollo immagini**~~ **Fatto** (`frames.h`).
3. **Macchina a stati del protocollo immagini** in C++ (porta della parte di protocollo di `tools/sim_immagini.py`, circa 900 righe). **Prima va separata nel Python**: oggi il simulatore è un blocco unico in cui le due stazioni, il canale e il tempo sono intrecciati (`Simulator.exchange`, `phase_hello`, `phase_transfer`...). Il piano: (a) estrarre nel Python due classi indipendenti, **mittente** e **ricevitore**, che ricevono un frame o un tick e restituiscono frame da trasmettere, senza sapere nulla del canale; (b) far girare il simulatore sopra queste due classi senza cambiare i suoi risultati (le prove esistenti devono passare identiche); (c) registrare ingressi e uscite di ciascuna classe come per il ponte e portarle in C++ con gli stessi vettori. Incontro a R10, salita e discesa dei gradini, finestre, ritrasmissione selettiva, budget di tempo, ricerca dopo la perdita del collegamento.
4. **Driver radio** (RadioLib): modi LoRa e FSK dei 15 gradini, potenza, **BOOST** ([boost.md](boost.md)); la maschera dei gradini c'è già (`limits.h`). Qui servono le **misure** della fase 1 (tempi in aria reali, sensibilità, rendimento delle schede) prima di fidarsi dei numeri.
5. **Ruoli dei nodi e dei ripetitori**: ascolto a turni, configurazione del sysop ([configurazione-nodo.md](configurazione-nodo.md)), microSD (solo nodi e ripetitori), voto, rete mesh.
6. **Gateway Internet** verso il reflector V3 (reflector già pronto in C++).

## Cosa NON è pronto per il firmware
- **Misure su schede vere** (fase 1): senza, i tempi in aria, le sensibilità e la deriva del quarzo sono stime. Il firmware di misura serve proprio a questo ed è ancora da provare.
- **Il protocollo radio V3 in C++** (punti 2 e 3): è tutto nel simulatore Python, non sulla scheda.
- **Ruolo "nodo"**: dipende dal protocollo radio.
