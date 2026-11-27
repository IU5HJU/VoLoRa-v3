# Telefono ↔ scheda via Bluetooth LE: testo, file e immagini (specifica v0.1, 26/11/2026)

> **Aggiornamento 27/11/2026 — la pagina deve stare nella scheda.** Chrome permette il Web Bluetooth solo da pagine https; una pagina servita dalla scheda (http) non può usarlo. Per le prove in laboratorio ("Internet non è affidabile") le schede `mobile_*` hanno quindi un **secondo trasporto**: la scheda crea il suo **Wi-Fi** e serve la pagina del telefono da `http://192.168.4.1`, e la pagina parla con la scheda via **WebSocket** (`ws://192.168.4.1/ws`) con **gli stessi comandi ed eventi**, ogni messaggio preceduto da un byte di canale (0 `cmd`, 1 `data_in`, 2 `evt`, 3 `data_out`). Il Bluetooth resta (ambienti `mobile_ble_*`). Evento nuovo, solo ponte collegato alla radio: **`E_DIAG 0x8A`** (obj 2, motivo 1, livelli 1, byte 3, gradino 1, % confermata 1, secondi 2): riepilogo di fine invio con il motivo di un fallimento ([prove-laboratorio-v3.md](prove-laboratorio-v3.md)). Vedi [firmware-v3.md](firmware-v3.md).

> **Stato: specifica e simulatore sul PC. Nessun firmware, nessuna prova su schede o telefoni.** Il simulatore è [`tools/ble_bridge.py`](../tools/ble_bridge.py), le prove sono [`tests/sim/test_ble_bridge.py`](../tests/sim/test_ble_bridge.py). Il tempo di radio è un modello (`protocollo_immagini.estimate_seconds`), non una misura.

**Decisione dell'autore (26/11/2026): BLE** (non Bluetooth classico): funziona con Android e con iPhone e costa meno RAM sull'ESP32.

## 1. Idea
Il telefono è la **tastiera e la fotocamera** del nodo mobile, e **il suo buffer**. La scheda non sa cos'è un'immagine ([protocollo-immagini.md](protocollo-immagini.md), principio 1): trasporta **byte**. Il telefono scrive il testo, sceglie il file, **comprime l'immagine** a pochi kB (livelli, ridimensionamento), **tiene l'oggetto intero** e mostra l'avanzamento.

**Regola dell'autore (26/11/2026): il buffer lo fa il telefono. La microSD è di esclusiva pertinenza dei nodi e dei ripetitori**, perché la configurazione hardware della modalità radio occupa tutti i pin, anche quelli della microSD. Quindi la **scheda mobile non ha la microSD** e ha poca RAM (la T3 non ha PSRAM): non può tenere l'oggetto.

Modello **a richiesta** (pull): la scheda non riceve l'oggetto in blocco, lo **chiede a blocchi da 1 kB** al telefono, quando la radio sta per averne bisogno. Tiene in RAM **al massimo 3 blocchi (3 kB)**: quello in trasmissione e i due successivi, e li libera appena trasmessi. Se la ritrasmissione selettiva ([protocollo-immagini.md](protocollo-immagini.md), principio 4) richiede un blocco già liberato, la scheda lo **richiede di nuovo** al telefono. Così la RAM della scheda non dipende dalla dimensione dell'oggetto (nel simulatore 64 kB passano con 3 kB di RAM), e la scheda non ha bisogno di nessuna memoria di massa.

Il BLE non è il collo di bottiglia: con MTU 23 (il peggiore) la radio a R5 è rimasta ferma ad aspettare il telefono meno dell'1% del tempo; anche a R3 (7 s per 20 kB) con MTU 185 aspetta poco. Se l'MTU è minuscolo e il gradino velocissimo, la radio può attendere un blocco: succede solo ai gradini più veloci.

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

**BEGIN** `0x10`: oggetto (2), tipo (1: **0 testo**, **1 file**, **2 immagine**), dimensione (3), **CRC32 dell'oggetto intero** (4, lo calcola il telefono e la scheda lo passa all'OFFER radio), larghezza (2), altezza (2), numero di livelli (1), fine di ogni livello (3 ciascuno, al massimo 8), destinatario (1 + ASCII, al massimo 12), nome del file (1 + UTF-8, al massimo 40).

**Dati** (`data_in`): oggetto (2), **offset** (3), byte: **solo in risposta a un `E_PULL`**. La scheda scarta ciò che non ha richiesto, o fuori ordine.

**Eventi** (`evt`): `E_INFO 0x80` (versione, chip, maschera dei gradini, **dimensione del blocco**, tetto, posizione nota, nominativo); `E_BEGIN_OK 0x81` (**tempo stimato di radio** 3 s, gradino 1, blocco 2); `E_ERR 0x82` (codice); **`E_PULL 0x89`** (offset 3, lunghezza 2: "mandami questi byte"); `E_PROGRESS 0x85` (percento, gradino, secondi che mancano); `E_DONE 0x86` (esito 0 consegnato, 1 fallito, 2 annullato); `E_RX 0x87` (oggetto in arrivo dalla radio: tipo, dimensione, CRC, nominativo del mittente).

**Errori:** 1 BUSY, 2 TOO_BIG, 4 NO_POSITION, 5 BAD_FRAME, 7 BAD_KIND, 8 UNKNOWN_OBJ, 9 NO_CALL (3 NO_MEMORY e 6 CRC sono riservati: con questo modello non servono).

## 4. Come si invia (telefono → radio)
1. `C_HELLO` → `E_INFO`: il telefono sa chip, gradini e se la scheda conosce la posizione.
2. **Posizione:** se la scheda non ha un GPS proprio, il telefono manda la **sua** posizione (`C_POSITION`, locatore o GPS assoluta). **Senza posizione la scheda rifiuta (NO_POSITION)**: ogni collegamento porta nominativo, rapporto e posizione ([regole-radioamatoriali.md](regole-radioamatoriali.md)).
3. `C_BEGIN` → `E_BEGIN_OK` con il **tempo stimato di radio**: il telefono può mostrare "circa 19 s a R5" e lasciar decidere. Errori subito: troppo grande, occupato, nessuna posizione.
4. La radio parte subito e la scheda manda `E_PULL` per i primi tre blocchi; il telefono risponde con i dati; a ogni blocco trasmesso la scheda chiede il successivo. Se un blocco manca, la radio **aspetta** (non perde la sessione).
5. A fine oggetto: `E_DONE` (consegnato o fallito). Durante la trasmissione, `E_PROGRESS`.
6. **Annullare:** `C_CANCEL`, anche durante la radio: la scheda si ferma e libera la RAM.

**Limiti:** un oggetto alla volta (il secondo riceve BUSY); **testo fino a 1 kB, oggetto fino a 64 kB** (tetto del ponte: lo decide il tempo di radio, non la RAM della scheda).

## 5. Interruzioni
Il BLE si interrompe spesso (telefono in tasca, uscita dal raggio). Alla caduta la scheda butta il blocco a metà e **continua la radio con quelli che ha in cache**, poi **aspetta**. Alla riconnessione il telefono manda `C_RESUME`: la scheda richiede i blocchi che le servono e la trasmissione riprende. **Non si rimanda niente di già trasmesso.** Se il telefono manca per **più di 60 s** con la radio ferma in attesa, la scheda abbandona la sessione; l'esito (consegnato, fallito, annullato) resta registrato e `C_RESUME` lo restituisce: così una notifica `E_DONE` persa nell'interruzione si recupera.

## 6. Ricezione (radio → telefono)
Un oggetto che arriva dalla radio si offre con `E_RX` e passa per `data_out` a pezzi con offset; il telefono controlla il CRC32 e manda `C_RX_ACK`: la scheda libera la copia. **Senza telefono collegato la scheda mobile non accetta oggetti dalla radio** (non ha dove tenerli: niente microSD, poca RAM): chi li manda li ritrasmette quando il telefono c'è. Il "negozio" che tiene gli oggetti per chi non c'è è il lavoro dei **nodi e dei ripetitori**, con la loro microSD.

## 7. Lato telefono: la pagina web (scritta il 26/11/2026)
La pagina è [`site/telefono.html`](../site/telefono.html) (si pubblica con il sito, accanto alla pagina del sysop). **Web Bluetooth: Chrome su Android e su computer; Safari su iPhone non lo supporta** (la pagina lo dice e spegne il pulsante): per l'iPhone servirà un'applicazione, ancora da scrivere.
- **Collegamento:** cerca la scheda per l'UUID del servizio, si abbona a `evt` e `data_out`, manda `HELLO` e mostra chip, nominativo e se la posizione è nota. Se il collegamento cade si **ricollega da solo** (attese 0,3, 1, 2, 4, 8 s) e manda `RESUME` per l'oggetto in corso.
- **Posizione:** GPS del telefono (assoluta) oppure locatore a 6 caratteri; la pagina non invia senza posizione se la scheda non ne ha una (la scheda rifiuterebbe comunque).
- **Testo** (fino a 1024 byte), **file** (fino a 64 kB) e **immagine**: l'immagine si ridimensiona e si comprime **nel telefono** fino a stare nel limite scelto (2, 5, 10, 20, 40, 64 kB), provando lati da 320 a 32 pixel e qualità da 0,8 a 0,2.
- **Invio:** `BEGIN` con CRC32, destinatario e nome; poi risponde alle richieste `E_PULL` a pacchetti da **240 byte** e **scende da sola a 100 e a 15 byte** se la scrittura è rifiutata (Web Bluetooth non dice l'MTU). Mostra il **tempo di radio stimato** dato dalla scheda, l'avanzamento in percento, "Consegnato", "Annullato" o l'errore in italiano; ha il pulsante **Annulla**.
- **Ricezione:** testo, immagine o file arrivati dalla radio, con il controllo del CRC32 e `RX_ACK` alla scheda.
- **Immagine a livelli:** la canvas scrive un JPEG normale e la pagina lo trasforma **senza perdite** in **JPEG progressivo a tre livelli** con [`site/jpeg_prog.js`](../site/jpeg_prog.js); il `BEGIN` porta la fine dei tre livelli (in byte, i primi due su confini di pezzo da 16). Dettagli e prove in [immagine-livelli.md](immagine-livelli.md).
- **Notifiche:** con l'MTU minimo (23) una notifica porta al massimo 20 byte, e `E_INFO` ed `E_RX` ne possono richiedere di più (13 o 12 byte più il nominativo): la scheda deve **chiedere un MTU di almeno 64** alla connessione (da verificare sul firmware).

## 8. Cosa è provato (sul PC) e cosa no
**Provato nel simulatore (42 controlli):** codec di tutti i frame; testo e file da 20 kB con MTU 23, 100, 185, 247 arrivano identici in radio **con al massimo 3 kB di RAM sulla scheda**; un oggetto da 64 kB (il tetto) passa con 3 kB; ogni blocco è richiesto una volta sola senza perdite; la radio aspetta il telefono meno del 10% del tempo anche con MTU 23; ritrasmissione selettiva: i blocchi già liberati sono richiesti di nuovo e il telefono rimanda solo quelli; due interruzioni del BLE durante la trasmissione senza riscaricare blocchi già trasmessi; telefono sparito oltre 60 s: la scheda abbandona e libera la RAM, e alla riconnessione il telefono riceve l'esito; annullamento durante la radio; errori (nessuna posizione, troppo grande, occupato, tipo sbagliato, radio fallita); dati non richiesti scartati; ricezione dalla radio con CRC, rifiutata senza telefono; 3000 frame casuali sulla scheda e 2000 sul telefono senza eccezioni.
**Pagina del telefono (59 controlli, `tests/page/run_telefono.js`, Chrome senza Bluetooth vero):** con una **scheda finta in JavaScript** che parla il protocollo (modello del ponte a richiesta con Web Bluetooth simulato): collegamento e INFO, UUID del servizio, posizione da locatore (7 byte), rifiuto senza posizione, testo, file di 5 kB con tre blocchi richiesti, file oltre 64 kB rifiutato dalla pagina, riduzione dei pacchetti a 15 byte quando la scrittura è rifiutata, caduta del collegamento a metà e `RESUME`, annullamento, errore NO_POSITION, ricezione dalla radio con `RX_ACK`, immagine compressa a meno di 5 kB e trasformata in JPEG progressivo con tre livelli nel BEGIN, tema chiaro e scuro, nessuno scorrimento orizzontale a 390 px, avviso senza Web Bluetooth.
**Non provato:** il Bluetooth vero (la pagina con un telefono e una scheda), firmware ESP32 (NimBLE), RAM libera con BLE e radio insieme (qui 3 kB di cache più i frame), latenza reale delle richieste sul BLE e quindi quanto aspetta la radio ai gradini veloci, consumo, MTU reale dei telefoni, perdite reali della scrittura senza risposta, pagina web o applicazione sul telefono, accoppiamento con il codice sullo schermo. Il collegamento BLE del simulatore è affidabile e non perde pacchetti salvo nelle interruzioni.

## 9. Da decidere
1. ~~**Telefono**~~ **Deciso il 26/11/2026: pagina web per prima** (Android e computer); l'applicazione nativa, anche per l'iPhone, dopo.
2. **Cache della scheda:** 3 blocchi da 1 kB nel ponte semplice (modello a tempo); **8 blocchi (8 kB) nel ponte collegato alla radio vera** (`live_bridge.h`: una finestra del protocollo vuole fino a 5 blocchi). Da misurare con RAM e latenza reali (blocchi più grandi se il BLE è lento, o più cache).
3. **Più oggetti in coda:** oggi uno solo, il resto lo tiene il telefono.
4. ~~**Ricezione senza telefono collegato**~~ **Deciso il 26/11/2026: un nodo o ripetitore con microSD tiene l'oggetto** per il mobile assente e lo consegna alla riconnessione (servizio "posta"). La scheda mobile resta senza memoria. Da definire: il protocollo di deposito e ritiro fra mobile e nodo, e per quanto tempo si conserva.
