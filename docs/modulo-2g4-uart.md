# Il modulo a 2,4 GHz con interfaccia seriale (Ebyte E28-2G4T27SX)

> **Principio (24/11/2026): si usa quello che si ha.** I moduli a 2,4 GHz che l'autore ha a disposizione sono gli **Ebyte E28-2G4T27SX** su scheda di prova USB (UART, 27 dBm). Il progetto li usa **così come sono**, in spirito radioamatoriale, invece di aspettare l'hardware ideale.
>
> **Stato: strumenti scritti e provati sul PC con moduli finti. Nessuna prova con moduli veri.** I dati sul modulo vengono da risultati di ricerca e da estratti di manuale; **non ho potuto leggere il manuale completo** (i siti non sono raggiungibili dalla sessione). Tutto ciò che è marcato "da verificare" va controllato sul manuale e misurato.

## 1. Cosa è e cosa non è (da verificare sul manuale)
- Modulo **UART a trasmissione trasparente** con firmware interno: la seriale entra, la radio esce. **Non** è il modulo SPI (E28-2G4M27S/SX) che si pilota registro per registro con RadioLib.
- Chip: **SX1281** secondo il titolo del prodotto; alcune pagine del manuale dicono SX1280 (da chiarire con la marcatura).
- Dichiara LoRa, FLRC e GFSK; velocità d'aria da 1 kbps a 2 Mbps; **27 dBm**; configurazione con i piedini **M0/M1** (forse M2); pin **AUX** per "pronto"; canale = 2400 + CHAN × 1 MHz (velocità basse) o × 3 MHz (1M); modo RSSI a 9600 8N1.
- **Non si possono scegliere** larghezza di banda e SF come con il chip nudo: la velocità d'aria è un numero della configurazione, la modulazione la decide il firmware del modulo.
- **Non si ha** l'RSSI e l'SNR di ogni pacchetto (da verificare: c'è un modo RSSI), né il CAD, né la deriva di frequenza, né i tempi in aria controllati.

## 2. Come lo usa il V3: profilo 2 "tubo opaco"
Nel frame `BAND-SET` il campo **profilo** vale **2** (`PROFILE_2G4_UART`): un trasferimento veloce su un tubo che porta byte da una stazione all'altra. Il resto del protocollo non cambia ([protocollo-immagini.md](protocollo-immagini.md), punto 7b):
1. **Incontro e controllo sulla banda base** (430-440 MHz, T3 come oggi): HELLO con l'opzione `profili` (profilo 0 e 2), la qualità del collegamento, il BAND-SET e il BAND-ACK.
2. **Dati sul modulo UART:** i frame DATA e STATUS passano nel tubo, **incapsulati** ([`tools/uart_frame.py`](../tools/uart_frame.py)): COBS, CRC16 e delimitatore. Il tubo spezzetta il flusso a piacere e un pacchetto perso lascia un buco: con l'incapsulamento chi riceve si risincronizza e scarta i frame rovinati, che poi il protocollo a finestre richiede di nuovo. **Costo: 4 byte per frame da 100 byte.**
3. **Ripiego:** se la raffica di prova non passa, o se per un tempo `G` non arriva nulla, si torna alla banda base, come per ogni cambio di banda.
4. **La banda base resta il canale di controllo** (e in un nodo con due radio resta in ascolto per beacon e mesh).

**Due modi d'uso, con una differenza grande:**
- **A. Banco con la scheda di prova USB.** I piedini M0/M1 sono ponticelli: **canale e velocità d'aria si impostano a mano, una volta**, uguali sui due moduli. Il BAND-SET non può riconfigurare nulla: "passare al profilo 2" vuol dire "usare il tubo già impostato". Un solo canale e una sola velocità per prova.
- **B. Nodo con un ESP32 che comanda M0/M1/AUX.** Si può cambiare il canale (per evitare il Wi-Fi) e la velocità a ogni BAND-SET, ma il cambio di modo costa tempo (da misurare: attese su AUX) e va gestito con il ripiego.

## 3. Cosa si può provare subito: la scheda "Modulo 2,4 GHz (UART)" dell'applicazione
Nella scheda **Modulo 2,4 GHz (UART)**:
1. Collega **due moduli** al computer (due porte USB-seriale), configurali con lo **stesso canale e la stessa velocità d'aria**, uguale baud e parità sulla seriale (valori di partenza 9600 8N1: poi alzali).
2. Scegli le due porte, il numero di byte per frame (per esempio 100), quanti frame, l'intervallo, e premi **Prova A→B**. In alternativa **Solo invio** su un computer e **Solo ascolto** sull'altro, per una prova a distanza.
3. L'applicazione scrive una riga `UARTSUM`: inviati, ricevuti, scartati dal CRC, perdita %, **velocità in kbit/s**, **latenza media e massima** (con i due moduli sullo stesso computer l'orologio è uno solo, quindi la latenza è vera).
4. Ripeti per: dimensioni diverse (40, 100, 200 byte), velocità d'aria diverse, **distanze** diverse, con **attenuatore** in serie, a **potenze** diverse, e con il Wi-Fi acceso e spento.

## 4. Misure da fare (tutto da verificare)
| Misura | Perché |
|---|---|
| Dimensione massima del pacchetto d'aria e comportamento con frame più lunghi | Decide la dimensione dei frame del profilo 2 (di partenza si assumono 200 byte) |
| **Velocità vera in funzione di baud e velocità d'aria** | La seriale può essere il collo di bottiglia: a 115200 baud si arriva al massimo a circa 92 kbit/s, anche se la radio dichiara 2 Mbps. Il guadagno rispetto al 433 MHz (R3 circa 37 kbit/s lordi) dipende da questo |
| Latenza di andata e commutazione tx/rx | Per la finestra e i tempi di guardia del protocollo |
| **Portata e perdita contro distanza e attenuazione** | Si confronta con la stima: il 2,4 GHz perde circa 15 dB in più dello spazio libero a 433 MHz |
| Se il modulo dà l'**RSSI** (e come) | Serve alla soglia `M_banda` per decidere il cambio di banda |
| Effetto del **Wi-Fi** sul collegamento (e viceversa) | Il 2,4 GHz è condiviso; per questo la scelta del canale per misura è importante |
| Tempo per **cambiare canale e velocità** (modo B) | Decide se la riconfigurazione a ogni BAND-SET è accettabile |
| Corrente in trasmissione e alimentazione | A 27 dBm la corrente è alta: verificare se l'USB basta |

## 5. Cosa non si può fare con questi moduli
- Misurare sensibilità per modo, larghezza di banda e SF come per le T3: non sono esposti.
- Il **voto fra due nodi** e il **canale di servizio**: vanno su radio che si controllano bene; restano sulla banda base.
- Il **ranging** (non c'è nel SX1281, e comunque il firmware non lo espone).

## 6. Cosa serve per andare oltre
1. Il **manuale completo** (incollato qui, o con l'accesso ai siti del manuale abilitato): serve per la mappa dei registri, il pacchetto massimo, i valori di velocità e canale, l'RSSI.
2. **Due moduli** per ogni prova di collegamento.
3. Per il firmware V3 su ESP32 (modo B): i piedini M0, M1, AUX, TX e RX collegati ai GPIO. Se nel tempo arrivano i moduli SPI (E28-2G4M27S o SX), il profilo 1 userà quelli.

## 7. Frequenza e potenza
Nota dell'autore ([regole-radioamatoriali.md](regole-radioamatoriali.md)): in Italia i radioamatori possono usare fino a 500 W sia a 430-440 MHz sia a 2,4 GHz. I 27 dBm del modulo non sono un problema normativo per questo progetto; restano i limiti tecnici (alimentazione, calore, saturazione del ricevitore nelle prove a banco: **attenuatore sempre in serie**).
