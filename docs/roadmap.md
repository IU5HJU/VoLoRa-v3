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
- Bozza calcolata della scala in [scala-modi.md](scala-modi.md): da sostituire con le misure; piano in [piano-misure.md](piano-misure.md).
- Per ogni modo: throughput reale, tempo in aria, sensibilità, banda occupata, perdita di pacchetti.
- Rendimento delle schede e delle antenne agli estremi della gamma (430 e 440 MHz).
- **Esito:** tabella modo, velocità, soglia SNR, portata stimata.

## Fase 1b: prove a distanza reale, con i colleghi radioamatori
- Materiale da condividere: [materiale.md](materiale.md). Guida per chi collabora: [guida-colleghi.md](guida-colleghi.md). Protocollo e scheda di rilievo: [prove-sul-campo.md](prove-sul-campo.md). Prova dei gradini lenti in laboratorio: [prova-gradini-lenti.md](prova-gradini-lenti.md).
- Primo passo: un volontario prova il firmware di misura a banco, prima di distribuirlo.

## Fase 2: base comune dei firmware
- Firmware di misura già scritto (non provato su schede): [firmware-misura.md](firmware-misura.md).
- **Firmware V3 (26/11/2026): iniziato dal nucleo** (ponte telefono-scheda in C++ uguale al riferimento Python, byte per byte, provato sul PC): [firmware-v3.md](firmware-v3.md). Mai eseguito su una scheda.
- Strato radio unico LoRa/FSK, driver SX1278 e SX1262.
- Build di più firmware (uno per ruolo e per scheda) dallo stesso codice.
- Livello di compatibilità v2 per voce, messaggio vocale e testo, verificato con i test della v2; **la v2 non si modifica** ([compatibilita-v2.md](compatibilita-v2.md)).

## Fase 3: protocollo immagini
- Logica mesh voluta (beacon, polling, ripetitori, ricezione da più stazioni): [mesh-v3.md](mesh-v3.md), bozza del 23/11/2026.
- Fatto sul PC (23/11/2026, non provato su schede): simulatore mesh con terminali nascosti, codice a fontana ([`tools/fontana.py`](../tools/fontana.py)), frame mesh e posizione ([`tools/frame_mesh.py`](../tools/frame_mesh.py)), elezione e voto fra due nodi in isofrequenza ([voting-isofrequenza.md](voting-isofrequenza.md)), spiegazione dei [terminali nascosti](terminali-nascosti.md).
- Regola: l'infrastruttura v2 non si modifica; il V3 è retrocompatibile solo per voce, messaggio vocale e testo ([compatibilita-v2.md](compatibilita-v2.md)); Internet non è un mezzo affidabile, annunci e voti vanno via radio.
- Bozza v0.1: [protocollo-immagini.md](protocollo-immagini.md) (scritta il 21/11/2026, prima delle misure).
- Simulatore sul PC: [simulatore-immagini.md](simulatore-immagini.md) (corregge la bozza in quattro punti, tre problemi aperti).
- Codifica a livelli: prima una versione piccola e utile, poi i raffinamenti.
- Frammentazione con pacchetti numerati; conferme selettive o correzione d'errore (Reed-Solomon o fountain), scelta in base alle misure della fase 1.
- Budget di tempo in aria e passi di ridimensionamento.
- Simulatore sul PC con perdite e rumore, prima delle schede.

## Fase 4: negoziazione del collegamento
- Incontro nel modo più robusto.
- Misura di RSSI, SNR e perdite, salita a gradini.
- Discesa se il canale peggiora; timeout che riporta al modo robusto se il cambio non è confermato.
- L'immagine si ridimensiona in base al modo concordato.

- **Cambio di banda** (profilo fisico, per esempio 2,4 GHz) quando il collegamento è molto forte: frame pronti sul PC, procedura al punto 7b di [protocollo-immagini.md](protocollo-immagini.md). Con l'hardware che c'è: moduli Ebyte UART come profilo 2, scheda di prova nell'applicazione, misure da fare ([modulo-2g4-uart.md](modulo-2g4-uart.md)).

## Fase 5: integrazione e prove
- Compatibilità v2 e V3 su schede vere.
- Prove a banco, in casa, sul campo a varie distanze.
- Immagini via ripetitore e reflector, se deciso.

## Fase 6: candidata al rilascio
- Documenti e pagina di installazione per ruolo, note di rilascio, registro delle prove.
