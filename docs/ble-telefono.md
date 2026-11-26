# Telefono ↔ scheda via Bluetooth LE: testo, file e immagini (specifica v0.1, 26/11/2026)

> **Stato: specifica e simulatore sul PC. Nessun firmware, nessuna prova su schede o telefoni.** Il simulatore è [`tools/ble_bridge.py`](../tools/ble_bridge.py), le prove sono [`tests/sim/test_ble_bridge.py`](../tests/sim/test_ble_bridge.py). Il tempo di radio è un modello (`protocollo_immagini.estimate_seconds`), non una misura.

**Decisione dell'autore (26/11/2026): BLE** (non Bluetooth classico): funziona con Android e con iPhone e costa meno RAM sull'ESP32.

## 1. Idea
Il telefono è la **tastiera e la fotocamera** del nodo mobile. La scheda non sa cos'è un'immagine ([protocollo-immagini.md](protocollo-immagini.md), principio 1): riceve **byte** e li manda in radio come oggetto. Il telefono fa tutto il lavoro "intelligente": scrive il testo, sceglie il file, **comprime l'immagine** a pochi kB (livelli, ridimensionamento) e mostra l'avanzamento.

Il BLE non è il collo di bottiglia: 20 kB passano dal telefono alla scheda in circa **11 s con l'MTU peggiore (23 byte)** e in meno di 2 s con MTU 185 o più; la radio a R5 ne richiede 19, a R10 oltre 1000 (simulatore). Per questo la scheda tiene **l'intero oggetto in RAM** (o sulla microSD, più avanti) e il telefono lo carica *prima* che parta la radio.

## 2. Servizio GATT
Un solo servizio, **quattro caratteristiche**:

| Nome | UUID | Proprietà | Verso | Cosa porta |
|---|---|---|---|---|
| servizio | `c49a1433-9f1b-4af8-9826-951953e47edb` | | | |
| `cmd` | `…1434…` | scrittura **con risposta** | telefono → scheda | comandi (HELLO, POSITION, BEGIN, CANCEL, RESUME, RX_ACK) |
| `data_in` | `…1435…` | scrittura **senza risposta** | telefono → scheda | pezzi dell'oggetto da inviare |
| `evt` | `…1436…` | **notifica** | scheda → telefono | eventi (INFO, BEGIN_OK, CREDIT, STAGED, PROGRESS, DONE, ERR, RESUME, RX) |
| `data_out` | `…1437…` | notifica | scheda → telefono | pezzi di un oggetto ricevuto dalla radio |

(Nel simulatore `data_out` viaggia sullo stesso collegamento; gli UUID sono scelti a caso e non registrati.) MTU: si negozia il massimo; il carico utile ATT è **MTU − 3** e i pezzi hanno **5 byte** di intestazione.

**Accoppiamento:** obbligatorio con **codice a 6 cifre mostrato sullo schermo della scheda** (LE Secure Connections, con bonding); niente "Just Works". La chiave dei comandi SYSOP via radio è un'altra cosa e non passa dal BLE.

## 3. Frame (tutti i numeri in big-endian)
**Comandi** (`cmd`): `C_HELLO 0x01` (versione); `C_POSITION 0x02` (7 byte di posizione come in [mesh-v3.md](mesh-v3.md) 8c: locatore o GPS assoluta); `C_BEGIN 0x10`; `C_CANCEL 0x12` (oggetto 2); `C_RESUME 0x13` (oggetto 2); `C_RX_ACK 0x14` (oggetto 2).

**BEGIN** `0x10`: oggetto (2), tipo (1: **0 testo**, **1 file**, **2 immagine**), dimensione (3), CRC32 (4), larghezza (2), altezza (2), numero di livelli (1), fine di ogni livello (3 ciascuno, al massimo 8), destinatario (1 + ASCII, al massimo 12), nome del file (1 + UTF-8, al massimo 40).

**Dati** (`data_in`): oggetto (2), **offset** (3), byte. Solo **in ordine**: la scheda scarta ciò che non è l'offset atteso o supera il credito.

**Eventi** (`evt`): `E_INFO 0x80` (versione, chip, maschera dei gradini, memoria totale, tetto, posizione nota, nominativo); `E_BEGIN_OK 0x81` (**credito** 3, **tempo stimato di radio** 3 s, gradino 1); `E_ERR 0x82` (codice); `E_CREDIT 0x83` (credito 3, prossimo offset 3); `E_STAGED 0x84` (tutti i byte arrivati e CRC giusto: l'oggetto è in coda per la radio); `E_PROGRESS 0x85` (percento, gradino, secondi che mancano); `E_DONE 0x86` (esito 0 consegnato, 1 fallito, 2 annullato); `E_RX 0x87` (oggetto in arrivo dalla radio: tipo, dimensione, CRC, nominativo del mittente); `E_RESUME 0x88` (prossimo offset, credito).

**Errori:** 1 BUSY, 2 TOO_BIG, 3 NO_MEMORY, 4 NO_POSITION, 5 BAD_FRAME, 6 CRC, 7 BAD_KIND, 8 UNKNOWN_OBJ, 9 NO_CALL.

## 4. Come si invia (telefono → radio)
1. `C_HELLO` → `E_INFO`: il telefono sa chip, gradini, memoria e se la scheda conosce la posizione.
2. **Posizione:** se la scheda non ha un GPS proprio, il telefono manda la **sua** posizione (`C_POSITION`, locatore o GPS assoluta). **Senza posizione la scheda rifiuta (NO_POSITION)**: ogni collegamento porta nominativo, rapporto e posizione ([regole-radioamatoriali.md](regole-radioamatoriali.md)).
3. `C_BEGIN` → `E_BEGIN_OK` con **credito** e **tempo stimato di radio**: il telefono può mostrare "circa 19 s a R5" e lasciar decidere. Errori subito: troppo grande, memoria, occupato.
4. Dati a **finestre da 2 kB**: la scheda dà credito, il telefono manda fino al credito, la scheda rinnova (`E_CREDIT`). Serve perché la scrittura senza risposta può perdere pacchetti se la coda della scheda si riempie.
5. A fine dati la scheda verifica il **CRC32** → `E_STAGED` (o `E_ERR` CRC). Da qui la radio la trasmette con il protocollo immagini e il telefono vede `E_PROGRESS` e `E_DONE`.
6. **Annullare:** `C_CANCEL`, anche durante la radio: la RAM si libera e niente parte (o la trasmissione si ferma).

**Limiti (da misurare):** un oggetto alla volta (il secondo riceve BUSY); **testo fino a 1 kB, oggetto fino a 64 kB**, entro la RAM libera (di partenza **32 kB** per il ponte: la T3 non ha PSRAM; con la microSD si potrà salire); destinatario e nome corti.

## 5. Interruzioni
Il BLE si interrompe spesso (telefono in tasca, uscita dal raggio). La scheda tiene la sessione **60 s**; alla riconnessione il telefono manda `C_RESUME` e la scheda risponde con **l'offset da cui riprendere** e un credito nuovo. Si rimandano solo i byte in volo (qualche centinaio), non tutto il file. Se i dati erano già tutti arrivati, `C_RESUME` restituisce `E_STAGED` o l'avanzamento; se la sessione è scaduta, `UNKNOWN_OBJ`.

## 6. Ricezione (radio → telefono)
Un oggetto che arriva dalla radio si offre con `E_RX` e passa per `data_out` a pezzi con offset; il telefono controlla il CRC32 e manda `C_RX_ACK`: la scheda libera la copia. Se il telefono non c'è, l'oggetto resta nella scheda (microSD, quando c'è) e si offre alla prossima connessione: da definire.

## 7. Lato telefono
- **Pagina web** (Web Bluetooth: Chrome su Android e su computer; **Safari su iPhone non lo supporta**: per iPhone serve un'applicazione, per esempio un pacchetto con un involucro nativo o un browser che lo supporta). Decisione da prendere: pagina web, applicazione nativa o entrambe.
- Compressione dell'immagine a livelli sul telefono: il formato resta il punto aperto 5 di [punti-aperti.md](punti-aperti.md). Finché non c'è, il ponte porta qualunque file (anche un JPEG normale, a gradino unico).
- Mostrare sempre il **tempo stimato** (E_BEGIN_OK) prima di caricare un'immagine: a R10 anche 2 kB richiedono oltre 100 s.

## 8. Cosa è provato (sul PC) e cosa no
**Provato nel simulatore (49 controlli):** codec di tutti i frame; testo e file da 20 kB con MTU 23, 100, 185, 247 arrivano identici in radio; il carico sulla scheda è più veloce della radio anche con MTU 23; ETA corretto; il credito è rispettato; due interruzioni del BLE durante l'invio e ripresa dall'offset senza rimandare il file; annullamento prima e durante la radio; errori (nessuna posizione, troppo grande, memoria, occupato, tipo sbagliato, CRC, radio fallita); sessione abbandonata; ricezione dalla radio con CRC; 3000 frame casuali sulla scheda e 2000 sul telefono senza eccezioni.
**Non provato:** firmware ESP32 (NimBLE), RAM libera con BLE e radio insieme, consumo, MTU reale dei telefoni, perdite reali della scrittura senza risposta, pagina web o applicazione sul telefono, accoppiamento con il codice sullo schermo. Il collegamento BLE del simulatore è affidabile e non perde pacchetti salvo nelle interruzioni.

## 9. Da decidere
1. **Telefono:** pagina web (Android, computer), applicazione nativa (anche iPhone) o entrambe.
2. **RAM del ponte:** 32 kB di partenza; sulla T3 con microSD fino a 64 kB o più?
3. **Più oggetti in coda** (oggi uno solo).
4. **Ricezione senza telefono collegato:** dove si tiene l'oggetto e per quanto.
