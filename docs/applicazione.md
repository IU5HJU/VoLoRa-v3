# Applicazione di prova (misure e, più avanti, immagini)

Programma con interfaccia grafica per fare le prove con meno fatica: **due monitor seriali** (scheda A e scheda B), **tasti rapidi**, una **tabella dei risultati**, la preparazione di **immagini fittizie** e l'**invio dei risultati su GitHub**. Funziona con il [firmware di misura](firmware-misura.md). Sta in [`app/`](../app).

> **Stato (21/11/2026): scritta e provata con schede finte, non ancora con schede vere.** La logica ha prove sul PC (`python3 tests/app/test_core.py`), l'interfaccia è provata con uno schermo virtuale e con schede finte che rispondono come il firmware (`tests/app/test_gui.py`). **Non sono provati**: il collegamento con la seriale vera, la comunicazione con GitHub (provata solo con una rete finta) e Windows/Mac (provata solo su Linux).

## Avvio
Serve Python 3.10 o successivo con Tkinter (su Windows e Mac è già incluso; su Linux `sudo apt install python3-tk`).
```bash
pip install -r app/requirements.txt
python3 app            # schede vere
python3 app --simulate # due schede finte, per vedere come funziona senza hardware
```
Su Windows: `py app`. Nessuna installazione: si lancia dalla cartella del progetto.

## Come si usa
1. Collega le due schede (firmware di misura già caricato, antenna o carico collegati) e per ognuna scegli la porta e premi **Collega** (921600 baud). Accanto al pulsante compare l'indicatore (`○ scollegata`, `… apro la porta`, `● collegata`, `✗ errore`, `✗ porta persa`) e nel monitor la riga `[sistema] collegata a ...`. L'apertura della porta riavvia la scheda: dopo circa due secondi l'app manda da sola `INFO` e compare il chip riconosciuto.
2. **F1** chiede `INFO` a entrambe. Scrivi il nominativo e premi **F2**.
3. Scegli il modo (L1-L13 LoRa, F1-F6 FSK, come in [scala-modi.md](scala-modi.md)) e premi **F3**: lo imposta su entrambe, con frequenza, potenza e dimensione del pacchetto.
4. Inserisci l'**attenuazione totale misurata** col NanoVNA e premi **F4**: la scheda scelta come trasmettitore (A o B) manda N pacchetti, l'altra ascolta, e nella tabella compare una riga con pacchetti ricevuti, perdita, RSSI, SNR e deriva di frequenza. Cambia l'attenuazione e ripeti.
5. **F8** salva il CSV; la scheda **GitHub** lo manda.

La riga dei comandi sotto ogni monitor accetta qualunque comando del firmware (`HELP`, `MODE ...`), con la cronologia sulle frecce.

## Prove sul campo con una scheda per stazione (22/11/2026)
Scheda **Prove sul campo**: ogni collega ha **una scheda** collegata al proprio computer; ci si accorda a voce (per esempio su un'altra banda) su ruolo e orario UTC.

1. **Orologio.** In alto compare l'ora UTC con la sorgente usata e la sua incertezza. Le sorgenti sono tre, e l'app sceglie quella con l'incertezza minore (le sorgenti più vecchie di 15 minuti si scartano):
   - **NTP**: premi "Sincronizza NTP" (server `pool.ntp.org`, cambiabile). Serve Internet (anche dal telefono in hotspot). Incertezza tipica: la metà del ritardo di rete, da pochi a qualche decina di millisecondi.
   - **GPS**: scegli la porta (seriale o USB, per esempio `/dev/ttyACM0`), la velocità (di base 9600) e premi "Collega GPS". Legge le frasi NMEA (RMC, GGA, ZDA, con somma di controllo) e mostra fix, satelliti, HDOP, posizione e locatore. **Senza PPS l'ora dalle frasi ha un'incertezza onesta di circa ±0,4 s**: il ricevitore può ritardare la frase di 100-500 ms e non lo sappiamo. Con un GPS che porta il segnale **PPS sul pin DCD** dell'adattatore seriale, spunta "PPS sul pin DCD": lo scarto è allora quello del fronte, con incertezza di pochi millisecondi.
   - **Computer**: se non c'è altro si usa l'orologio del computer, con 1 s di incertezza dichiarata.
   - Se hai sia GPS sia NTP, la riga mostra la **differenza fra i due** (un controllo incrociato).
2. **Le stazioni.** La mia posizione viene dal GPS (se ha il fix) oppure dalla casella scritta a mano (`lat,lon` o locatore). Per il collega scrivi nominativo e posizione, oppure li importi con la sua riga (punto 4). L'app calcola **distanza e direzione**.
3. **Appuntamento.** Scegli il ruolo (Trasmetto o Ricevo) e la scheda, scrivi **T0 in UTC** (`2026-11-22 10:30:00` oppure solo `10:30:00`) e premi "Programma la prova". Modo, frequenza, potenza, pacchetto, quanti e intervallo sono quelli della scheda Misure (devono essere uguali). L'app configura la scheda e poi **aspetta l'ora esatta** con l'orologio scelto; chi riceve parte con un anticipo (di base 5 s) e ascolta fino a 10 s dopo l'ultimo pacchetto. Un conto alla rovescia mostra i secondi. "Copia le condizioni per il collega" mette negli appunti una frase da leggere o incollare. L'orario deve essere almeno 5 s nel futuro.
4. **Risultati.** Finita la prova la riga compare nella tabella, con l'errore di partenza (ms) e la sorgente dell'orologio. **Copia i miei dati** mette negli appunti una riga `VOLORA-PROVA 1 call=... loc=... lat=... lon=... t0=... role=... mode=... ...`; il collega la incolla con **Incolla i dati del collega…**: l'app unisce le due metà (il trasmettitore ha i pacchetti inviati, il ricevitore quelli ricevuti, RSSI, SNR e deriva), calcola **perdita e distanza** e **avvisa** se gli orari differiscono di più di 5 s, se i modi o le frequenze sono diversi, o se i conteggi non tornano. "Salva CSV di rilievo" scrive un file con le colonne di `docs/misure/modello-rilievo.csv`.

**Con una scheda sola F5 e F6 funzionano** (F5 trasmette, F6 ascolta sulla scheda collegata). F4 (misura completa) resta per due schede sullo stesso computer.

**Cosa NON è provato:** NTP e GPS **veri** (la logica è provata con un server NTP finto in locale e con frasi NMEA finte, anche con PPS), la scheda con una seriale vera, e il comportamento su due computer. Il limite sull'orario di partenza è quello dell'orologio meno preciso fra i due, più il tempo che la scheda impiega a cominciare dopo il comando (millisecondi, trascurabili rispetto ai tempi in aria di LoRa).

## Tasti rapidi
| Tasto | Azione |
|---|---|
| F1 | `INFO` a entrambe |
| F2 | `CALL` (nominativo) a entrambe |
| F3 | modo, frequenza, potenza e pacchetto su entrambe |
| F4 | un punto di misura, con riga di risultato |
| F5 | solo TX |
| F6 | solo RX per 60 s |
| F7 | portante per il misuratore di potenza (10 s) |
| Esc | **STOP** immediato |
| F8 | salva il CSV |
| F9 | scheda GitHub |
| Ctrl+L | pulisce i monitor |

## Invio dei risultati su GitHub
- **2a, senza token (per tutti):** apre nel browser la pagina "nuova segnalazione" del repository già compilata con le note e la tabella; tu **allegi il CSV** e invii. Se il testo è troppo lungo per l'indirizzo viene accorciato (il CSV completo si allega).
- **2b, con un token (per i collaboratori con permesso di scrittura):** crea un ramo `misure/NOMINATIVO-data`, carica CSV e note in `docs/misure/` e apre una **richiesta di modifica** (PR). Il token si crea in GitHub (Settings, Developer settings) con permesso di scrittura sul repository; **non viene salvato** se non spunti "Ricorda" (in quel caso sta in chiaro in `~/.config/volora-misure/config.json`, con permessi ristretti).
- Le note e i nomi delle schede si scrivono nella stessa scheda. **Privacy:** niente coordinate precise di casa nelle note, solo il locatore a 6 caratteri.

## Immagini di prova
La scheda **Immagini** prepara gli oggetti per le prove del [protocollo immagini](protocollo-immagini.md): un **blocco di byte pseudocasuali** di dimensione a scelta (con CRC32), uno **schema di prova PNG** a larghezza e altezza a scelta (gradiente, griglia, cerchio, barre) oppure un **JPEG progressivo** (serve Pillow). I file vanno in `~/volora-immagini/`. Per ogni oggetto mostra il **tempo stimato per ogni gradino** della scala (da `tools/protocollo_immagini.py`), per la coppia SX1278 o SX1262.
**L'invio via radio non c'è ancora**: serve il firmware della fase 3. L'applicazione è fatta perché la stessa scheda diventi il punto di invio quando il firmware lo permetterà.

## Come è fatta
| File | Contenuto |
|---|---|
| `app/volora_misure/core.py` | logica: modi, righe della seriale, CSV, note, GitHub, immagini, impostazioni |
| `app/volora_misure/serialio.py` | porta seriale vera e schede finte |
| `app/volora_misure/runner.py` | sequenza di una misura fra due schede |
| `app/volora_misure/timesync.py` | orologio, NTP, GPS (NMEA e PPS), appuntamento |
| `app/volora_misure/geo.py` | distanze, direzioni e locatore Maidenhead |
| `app/volora_misure/field.py` | righe di scambio, unione dei risultati e CSV di rilievo |
| `app/volora_misure/gui.py` | interfaccia Tkinter |
| `tests/app/` | prove della logica e dell'interfaccia |
