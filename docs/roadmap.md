# Roadmap

Le cifre sulle prestazioni radio sono da verificare: la fase 1 serve a misurarle.

## Fase 0: studio e decisioni (solo documenti)
- Requisiti e definizione di "ruolo specializzato".
- Ruoli (vedi [architettura.md](architettura.md)) e compatibilità con la v2.
- Limiti delle radio SX1278 e SX1262: prima bozza in [radio-limiti.md](radio-limiti.md) (da fonti secondarie, da confermare sui datasheet Semtech).
- Frequenze: libere fra 430 e 440 MHz, senza limiti di banda né di band plan (deciso il 21/11/2026). Resta l'identificazione con il nominativo e niente cifratura.
- **Esito:** documento di architettura e decisioni scritte ([punti-aperti.md](punti-aperti.md)).

## Fase 1: caratterizzazione del livello fisico (a banco, con la chiavetta SDR)
- Scala dei modi, dal più veloce al più robusto: FSK alto e basso bitrate, LoRa BW500 con SF basso, LoRa BW125 con SF alto, fino ai modi estremi (BW bassa, SF12, CR 4/8).
- Bozza calcolata della scala in [scala-modi.md](scala-modi.md): da sostituire con le misure.
- Per ogni modo: throughput reale, tempo in aria, sensibilità, banda occupata, perdita di pacchetti.
- Rendimento delle schede e delle antenne agli estremi della gamma (430 e 440 MHz).
- **Esito:** tabella modo, velocità, soglia SNR, portata stimata.

## Fase 2: base comune dei firmware
- Strato radio unico LoRa/FSK, driver SX1278 e SX1262.
- Build di più firmware (uno per ruolo e per scheda) dallo stesso codice.
- Livello di compatibilità v2 per voce e testo, verificato con i test della v2.

## Fase 3: protocollo immagini
- Codifica a livelli: prima una versione piccola e utile, poi i raffinamenti.
- Frammentazione con pacchetti numerati; conferme selettive o correzione d'errore (Reed-Solomon o fountain), scelta in base alle misure della fase 1.
- Budget di tempo in aria e passi di ridimensionamento.
- Simulatore sul PC con perdite e rumore, prima delle schede.

## Fase 4: negoziazione del collegamento
- Incontro nel modo più robusto.
- Misura di RSSI, SNR e perdite, salita a gradini.
- Discesa se il canale peggiora; timeout che riporta al modo robusto se il cambio non è confermato.
- L'immagine si ridimensiona in base al modo concordato.

## Fase 5: integrazione e prove
- Compatibilità v2 e V3 su schede vere.
- Prove a banco, in casa, sul campo a varie distanze.
- Immagini via ripetitore e reflector, se deciso.

## Fase 6: candidata al rilascio
- Documenti e pagina di installazione per ruolo, note di rilascio, registro delle prove.
