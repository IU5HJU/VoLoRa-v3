# Compatibilità con la v2: la regola

> **Regola dell'autore (23/11/2026).** L'**infrastruttura v2 esistente resta com'è, senza modifiche**. Il protocollo V3 deve essere **retrocompatibile solo per il traffico voce, messaggio vocale e testo del protocollo v2**. Tutto il resto del V3 è aggiunto, separato, e non deve chiedere nulla alla v2.

Il codice e i documenti della v2 sono nel submodule `third_party/VoLoRa-v2` (versione `v0.1.0-rc.1`), **in sola lettura**: il progetto V3 non li modifica.

> **Principio d'uso (26/11/2026).** Un nodo V3 si usa **come un nodo v2, con le solite funzioni**, e in più ha una capacità maggiore di relazionarsi con gli altri nodi e con le radio mobili grazie alle caratteristiche del V3 ([configurazione-nodo.md](configurazione-nodo.md)).

> **Il reflector V3 sostituirà il reflector v2 (26/11/2026).** Poiché la v2 non si modifica, il nuovo reflector deve essere un **sostituto compatibile**: parla ai nodi v2 il protocollo v2 **invariato** (collegamento firmato, KEEPALIVE, contatore anti-ripetizione, modi voce, messaggio e testo) e ai nodi V3 il protocollo V3. Il suo progetto è da fare.

## 1. Cosa significa
1. **Nessuna modifica ai formati v2:** né ai pacchetti (modi 1-7, flag, sessione, nominativo, posizione), né al significato del bit `RELAYED`, né ai comandi del sysop, né al reflector.
2. **Le stazioni, i ripetitori e i nodi v2 già installati continuano a funzionare senza aggiornamenti.** Nessun campo nuovo nei pacchetti v2.
3. **Il V3 sa parlare v2** per **voce** (modi 1 e 4), **messaggio vocale** e **testo** (modo 7, compreso l'identificativo del ripetitore con `seq` = 1): stessi byte, stesse regole (CAD prima del PTT, sessione per PTT, doppia copia del testo, ecc.). Per questo il V3 riusa il codice v2 invece di riscriverlo.
4. **Tutto ciò che è nuovo** (immagini, beacon, polling, ripetitori a gruppo, fontana, VOTO) usa **frame V3** (`byte 0 = 0x30 | tipo`) e, dove serve, **un canale proprio**.

## 2. Perché i due mondi convivono
- Il ricevitore v2 scarta ogni pacchetto con versione diversa da 2 (`decodePacket` in `lib/voicecore/packet.cpp`: `if ((in[0] >> 4) != kProtocolVersion) return false;`, verificato il 23/11/2026). Un frame V3 non è né decodificato né interpretato da una stazione v2.
- **Il V3 non occupa nulla nei pacchetti v2:** il nodo V3 che ritrasmette voce v2 mette il bit `RELAYED` (bit 7 del **byte dei flag**, byte 4) esattamente come fa un ripetitore v2.

## 3. Cosa resta da tenere d'occhio (non è una modifica alla v2)
| Punto | Cosa succede | Gestione |
|---|---|---|
| Occupazione del canale | Un frame V3 non disturba la decodifica v2, ma **occupa il canale**; il CAD della v2 vede solo preamboli LoRa con i parametri della sua voce, quindi una trasmissione FSK o con altra banda **non è vista** da una stazione v2, che potrebbe trasmettere sopra | **Canale proprio** per il V3 (dentro 430-440 MHz) e CAD prima di trasmettere. Da verificare sul campo |
| Voting con un ripetitore v2 | Un ripetitore **v2** non può partecipare al voto (non sa cosa sia un VOTO) | Il voto è **solo fra nodi V3**. Un nodo V3 e un ripetitore v2 sulla stessa frequenza con copertura in comune restano, come oggi, un fatto da risolvere fra radioamatori. **Il protocollo non può risolverlo senza cambiare la v2.** |
| Mobile v2 non modificata | Non manda nessun campo "nodo scelto" | L'elezione è tutta **lato nodo** (qualità, memoria del vincitore per nominativo): non serve nulla alla mobile ([voting-isofrequenza.md](voting-isofrequenza.md)) |
| Nominativo nei pacchetti | In v2 il nominativo è **solo nel pacchetto START** (flag CALLSIGN): i pacchetti successivi portano solo la sessione | Il nodo V3 lega la sessione al nominativo dallo START; se lo START è perso, la sessione non ha nominativo e il voto non può dichiararlo (da trattare) |
| Schede con la beta.2 | Scartano i pacchetti con `RELAYED` | Come già nella v2 (nota di `docs/protocollo.md`): non sentono le copie ripetute, nessun disturbo |
| Identificazione del nodo | La v2 ha già l'identificativo del ripetitore (testo con `seq` = 1) | Il nodo V3 lo usa **tale e quale**; i beacon V3 sono separati |

## 4. Cosa verificare (da fare)
- **Test di compatibilità** con i vettori di prova della v2: pacchetti v2 di voce, messaggio vocale e testo passano dal codice V3 **senza cambiare un byte**.
- Una stazione v2 **non reagisce** ai frame V3 (verifica già fatta sul codice, da fare su schede).
- Una stazione v2 che trasmette in presenza di un trasferimento V3 sullo stesso canale: **coesistenza da misurare**.
- Il V3 sui moduli v2 esistenti: **nessun aggiornamento richiesto** alle schede v2.

## 5. Provato e non provato
- **Verificato sul codice v2** (lettura): il rifiuto della versione diversa da 2 e il significato di `RELAYED`.
- Nei test sul PC dello studio: i decodificatori V3 **scartano** i pacchetti v2 e viceversa (`tests/sim/test_frame_mesh.py`).
- **Non provato su schede:** niente di quanto sopra.
