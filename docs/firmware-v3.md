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
| `firmware/v3/src/main.cpp`, `platformio.ini` | Il guscio del solo ponte BLE con la radio **simulata** (ambienti `ble_sim_t3`, `ble_sim_tbeam1262`). Compilato dalla CI. La scheda completa è `main_mobile.cpp` (sezione "Il ponte collegato al mezzo"). |
| `firmware/v3/src/frames.h` | **Codec dei frame del protocollo immagini** (HELLO, PROBE, PROBE_REPORT, MODE_SET, MODE_ACK, OFFER, ACCEPT, DATA, STATUS, DONE, ABORT): codifica e decodifica, senza memoria dinamica. Porta di `tools/sim_immagini.py` (`enc_*`, `decode`). |
| `firmware/v3/src/limits.h` | Limiti dei chip dai datasheet e **maschera dei gradini** (`rungMask`, `commonMask`): R0 solo SX1278, R12-R14 solo con TCXO, R3 tolto se i chip differiscono. Porta di `tools/limiti_chip.py`. |
| `firmware/v3/tests/test_frames.cpp`, `test_limits.cpp` | Conformità di codec e limiti al riferimento Python. |
| `firmware/v3/src/img_proto.h` | **Il protocollo immagini**: `Link` (gradino, silenzio, ricerca a calendario), `Receiver` (risponde ai frame, compone STATUS e PROBE-REPORT) e `Sender` (il mittente, un processo che chiede azioni al mezzo). Porta di `tools/img_proto.py`. |
| `firmware/v3/tests/test_protocol.cpp` | Rifa' ogni scenario del simulatore, stazione per stazione, con le tracce registrate dal Python (`tools/gen_tracce_protocollo.py`). |
| `firmware/v3/src/medium.h` | **Il mezzo della scheda**: `Radio` (interfaccia) e `Station` (collegamento + ricevitore che risponde da solo + mittente le cui azioni diventano trasmissioni e attese). |
| `firmware/v3/src/radio_board.h`, `main_bench.cpp` | Driver radio RadioLib per T3 (SX1278) e T-Beam (SX1262) e il firmware di **prova a banco** fra due schede. Compilano in CI; mai eseguiti. |
| `firmware/v3/tests/test_medium.cpp` | Due stazioni con canale con perdite, confrontate con il riferimento Python (`tools/gen_riferimento_medio.py`). |
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
`firmware/v3/src/main.cpp` e `platformio.ini`: servizio BLE con le quattro caratteristiche di [ble-telefono.md](ble-telefono.md) (NimBLE-Arduino 1.4.2), **accoppiamento con codice a 6 cifre** (LE Secure Connections con bonding, niente "Just Works"; il codice per ora esce sulla **seriale**, lo schermo OLED non è collegato), coda fra i callback del BLE e il ponte (24 frame), `tick` dall'orologio, ripubblicazione della pubblicità dopo ogni disconnessione, nominativo salvato in memoria permanente. **Compila per T3 (SX1278) e T-Beam (SX1262)** nella CI (`pio run -e ble_sim_t3`, `-e ble_sim_tbeam1262`): flash circa 604 kB su 1,31 MB (46%), RAM statica circa 42 kB su 328 kB (13%), comprese le librerie BLE.

**La radio è simulata.** I blocchi "partono" con il modello a tempo del nucleo e si vedono sulla seriale (`[radio simulata] oggetto 7 blocco 3`): il telefono vede comunque consegna, avanzamento e tempi come con la radio vera. Serve a **provare per prima la pagina del telefono con una scheda vera**, senza aspettare il protocollo radio.

Seriale a 115200 baud: `CALL IU5HJU` (salva il nominativo; senza, la scheda risponde NO_CALL), `STATO` (nominativo, BLE, oggetto in corso, RAM, richieste, blocchi, pacchetti scartati).

**Questo guscio è quello con la radio simulata.** Quello con la radio vera è `main_mobile.cpp` (ambienti `mobile_t3`, `mobile_tbeam1262`): vedi la sezione "Il ponte collegato al mezzo".

**Primo passo sulla scheda vera (da fare):** caricare il firmware, scrivere `CALL`, aprire `telefono.html` con Chrome su Android, accoppiare con il codice che compare sulla seriale e mandare un testo e un file. Cosa si guarda: l'accoppiamento funziona? Chrome vede il servizio? Le notifiche arrivano intere (serve MTU almeno 64)? La scrittura senza risposta regge i 240 byte (la pagina scende da sola a 100 e a 15 se serve)? La RAM libera resta alta durante un file da 64 kB (il nucleo ne usa 3 kB)?

## Fatto: il protocollo immagini in C++ (nucleo, senza radio)
**Separazione nel Python.** Il simulatore era un blocco unico (due stazioni, canale e orologio intrecciati). Ora il protocollo sta in [`tools/img_proto.py`](../tools/img_proto.py) e non conosce né il canale né l'orologio: `Link` (stato del collegamento), `Receiver` e `Sender`. Il **mittente è un processo** (generatore): a ogni passo **chiede un'azione al mezzo** e riceve la risposta. Il simulatore (`tools/sim_immagini.py`) è diventato il *mezzo* (canale con perdite, orologio, due gradini) che esegue le azioni. **I risultati non sono cambiati:** `tests/sim/test_golden_sim_immagini.py` confronta 134 scenari (90 riusciti, 44 falliti) con quelli catturati prima del rifacimento, **identici fino all'ultimo bit** (tempi, gradini, frame, ritrasmissioni).

**Azioni del mittente** (il mezzo le esegue; nel firmware saranno radio e timer):
| Azione | Cosa chiede al mezzo | Risposta |
|---|---|---|
| `exchange` | manda un frame e aspetta la risposta di un tipo, con N tentativi | il frame di risposta o niente |
| `probe` | una raffica di PROBE e il PROBE-REPORT del ricevitore | il report o niente |
| `modeset` | MODE-SET e MODE-ACK; il ricevitore passa al nuovo gradino dopo l'ACK | l'ACK o niente |
| `burst` | frame di seguito (dati, abort), senza risposta | — |
| `status` | lo STATUS dopo una finestra | lo STATUS o niente |
| `wait`, `rand`, `setrung`, `holdclear` | attesa, numero casuale, cambio di gradino, fine della tenuta | — |
| `oracle` | **solo simulatore**: il ricevitore ha sentito il DONE? | sì o no |

**Il C++** (`img_proto.h`) ha le stesse tre parti. Il mittente C++ è scritto con **coroutine a macro** (`switch` e `__LINE__`): ogni procedura (incontro, raffica di prove, cambio di gradino, ricerca, negoziazione, trasferimento) ha la stessa struttura del generatore Python, quindi la traduzione è meccanica e ogni riga si può confrontare. Niente memoria dinamica; il Sender occupa pochi kB (la RAM esatta la stampa la scheda all'avvio), i pezzi ricevuti vanno in un `Store` (RAM, telefono o microSD).

**Prova di conformità: 139 scenari, oltre un milione di controlli, 0 falliti.** Il simulatore Python registra, per ogni scenario, tre tracce: il **collegamento** di ciascuna stazione (ogni chiamata e lo stato dopo), il **ricevitore** (ogni frame con rssi, snr, ora e gradino, e la risposta) e il **mittente** (a ogni ripresa ora, gradino, risposta, e l'azione chiesta). Il C++ rifa' ogni stazione da sola con quegli ingressi e deve dare **le stesse uscite, byte per byte e con gli stessi numeri decimali**. Gli scenari sono 9 scelti a mano (vicino, lontano, collegamento perso, budget che taglia i livelli, quattro livelli, due chip diversi, TCXO, nessuna risposta...) più i 130 del riferimento con ricerca a calendario (chip, potenza da -100 a -142 dBm, quattro scenari di canale, budget, livelli). Per misurare quanto la prova sia sensibile ho cambiato di proposito una cosa alla volta nel C++: soglia di perdita, attesa minima della ricerca, flag di ritrasmissione, margine di salita, numero di finestre buone, tempo di abbandono, tenuta del ricevitore, sensibilità dei gradini: **tutte trovate**. Due mutazioni non sono state trovate perché non cambiano il comportamento (il reset del ricevitore a metà raffica e il quarzo del TCXO a 2,2 ppm).

```bash
make -C firmware/v3 test     # genera le tracce con il Python e le riproduce in C++ (qualche secondo)
python3 tests/sim/test_golden_sim_immagini.py     # il simulatore rifatto da' i risultati di prima
```

**Tre semplificazioni del simulatore risolte (26/11/2026), prima di scrivere il mezzo:**
1. **Quanti frame ha mandato il mittente in una finestra.** Il ricevitore non lo deve più ricevere dal mittente: nei frame DATA i **4 bit alti del campo del primo pezzo** portano l'**indice del frame nella finestra** (0-15); il primo pezzo resta a 12 bit, cioè oggetti fino a **4096 pezzi = 64 kB**, il tetto del progetto. Il ricevitore ricava i frame partiti dal frame con il flag di ultima finestra, o dal più alto indice sentito. L'intestazione non si allunga e le stime dei tempi non cambiano. Inoltre il ricevitore impara da solo `k` (pezzi per frame) dal HELLO e dal MODE-SET. La finestra ha al massimo 16 frame.
2. **Il DONE senza oracolo.** Se il DONE non è confermato dopo 4 tentativi il mittente dichiara "non confermato" (non sa se è arrivato); il simulatore lo segna a parte (`unconfirmed`).
3. **Il ricevitore risponde da solo** (vedi il mezzo qui sotto).
Effetto sul simulatore: su 134 scenari ne cambiano 8, di pochi secondi, **nessun esito** (stessi 90 riusciti): il riferimento è stato rigenerato e il C++ lo riproduce.

## Fatto: il mezzo della scheda (`medium.h`) e il driver radio
Il **mezzo** è ciò che porta le azioni del mittente sulla radio e sui timer. Sul simulatore lo faceva `Simulator` con un canale finto; sulla scheda lo fa `Station`.

| Pezzo | Cosa fa |
|---|---|
| `Radio` (interfaccia) | `setRung`, `transmit` (non bloccante), `random`. La implementano `BoardRadio` (scheda) e il simulatore del banco di prova (PC). |
| `Station` | Una stazione: **collegamento + ricevitore + mittente**. Si pilota con tre eventi: `onRx` (frame sentito), `onTxDone` (trasmissione finita), `poll` (il tempo passa). Mezzo duplex. Nessuna memoria dinamica. |
| `BoardRadio` (`radio_board.h`) | RadioLib: ogni gradino è un modo LoRa (banda, SF, CR 4/5) o FSK (bit rate, deviazione, filtro: **banda laterale singola** sull'SX1278, doppia sull'SX1262, scelto con l'errore di due quarzi da 10 ppm); interrupt di fine trasmissione e ricezione; RSSI e SNR. 433,700 MHz, +17 dBm, parola di sincronismo 0x5D. |

**Il ricevitore risponde da solo** (era il mezzo, a richiesta del mittente): ai frame di richiesta (HELLO, MODE-SET, OFFER, DONE) dopo una commutazione; manda lo **STATUS** appena sente il frame con il flag di ultima finestra, **oppure dopo un silenzio** (un frame lungo più la commutazione) se ha sentito qualche DATA; il **PROBE-REPORT** appena sente l'ultimo PROBE, oppure dopo un silenzio; dopo il MODE-ACK passa al nuovo gradino, sia che il mittente lo senta o no. **Il mittente aspetta** la risposta fino a un tempo limite (due commutazioni più il tempo in aria della risposta, più il silenzio del ricevitore dove serve); scaduto ritenta o riporta "nessuna risposta" al protocollo, che decide.

**Prova sul PC (`tests/test_medium.cpp`).** Due stazioni, un canale con perdite (lo stesso modello del simulatore Python, con affievolimento casuale) e un orologio a eventi; 9 scenari × 8 semi; il riferimento Python è generato da `tools/gen_riferimento_medio.py`. **Non è un confronto bit per bit** (qui i tempi di risposta sono veri, nel Python sono modellati), ma di comportamento:

| Scenario | Consegnati C++ / Python | Tempo mediano C++ / Python |
|---|---|---|
| vicino, -100 dBm, 5 kB | 8/8 e 8/8 | 8 s / 9 s |
| medio, -118 dBm | 8/8 e 8/8 | 12 s / 13 s |
| in degrado, -122 dBm | 8/8 e 8/8 | 29 s / 30 s |
| gradino di -11 dB, SX1262 | 7/8 e 8/8 | 509 s / 460 s |
| oscillante, -125 dBm | 8/8 e 8/8 | 502 s / 447 s |
| SX1278 con SX1262, -120 dBm | 8/8 e 8/8 | 17 s / 18 s |
| con TCXO, -136 dBm | 8/8 e 8/8 | 255 s / 251 s |
| budget di 2 minuti, 30 kB | 8/8 e 8/8 | 1499 s / 1372 s |
| nessun collegamento, -150 dBm | 0/8 e 0/8 | — |

**In ogni consegna l'oggetto arriva identico, byte per byte.** Il budget breve ferma il trasferimento a un livello intermedio. Un gradino che la radio non sa fare (R3 sull'SX1278) non si annuncia e non si usa: con R3 permesso la negoziazione lo sceglie, senza passa a R4 (4/4 consegne). Il C++ del mezzo è compilato con `-Wall -Wextra`, ASan e UBSan.

**Cosa NON è stato provato:** il driver radio e il mezzo **non sono mai girati su una scheda**; il canale del banco di prova è un modello. Il comportamento reale (tempi di commutazione della radio, ascolto prima di parlare, collisioni, interferenze) può cambiare i tempi limite.

### Pagina del telefono dentro la scheda (Wi-Fi), registro delle prove
**Decisione del 27/11/2026:** la pagina del telefono **risiede nella scheda**: per le prove non si usa più una pagina su Internet (regola "Internet non è affidabile"). Il firmware `mobile_t3` / `mobile_tbeam1262` con il Wi-Fi acceso fa così:
- La scheda crea il **suo Wi-Fi** `VoLoRa-<NOMINATIVO>` (password a 8 cifre, salvata; sul display e sulla seriale: `WIFI`, `WIFI NUOVA`), un **server web** serve la pagina incorporata nel firmware (`site/telefono.html` e `jpeg_prog.js` compressi, circa 16 kB; script `tools/embed_site.py`, verificato dai test) su `http://192.168.4.1`, e la pagina parla con la scheda via **WebSocket** `/ws` con lo stesso protocollo del Bluetooth (messaggi con un byte di canale davanti, vedi [ble-telefono.md](ble-telefono.md)). La pagina si collega da sola. Nessun Web Bluetooth, nessun https, funziona anche su iPhone.
- Un **DNS** che risponde con l'indirizzo della scheda e le **sonde di Internet** di Android, iOS e Windows (`/generate_204`, `/hotspot-detect.html`, `/connecttest.txt`...) fanno credere al telefono che la rete sia buona, così non la abbandona per quella cellulare. **Mai provato su un telefono vero.**
- Un solo telefono per volta (un nuovo collegamento sostituisce il vecchio). Il Wi-Fi e la radio LoRa lavorano insieme: l'effetto sui tempi del protocollo va misurato.
- **Un solo firmware mobile per tutti (decisione del 27/11/2026):** **Android** usa il **Bluetooth** con l'**app VoLoRa-V3.apk** ([app-android.md](app-android.md), mai provata su un telefono); **iPhone** usa il **Wi-Fi della scheda** con la pagina dentro. Il **Bluetooth è sempre acceso all'avvio; il Wi-Fi è spento** e lo accende solo chi ne ha bisogno: dalla voce **"Wi-Fi" del menu a bordo** (volume lungo per aprirlo, vedi sotto; pulsante esterno facoltativo) oppure con `WIFI ON` / `WIFI OFF` sulla seriale. Con il Wi-Fi acceso il Bluetooth tace (un solo telefono alla volta, meno RAM e meno interferenza) e il display mostra rete, password e indirizzo; sulla schermata del Bluetooth un richiamo ("iPhone: VOL lungo / poi voce Wi-Fi") alterna ogni 4 s con il codice. Il Wi-Fi non è salvato: a ogni avvio riparte spento. I due modi insieme non sono mai stati provati su una scheda: partizioni `huge_app` (app da 3 MB) perché il firmware con Bluetooth, Wi-Fi e server web non entra nei 1,3 MB predefiniti.
- **Registro delle prove** (`testlog.h`, provato sul PC): la scheda tiene le ultime ~60 righe (collegamento del telefono, cambi di gradino, perdita e ritrovamento del collegamento, inizio e **riepilogo di fine di ogni invio con il motivo**, oggetti ricevuti con RSSI e SNR). Si legge dalla seriale (`LOG`, `LOG CLEAR`) e dalla pagina ("Registro della scheda", scarica `registro-scheda.txt`, anche da `http://192.168.4.1/log`).
- **Evento `E_DIAG`:** a fine invio la scheda dice alla pagina il motivo di un fallimento (nessuna risposta, negoziazione, offerta non accettata, tempo massimo, collegamento perso, telefono sparito...). La pagina tiene lo schermo acceso durante l'invio (Screen Wake Lock) e avvisa se la stima supera il tempo massimo di 600 s.
- La procedura di laboratorio è in [prove-laboratorio-v3.md](prove-laboratorio-v3.md). **Provato sul PC:** pagina servita in modalità WebSocket con la scheda finta (`tests/page/run_telefono_ws.js`), registro (`test_testlog`), riepilogo (`test_live`), pagina incorporata identica all'originale. **Compilato dalla CI, mai eseguito su una scheda.**

### Confronto con la radio mobile v2 (cosa manca al V3)
La mobile **V2** è una radio vocale a turni (Codec2 su LoRa) con PTT, menu a bordo e tante funzioni; la mobile **V3** per ora è il **ponte telefono → protocollo immagini/dati**. Stato, funzione per funzione (v2 letta in `third_party/VoLoRa-v2`):

| Funzione della v2 | V3 mobile |
|---|---|
| Display OLED 128×64: layout, batteria `(Batt=…V)`, versione all'avvio, barra, avvisi | **fatto** (sezione sotto), non visto su schermo vero |
| Nominativo, frequenza configurabile, "solo RX" senza nominativo, potenza | **fatto** (`CALL`, `FREQ`; potenza +17 dBm, BOOST, IOF MODE) |
| Aggiornamento dalla pagina web senza perdere le impostazioni | **fatto** (pagina `firmware-v3.html`, quattro parti) |
| Messaggi di testo (SMS, 150 caratteri) e file/immagini | **fatto, in modo nuovo**: dal telefono via Bluetooth, sul protocollo V3 con livelli e ritrasmissione selettiva |
| Casella dei messaggi ricevuti (busta, "leggi") | **sul telefono** (sezione "Ricevuti dalla radio"); la scheda li passa e li libera |
| Posizione: QTH fisso o GPS, distanza dalla stazione, T-Beam col GPS | **fatto** (sezione "GPS e distanza"): GPS del T-Beam (`GPS ON`), posizione del telefono come ripiego, locatore Maidenhead, distanza sul display. Provato sul PC, **non su una scheda** |
| Pulsanti: PTT (GPIO0), volume lungo per il menu | **fatto** (sezione "Tasti e menu a bordo"), senza PTT né volume: il V3 non ha la voce |
| **Voce a turni** con Codec2 (profili Standard, Range, Messaggio, Diretta), microfono, altoparlante, PTT | **manca**: il V3 è un protocollo dati; la voce non è nel firmware V3 (il V3 è retrocompatibile con la voce v2 solo a livello di protocollo, non implementato sulla scheda) |
| Configurazione dal Wi-Fi della scheda (`192.168.4.1`) e comandi `CFG` | **manca** (si usano `CALL`, `FREQ`, `BOOST`, `IOF`, `DISPLAY` sulla seriale) |
| Shift del ripetitore (0-10 MHz) | **manca** |
| MeshCom (escursione sulle reti di testo a 433,175 MHz) | **manca** |
| Prova di collegamento e prova di potenza (frame noti, esito sul display) | **manca** (c'è il banco `bench_*` e il firmware di misura) |
| Ruoli ripetitore RX/TX, comandi del sysop, nodo Internet e reflector | **manca** (ruoli nodo e ripetitore del V3 non scritti; il reflector V3 è in C++ sul PC) |
| Identificativo periodico anche in Morse in FM | **manca** |
| Beacon periodico | **manca** |

**Schede supportate:** T3 V1.6.1 (SX1278), T-Beam V1.2 con modulo **SX1262** e T-Beam V1.2 con modulo **SX1278** (stessi pin, cambia il chip; guarda la sigla sul modulo radio). Per il T-Beam SX1278 ci sono `mobile_tbeam1278` e `bench_tbeam1278` (e `tbeam1278` nel firmware di misura): come la T3 per la radio (R3 escluso, niente IOF MODE), con GPS e PMU del T-Beam. Compilati dalla CI, mai eseguiti su una scheda.

### Tasti e menu a bordo (`menu.h`): logica della v2
**Il menu è quello della v2, senza aggiunte** (correzione del 27/11/2026: una prima versione aveva voci e gesti inventati, tolti). `firmware/v3/src/menu.h` è la **porta fedele** di `menu.h`, `menu.cpp`, `button_gesture.h` e `ptt_button.h` della v2, e `tests/test_menu.cpp` è la **copia dei test della v2** (92 controlli, tutti passano sul codice portato).
- **Tasti come nella v2:** *PTT* = T3 GPIO0 (BOOT), T-Beam GPIO38 (tasto utente); *volume* = pulsante **esterno facoltativo** fra GPIO15 e massa (se manca resta alto e non fa niente). Un tasto già premuto all'accensione non vale (come nella v2).
- **Gesti:** volume lungo (2 s) a scheda ferma apre il menu; nel menu **PTT breve = voce successiva** (si saltano le voci non disponibili), **volume breve = conferma**, **volume lungo = esce**, **10 s senza tasti = esce**; se arriva una ricezione il menu si chiude. Nel menu il PTT non fa altro. Aspetto: cinque righe da 9 punti, `*` sulla voce in uso, voce scelta in negativo, in basso `PTT=avanti  VOL=ok`, " (presto)" per le voci non disponibili.
- **Voci della v2:** Modo Standard, Modo Range, Modo Messaggio, Modo Diretta, Invia testo, MeshCom, MeshCom ascolto, Wi-Fi. **Nel V3 mobile esiste solo "Wi-Fi"** (accende o spegne il Wi-Fi della scheda per l'iPhone: con il Wi-Fi acceso il Bluetooth tace): le altre **non si mostrano** perché quelle funzioni non ci sono (restano nel codice con `enabled`, la v2 le mostrerebbe con " (presto)").
- Fuori dal menu i tasti non fanno altro: il V3 non ha PTT né volume.
- **Da decidere con l'autore (cose specifiche del V3):** come far accendere il Wi-Fi a chi ha l'iPhone sulla **T3 senza il pulsante esterno del volume** (oggi: seriale `WIFI ON`, oppure il pulsante esterno); se mostrare le voci non ancora disponibili con " (presto)"; quali voci nuove servono al V3 (per esempio potenza, GPS, informazioni: oggi `POWER`, `GPS` e `LOG` sono solo comandi della seriale).
- Provato sul PC (92 controlli della v2 sul codice portato; schermata del menu in `test_display`). **Mai provato su una scheda.**

### Potenza ridotta per le prove con attenuatori (`POWER`)
`POWER <dBm>` imposta la **potenza normale**: da **2 a 17 dBm** sull'SX1278 (il minimo con l'uscita PA_BOOST), da **−9 a 17 dBm** sull'SX1262. `POWER` da solo la mostra. Serve a non saturare il ricevitore nelle prove a banco ([prove-laboratorio-v3.md](prove-laboratorio-v3.md), con i conti di quanta attenuazione serve). Sulla scheda mobile **si salva** (all'avvio, se non è +17 dBm, un avviso lo dice); il banco riparte da +17 dBm. BOOST (+20) e IOF MODE (+22) restano comandi a parte e non si salvano. Il display mostra la potenza in uso (`R10 5dBm`). Provato sul PC (`test_boost`, 50 controlli: comando, minimi dei due chip, BOOST e IOF sopra la base); **mai provato su una scheda** (in particolare non so che potenza vera esca a +2 dBm sulla T3).

### GPS e distanza
- **GPS del T-Beam** (u-blox, 9600 baud, ALDO3 del PMU): porta di `src/gps.cpp` e dell'interprete NMEA della v2 (`nmea.h`, provato con gli stessi 45 controlli della v2). **Spento di base** come nella v2: seriale `GPS ON` / `GPS OFF` (salvato), `GPS` mostra stato e satelliti. Sulla T3 non c'è il GPS.
- **Quale posizione va nell'OFFER:** con un fix recente (meno di 15 s) la **posizione GPS assoluta** (come vuole [regole-radioamatoriali.md](regole-radioamatoriali.md): "la GPS è meglio"); senza fix quella che il telefono manda (locatore o GPS del telefono). Con il solo GPS si può inviare anche senza che il telefono abbia mandato la posizione.
- **Distanza:** dal blocco di posizione di chi manda (nell'OFFER) e dalla propria, anche se una delle due è solo un locatore (`position.h`: centro del quadrato Maidenhead, 4, 6 o 8 caratteri; formula dell'emisenoverso della v2). Sul display: `12.3km  RSSI -97` mentre si riceve, `Ultimo IZ5FSN 12.3km` dopo. Con un locatore a 6 caratteri l'errore è di qualche km.
- Provato sul PC: `test_position` (56) e `test_nmea` (45) sono i test della v2 sul codice portato; `test_geo` (15: locatore, distanze, blocco da 7 byte); `test_live` (GPS preferito al locatore, ripiego senza fix, invio con il solo GPS, distanza A↔B); `test_display` (stato del GPS, distanza). **Mai provato con un GPS vero.**

### Display OLED
La scheda mobile mostra sull'OLED lo stato come la v2 (stesso layout, batteria, versione all'avvio) con in più il **codice di accoppiamento Bluetooth**, gradino e potenza, avanzamento di invio e ricezione, e la lettera **V / B / I** per potenza normale / BOOST / IOF MODE. Dettagli e schermate in [display-v3.md](display-v3.md). Modello provato sul PC (61 controlli); **disegno mai visto su uno schermo vero**. Comando seriale `DISPLAY 0|1`.

### Frequenza configurabile (`freq.h`)
Come da nota dell'autore ([regole-radioamatoriali.md](regole-radioamatoriali.md)): la frequenza del canale di T3 e T-Beam è **liberamente configurabile** e il firmware controlla **solo il campo di sintonia del chip** (SX1278: 137-175 e 410-525 MHz; SX1262: 150-960 MHz, dai datasheet). Nessun altro limite, nessuna avvertenza. Il valore di partenza è 433,700 MHz.
- **Comando seriale** (mobile e banco): `FREQ` mostra la frequenza e il campo del chip; `FREQ 433.700` (o con la virgola, fino a 3 decimali = 1 kHz) la imposta. Fuori dal campo del chip il comando risponde con il campo giusto e non cambia niente. Nella scheda **mobile** la frequenza si **salva** (resta dopo lo spegnimento); sul banco no. `STATO` e l'avvio stampano la frequenza in uso.
- **Le due stazioni devono avere la stessa frequenza** per incontrarsi: il protocollo non la negozia ancora (il cambio di canale con la frequenza esplicita in kHz, BAND-SET-FREQ, è previsto per il cambio di banda e non è nel firmware).
- La frequenza arriva anche ai **limiti dei chip**: la maschera dei gradini annunciata nell'HELLO dipende da essa (bit rate FSK massimo dell'SX1262, budget di errore di frequenza dei quarzi). Il driver ricalcola il filtro di ricezione FSK con la frequenza in uso.
- Il cambio di frequenza è rifiutato durante un invio e ricrea la stazione (il collegamento riparte da R10).
- **Provato sul PC** (`tests/test_freq.cpp`, 43 controlli: comando, campo dei due chip, canali liberi, maschera per frequenza, trasferimento SX1262 a 868 MHz); **compilato dalla CI, mai eseguito su una scheda**. Il 2,4 GHz (modulo Ebyte, griglia 2400-2450 MHz) non è nel firmware V3.

### Installare il firmware V3 dalla pagina web
La pagina `firmware-v3.html` (sul sito di GitHub Pages, accanto a quella del firmware di misura) installa dal browser (Chrome, Edge od Opera) uno dei sei firmware V3: `mobile_t3`, `mobile_tbeam1262` (scheda mobile completa), `bench_t3`, `bench_tbeam1262` (prova a banco), `ble_sim_t3`, `ble_sim_tbeam1262` (ponte BLE con radio simulata). A ogni push su `main` la CI compila i sei firmware, ne tiene i binari e pubblica la pagina con la versione e il commit (si vedono sulla pagina). **Si scrivono quattro parti** (bootloader a 0x1000, partizioni a 0x8000, boot_app0 a 0xe000, programma a 0x10000) e **non si cancella la scheda**: nominativo e accoppiamento Bluetooth, salvati in NVS, restano. Seriale a 115200 baud. La logica della pagina è provata in CI (`tests/page/run_v3.js`: sei manifest con gli indirizzi giusti, scelta della scheda, avviso di firmware mancante, tema chiaro e scuro, 390 px); **la scrittura sulla scheda dal browser non si prova in CI** (come per il firmware di misura).

### Prova a banco fra due schede (`main_bench.cpp`, da fare tu)
Firmware senza Bluetooth che usa il mezzo e il driver radio: **una scheda manda un oggetto di prova, l'altra lo riceve**. Compila in CI per T3 e T-Beam.
```bash
cd firmware/v3
pio run -e bench_t3 -t upload              # oppure bench_tbeam1262
pio device monitor -b 115200
```
Su **due schede uguali**, con l'antenna (meglio un attenuatore se sono vicine: saturazione del ricevitore, vedi [piano-misure.md](piano-misure.md)): sulla seriale di ciascuna `CALL IU5HJU` e `CALL IK5XYZ`; poi su una `SEND 5000` (`BOOST ON RISCHIO` porta la potenza da +17 a +20 dBm: vedi [boost.md](boost.md); con le schede vicine non serve). Si vede il gradino cambiare (`gradino R10`...), poi sulla scheda che invia `INVIO FINITO: 3 livelli, 5000 byte consegnati` e sull'altra `OGGETTO RICEVUTO: ... CRC GIUSTO`. `STATO` mostra gradino, ricerca e errori di ricezione. L'oggetto è al massimo di 32 kB (RAM). **Cosa si guarda:** parte la radio? gli HELLO si sentono a R10? la negoziazione sale di gradino? il CRC torna giusto? Quanti secondi? Dimmi cosa vedi: i tempi limite del mezzo si regolano sulla prova vera.

## Fatto: il ponte collegato al mezzo (`live_bridge.h`, `main_mobile.cpp`)
Quello che il telefono manda parte **sul protocollo radio vero** (mezzo + driver), e quello che arriva dalla radio va al telefono. Provato **sul PC** (`tests/test_live.cpp`, 74 controlli, 0 falliti, ASan/UBSan): telefono finto → ponte → stazione A → canale con perdite → stazione B → ponte → secondo telefono finto. **Mai eseguito su schede.**

**Come funziona.**
- Il mittente del protocollo non vuole più l'oggetto intero in memoria: legge i byte da un `ObjectSource` (`img_proto.h`). `MemSource` è la versione in memoria (prove, banco: i 139 scenari di conformità del protocollo e le prove del mezzo danno gli stessi risultati di prima). `LiveBridge` è la versione "telefono": se i byte non ci sono ancora il mezzo aspetta 20 ms e riprova (`FR_PENDING`), senza perdere la finestra.
- **Cache:** 8 blocchi da 1 kB (8 kB di RAM). Il nucleo di prima ne teneva 3, ma una finestra da 16 frame da 15 pezzi vuole fino a 5 blocchi. I blocchi si chiedono con `E_PULL` quando il mittente li legge (più 3 in anticipo), si buttano quelli meno usati che il CRC ha già contato, e se il telefono è assente non si chiede niente. Dopo una caduta del BLE e `RESUME` quello che mancava si richiede.
- **CRC:** quello dell'intero oggetto lo dà il telefono in `BEGIN`; quelli dei prefissi alla fine di ogni livello (che il `DONE` vuole) si calcolano mentre i blocchi passano la prima volta in ordine. Se il CRC finale non torna con quello di `BEGIN` il ponte lo segnala (`crcMismatch`).
- **Posizione:** la posizione che il telefono manda (`POSITION`) ora va **nell'OFFER**, insieme al nominativo (prima il mittente non la metteva): il ricevente la tiene (`offerPos`).
- **Esiti verso il telefono:** `BEGIN_OK` con la stima del tempo al gradino attuale, `PROGRESS` dai pezzi confermati dal ricevente (a scatti del 10%, non più spesso di ogni 2 s), `DONE` consegnato / fallito / annullato; stesse regole di errore del ponte semplice (`NO_CALL`, `BAD_KIND`, `NO_POSITION`, `TOO_BIG`, `BUSY`). Senza byte dal telefono per 60 s l'invio si chiude fallito; `CANCEL` ferma subito la stazione.
- **Dalla radio al telefono:** il ricevente accetta un'offerta **solo col telefono collegato**, con la scheda non occupata a mandare e se l'oggetto sta nella RAM (`kRxMax` = 32 kB sulla scheda). Altrimenti l'OFFER resta senza risposta e il mittente chiude con "offerta" (prova: 75 s). Quando arriva un oggetto con CRC giusto il telefono riceve `E_RX` (tipo, dimensione, CRC dei byte consegnati, nominativo) e poi i byte su `data_out` a pezzi da 48 byte (MTU minimo 64), 4 pezzi per giro. Se si consegna solo un prefisso (budget scaduto a un livello intermedio) il telefono riceve quel prefisso.

**Cosa si vede nelle prove.** Testo da 200 B a −100 dBm: consegnato in 6 s. Immagine da 20 kB a −118 dBm: 57 s, 20 richieste di blocchi, oggetto identico al telefono B. Caduta del BLE di 6 s a metà: consegnato (21 s). Oggetto da 64 kB tra SX1262 a −100 dBm: 42 s. Andata e ritorno tra due telefoni. Telefono sparito: dopo 60 s l'invio si chiude fallito e il `RESUME` successivo lo dice. Destinatario senza telefono o con oggetto troppo grande: l'invio fallisce, nessun `E_RX`.

**Guscio:** `main_mobile.cpp` (NimBLE + `Station` + `BoardRadio` + `LiveBridge`), ambienti `mobile_t3` e `mobile_tbeam1262`; i vecchi ambienti col ponte semplice e radio simulata si chiamano `ble_sim_t3` e `ble_sim_tbeam1262`. **Nome Bluetooth:** `VoLoRa-V3 <NOMINATIVO>` (per esempio `VoLoRa-V3 IU5HJU`), così con più schede accese si riconosce quale scegliere; senza nominativo è `VoLoRa-V3`. Il nome cambia con `CALL`: se il nominativo è diverso da quello salvato la scheda **si riavvia** per annunciarlo (l'accoppiamento resta, ma Android può tenere in memoria il vecchio nome di una scheda già accoppiata: in quel caso "dimentica" il dispositivo e ricollega). La pagina del telefono cerca la scheda dal servizio, non dal nome, quindi non cambia. Seriale: `CALL <nominativo>`, `STATO`, `BOOST ON RISCHIO|OFF|STATUS` e, solo sull'SX1262, `IOF ON RISCHIO|OFF|STATUS` (+22 dBm, [boost.md](boost.md)). Il TCXO non si legge ancora (R12-R14 non si annunciano) e R3 sull'SX1278 è escluso come nel banco.

**Limiti e cose da guardare sulla scheda:**
- Il ritardo del BLE (la prova usa 100 ms più 15 ms ogni 100 byte) è un'ipotesi: se la scheda aspetta il telefono più della pazienza del ricevente, la finestra si allunga e il ricevente manda STATUS a vuoto. Il numero vero si misura con la pagina del telefono.
- Il ponte non conosce il "negozio" per chi non c'è: senza telefono la scheda non accetta oggetti. Quel lavoro è dei nodi e dei ripetitori.
- Tutto il carico (radio a ogni IRQ, notifiche BLE, 8 kB di cache, 32 kB per gli oggetti in arrivo) non è stato misurato sulla scheda.

## Da fare, in ordine
1. ~~**Guscio per la scheda del mobile**~~ **Scritto e compilato dalla CI** (vedi la sezione sotto). Non provato su una scheda.
2. ~~**Codec dei frame del protocollo immagini**~~ **Fatto** (`frames.h`).
3. ~~**Macchina a stati del protocollo immagini** in C++~~ **Fatta** (vedi la sezione sotto). Il piano seguito: **prima separata nel Python**: oggi il simulatore è un blocco unico in cui le due stazioni, il canale e il tempo sono intrecciati (`Simulator.exchange`, `phase_hello`, `phase_transfer`...). Il piano: (a) estrarre nel Python due classi indipendenti, **mittente** e **ricevitore**, che ricevono un frame o un tick e restituiscono frame da trasmettere, senza sapere nulla del canale; (b) far girare il simulatore sopra queste due classi senza cambiare i suoi risultati (le prove esistenti devono passare identiche); (c) registrare ingressi e uscite di ciascuna classe come per il ponte e portarle in C++ con gli stessi vettori. Incontro a R10, salita e discesa dei gradini, finestre, ritrasmissione selettiva, budget di tempo, ricerca dopo la perdita del collegamento.
4. **Driver radio** (RadioLib): modi LoRa e FSK dei 15 gradini, potenza, **BOOST** ([boost.md](boost.md)); la maschera dei gradini c'è già (`limits.h`). Qui servono le **misure** della fase 1 (tempi in aria reali, sensibilità, rendimento delle schede) prima di fidarsi dei numeri.
5. ~~**Il mezzo della scheda**~~ **Scritto e provato sul PC** (sopra); manca la **prova sulle schede** (`bench_t3`), ~~il **BOOST** (+20 dBm) nel driver~~ **fatto** ([boost.md](boost.md): `BOOST ON RISCHIO` sulla seriale, provato sul PC, non sulla scheda), **R3 sull'SX1278** (intestazione implicita), il **TCXO letto dalla scheda**. La **frequenza configurabile** è fatta (sezione "Frequenza configurabile"). Il **collegamento con il ponte Bluetooth** è fatto (sezione "Il ponte collegato al mezzo"): il mittente legge da una sorgente, il telefono è il buffer e la cache è di 8 blocchi.
6. **Ruoli dei nodi e dei ripetitori**: ascolto a turni, configurazione del sysop ([configurazione-nodo.md](configurazione-nodo.md)), microSD (solo nodi e ripetitori), voto, rete mesh.
7. **Gateway Internet** verso il reflector V3 (reflector già pronto in C++).

## Cosa NON è pronto per il firmware
- **Misure su schede vere** (fase 1): senza, i tempi in aria, le sensibilità e la deriva del quarzo sono stime. Il firmware di misura serve proprio a questo ed è ancora da provare.
- **Il protocollo radio V3 in C++** (punti 2 e 3): è tutto nel simulatore Python, non sulla scheda.
- **Ruolo "nodo"**: dipende dal protocollo radio.
