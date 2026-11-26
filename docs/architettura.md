# Architettura (bozza, da discutere)

## Principio
Ogni dispositivo ha **un compito solo** e un firmware che fa soltanto quello. Dallo stesso codice comune si producono più firmware, uno per ruolo e per scheda.

## Ruoli candidati

| Ruolo | Funzione unica | Note |
|---|---|---|
| Nodo voce/testo | voce e testo in protocollo v2 | compatibile con le stazioni v2 |
| Nodo immagini | invio e ricezione di immagini | LoRa e FSK, negoziazione del modo |
| Ripetitore RX | ascolta e configura la TX | come oggi, firmware dedicato |
| Ripetitore TX | trasmette | come oggi, firmware dedicato |
| Nodo mesh (deciso il 25/11/2026) | beacon, polling, ripetizione e invio dei trasferimenti | ruolo a sé, a 433 MHz; ascolto a R10; **due radio con una sola antenna collineare bibanda e un duplexer 2 m / 70 cm** (voto a 144,850 MHz, deciso il 26/11/2026) |
| Nodo a due bande (ipotesi) | trasferimenti veloci a 2,4 GHz con la banda 430-440 MHz come incontro e ripiego | due radio: una T3 a 433 MHz e un **modulo Ebyte E28-2G4T27SX** (UART, già a disposizione dell'autore, [modulo-2g4-uart.md](modulo-2g4-uart.md)); in alternativa una T3-S3 con SX1280 |
| Nodo Internet | porta i pacchetti al reflector | gateway; **solo aiuto alla sperimentazione**, non fa parte del collegamento radio affidabile |

Da decidere: se le immagini passano da ripetitore e reflector.

## Schede e radio
- LilyGo LoRa32 T3 V1.6.1 (SX1278) e T-Beam V1.2 (SX1278 o SX1262).
- Le due radio hanno FIFO diversi (64 e 256 byte circa) e prestazioni diverse in FSK: da verificare sui datasheet e a banco (fase 1).

## Memoria e microSD (T3)
La T3 non ha PSRAM ma ha lo slot microSD. Nei ruoli senza audio (nodo immagini, nodo Internet) può servire per frammenti, coda e archivio. Dettagli e cautele in [scheda-sd.md](scheda-sd.md).

## Strati
1. **Radio**: LoRa e FSK dietro la stessa interfaccia, driver SX1278 e SX1262.
2. **Collegamento**: scala dei modi, misura del canale, negoziazione.
3. **Trasporto immagini**: frammentazione, conferme o correzione d'errore.
4. **Codifica immagine**: a livelli, dal più piccolo ai raffinamenti.
5. **Compatibilità v2**: voce e testo, dal submodule.

## Vincoli
- **Compatibilità v2 (deciso il 23/11/2026):** l'**infrastruttura v2 esistente resta senza modifiche**; il V3 è retrocompatibile solo per voce, messaggio vocale e testo del protocollo v2. Dettagli in [compatibilita-v2.md](compatibilita-v2.md).
- **Internet (deciso il 23/11/2026):** è solo uno strumento per agevolare la sperimentazione, **non** un mezzo di comunicazione affidabile. Nulla di essenziale al protocollo (annunci, voto, coordinamento fra nodi) deve dipendere da Internet; l'orologio è NTP se c'è Internet, GPS se non c'è.
- **Frequenze (deciso il 21/11/2026, precisato il 23/11/2026):** libere fra **430 e 440 MHz**, la gamma attribuita al servizio di radioamatore, senza limiti di larghezza di banda né di band plan: lo studio non entra nella divisione in fette fra i servizi, che cambia da paese a paese. Le modalità si scelgono per prestazioni e robustezza. La banda però è **condivisa e non larga**: si lavora il più possibile in **isofrequenza** (vedi [voting-isofrequenza.md](voting-isofrequenza.md)).
- Identificazione periodica del nominativo, nessuna cifratura dei contenuti.
- Tempo in aria massimo per immagine (budget da fissare).
