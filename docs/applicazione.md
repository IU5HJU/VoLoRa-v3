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
| `app/volora_misure/gui.py` | interfaccia Tkinter |
| `tests/app/` | prove della logica e dell'interfaccia |
