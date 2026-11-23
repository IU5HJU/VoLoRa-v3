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
| Nodo Internet | porta i pacchetti al reflector | gateway |

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
- **Frequenze (deciso il 21/11/2026, precisato il 23/11/2026):** libere fra **430 e 440 MHz**, la gamma attribuita al servizio di radioamatore, senza limiti di larghezza di banda né di band plan: lo studio non entra nella divisione in fette fra i servizi, che cambia da paese a paese. Le modalità si scelgono per prestazioni e robustezza. La banda però è **condivisa e non larga**: si lavora il più possibile in **isofrequenza** (vedi [voting-isofrequenza.md](voting-isofrequenza.md)).
- Identificazione periodica del nominativo, nessuna cifratura dei contenuti.
- Tempo in aria massimo per immagine (budget da fissare).
