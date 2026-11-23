# Mesh V3: beacon, polling, ripetizione e ricezione da più stazioni (bozza)

> **Stato (23/11/2026): bozza di progetto, non implementata, non provata né sul simulatore né sulle schede.** Descrive la logica voluta dal responsabile del progetto (IU5HJU) e ci aggiunge numeri **calcolati** e punti da decidere. Le sole misure su schede vere che toccano questo documento sono quelle della prima prova a due T3 ([misure](misure/2026-11-22-iu5hju-t3-t3-l4-banco.md)).
> **Regola di progetto da rileggere:** nominativo, rapporto di segnale e posizione (locatore o GPS assoluta) sono elementi fissi e si trasmettono sempre: [regole-radioamatoriali.md](regole-radioamatoriali.md). Non si tratta nessuna privacy.

## 1. La logica voluta (appunti dell'autore)
1. **Ascolto nel modo di massima portata.** Ogni periferica V3, quando è in ascolto, sta nel modo radio di portata più estrema.
2. **Beacon ciclico con il solo nominativo.** Ogni tanto la periferica trasmette un beacon fatto **solo dal nominativo**. Chi lo sente sa chi è in portata radio e può tentare un collegamento. Il primo contatto può essere il solo nominativo (è lecito: vedi la regola).
3. **Protocollo anti collisione.** Le periferiche mitigano la trasmissione contemporanea.
4. **Polling verso il destinatario.** Quando l'operatore inserisce il nominativo del destinatario di un testo o di un'immagine, la periferica avvia un tentativo di polling con la stazione di quel nominativo, per capire se ci sono le condizioni per inviare il contenuto (regole da sviluppare a protocollo maturo).
5. **Scambio completo quando serve.** Dopo che le due stazioni si sono ascoltate con il solo nominativo, si scambiano **nominativo, rapporto di segnale e posizione** (GPS assoluta o locatore).
6. **Percorso diretto se le condizioni di portata sono accettabili.** La trasmissione ha luogo.
7. **Altrimenti via stazione terza, in stile mesh.** Più stazioni possono ripetere **contemporaneamente**.
8. **La ricevente ricostruisce da più fonti.** Riceve e identifica ogni singolo pacchetto che manca all'immagine e costruisce l'immagine con pacchetti che arrivano anche da stazioni diverse.

## 2. Livelli del collegamento
| Livello | Cosa si scambia | Quando |
|---|---|---|
| **0 - beacon** | solo nominativo | ciclicamente, da tutti |
| **1 - polling** | nominativo del destinatario, nominativo del mittente | quando l'operatore sceglie un destinatario |
| **2 - scambio** | nominativi, **rapporto di segnale** (RSSI e SNR misurati), **posizione** (GPS o locatore), capacità (gradini ammessi, memoria) | dopo che le due stazioni si sono ascoltate |
| **3 - trasferimento** | testo o immagine a pezzi, con le regole del [protocollo immagini](protocollo-immagini.md) | se le condizioni lo permettono (diretto) o via ripetitori |

**Ogni collegamento** (ogni trasferimento) contiene, almeno una volta, nominativo, rapporto e posizione: non esistono trasferimenti senza posizione.

## 3. Il beacon: quanto costa
Beacon di **7 byte**: tipo (1 byte) più nominativo compresso a 6 bit per carattere, 8 caratteri (6 byte). Per confronto, il beacon con la posizione (7 byte in più, come nel formato della v2) ne ha 14. Numeri **calcolati** con [`tools/mesh_beacon.py`](../tools/mesh_beacon.py).

Tempo in aria del beacon (CR 4/5, preambolo 8, intestazione esplicita, CRC), secondi

| byte | contenuto | R10 | R11 | R12 | R13 | R14 |
|---|---|---|---|---|---|---|
| 7 | solo nominativo (compresso) | 1.0 | 2.0 | 4.0 | 7.9 | 15.9 |
| 14 | nominativo + posizione | 1.2 | 2.3 | 4.6 | 9.3 | 18.5 |

**Togliere la posizione dal beacon fa risparmiare solo circa il 14 %**: a questi gradini una parte fissa (il preambolo, circa il **40 %** del totale per un beacon così corto) non dipende dai byte. Il tempo si recupera meglio con altre tre leve:

Beacon da 7 byte: quanto pesa la parte fissa e cosa fa risparmiare l'intestazione implicita, senza CRC, preambolo di 6 simboli

| gradino | totale | di cui preambolo | a lunghezza fissa | risparmio |
|---|---|---|---|---|
| R10 | 1.0 s | 0.4 s (40 %) | 0.8 s | 23 % |
| R11 | 2.0 s | 0.8 s (40 %) | 1.5 s | 23 % |
| R12 | 4.0 s | 1.6 s (40 %) | 3.0 s | 23 % |
| R13 | 7.9 s | 3.2 s (40 %) | 6.1 s | 23 % |
| R14 | 15.9 s | 6.4 s (40 %) | 12.2 s | 23 % |

1. **Beacon a lunghezza fissa** (intestazione implicita, senza CRC, preambolo di 6 simboli): circa **-23 %**.
2. **Beacon meno frequenti**, e adattivi: più rari se i vicini sono tanti o il canale è occupato, più frequenti se sono pochi.
3. **Un gradino di ascolto meno estremo.** Il beacon a R14 dura 16 s, a R12 4 s, a R10 1 s: è la leva più forte (vedi il punto 4).

Beacon solo nominativo (7 byte), un beacon ogni 10 minuti: probabilita' di arrivare senza collisione

| stazioni | R10 (senza / con slot) | R12 (senza / con slot) | R14 (senza / con slot) |
|---|---|---|---|
| 10 | 97 % / 98 % | 88 % / 94 % | 59 % / 77 % |
| 20 | 94 % / 97 % | 77 % / 88 % | 35 % / 59 % |
| 50 | 85 % / 92 % | 52 % / 72 % | 7 % / 27 % |
| 100 | 72 % / 85 % | 27 % / 52 % | 1 % / 7 % |

"Con slot" = trasmissioni sincronizzate dall'orologio (basta un'ora esatta entro 1 secondo, vedi [applicazione.md](applicazione.md)): ogni stazione trasmette nel proprio slot, calcolato dal nominativo.

## 4. Il "modo di massima portata": i vincoli veri
1. **R14 (banda 7,8 kHz) a 100 stazioni è inutilizzabile** (1 % senza coordinamento, 7 % con slot) e a 50 sta al 7-27 %. Il canale si riempie da solo.
2. **L'errore di frequenza fra due schede è un problema vero nei gradini stretti.** Fra le due T3 abbiamo **misurato circa 1,55 kHz (3,6 ppm)**, cioè il 20 % di una banda da 7,8 kHz e il 10 % di 15,6 kHz. Le T3 non hanno il TCXO: senza correzione automatica della frequenza (usando l'errore misurato sul beacon) due T3 potrebbero **non sentirsi a R13-R14**. Da misurare prima di fissare il gradino di ascolto.
3. **Il ricevitore ascolta un modo alla volta.** Se tutti ascoltano a R14, ogni primo contatto è a R14 (frame da decine di secondi): il polling iniziale è lento e il passaggio a modi più veloci va progettato (per esempio nel beacon o nel primo scambio, il gradino a cui "mi senti bene").
4. **Scelta da fare dopo le misure:** gradino di ascolto fisso (R12 o R10, più veloce e con meno collisioni) oppure R14 solo dove i vicini sono pochi (gradino adattivo, annunciato nel beacon).

## 5. Anti collisione: strumenti disponibili
Da scegliere e confrontare sul simulatore (nessuna è ancora decisa):
- **Ascolto prima di parlare** (il CAD del chip: rileva un preambolo LoRa in corso) e **ritardo casuale** prima di trasmettere.
- **Slot dall'orologio:** ogni stazione sceglie lo slot dal proprio nominativo (funzione di hash). Serve un'ora esatta entro 1-2 secondi (NTP o GPS: già disponibile nell'applicazione).
- **Intervallo del beacon adattivo** (più lungo con più vicini).
- **Priorità dei frame di controllo** (POLL, risposte) rispetto ai beacon.
- Nessun rilevamento di collisione durante la trasmissione (come in una normale fonia radio): si limita la probabilità e si ritrasmette.

## 6. Polling
1. L'operatore indica il nominativo del destinatario.
2. La periferica trasmette un **POLL** (nominativo mittente, nominativo destinatario) al gradino di ascolto, dopo l'ascolto del canale. Ritenta con attesa crescente (come l'HELLO del protocollo immagini).
3. Il destinatario risponde con il livello 2: **rapporto di segnale** con cui ha sentito il POLL, la sua **posizione** (GPS o locatore) e le sue capacità.
4. Il mittente calcola il **margine** a ogni gradino (come in [protocollo-immagini.md](protocollo-immagini.md)) e decide: **diretto** se c'è un gradino che dà un'attesa accettabile, **via ripetitori** altrimenti.

Se il destinatario non risponde ma si sente di altre stazioni (livello 0), si passa alla ripetizione (punto 7), con le stazioni più vicine per rapporto di segnale come candidate.

## 7. Ripetizione da una o più stazioni
Per quando la portata diretta non basta. Più ripetitori insieme sono voluti. Problemi e soluzioni:
- **Tempesta di rilanci** (tutti rilanciano lo stesso pezzo): ritardo casuale **proporzionale** alla distanza dal destinatario o al margine peggiore, **soppressione** se si sente un'altra stazione che ha già rilanciato quel pezzo, numero massimo di salti (2-3).
- **Chi sceglie i ripetitori.** Le posizioni dei vicini non sono nel beacon (solo nominativo): si conoscono dopo il livello 2. Opzioni: scambio di posizione fra vicini quando serve (scelta **geografica**: rilancia chi è più vicino al destinatario), oppure scelta in base al rapporto di segnale. La posizione è comunque parte fissa dello scambio.
- **Anti loop e duplicati.** Ogni oggetto ha un **identificativo globale** (nominativo di origine più contatore) e un contatore di salti: un pezzo già visto non si rilancia.
- **Memoria dei ripetitori.** Un ripetitore tiene i pezzi finché servono (la T3 ha 520 kB di RAM e nessuna PSRAM; la microSD può servire, vedi [scheda-sd.md](scheda-sd.md)).

## 8. Ricezione da più stazioni
Il [protocollo immagini](protocollo-immagini.md) indirizza i pezzi per posizione e il ricevitore tiene una mappa dei pezzi: **più sorgenti per lo stesso oggetto sono già nel disegno**, a patto di due cambi:
1. **Identificativo di oggetto globale** al posto della sessione casuale a 16 bit fra due sole stazioni.
2. **STATUS in broadcast:** il ricevitore comunica quali pezzi mancano a chiunque ascolti, e ogni stazione che li ha può rispondere. Con più ripetitori è utile evitare le risposte doppie (stesse regole di soppressione).
- **Variante con codici a fontana.** Invece di chiedere i pezzi mancanti, ogni ripetitore trasmette pezzi **codificati** diversi e il ricevitore ricostruisce l'immagine appena ne ha poco più del necessario, **da chiunque arrivino**. Non serve coordinare chi manda cosa. Costo: codifica e decodifica più pesanti sull'ESP32 e un poco di sovrapposizione. Da valutare sul simulatore contro la ritrasmissione selettiva.
- **Integrità:** CRC32 dell'oggetto verificato in fondo, indipendente dalla fonte dei pezzi.

## 9. Cosa cambia nel protocollo immagini già scritto
| Punto | Oggi | Con il mesh |
|---|---|---|
| Identificativo di sessione | 16 bit casuali, due stazioni | identificativo di oggetto globale (origine + contatore) e contatore di salti |
| HELLO / OFFER | nominativo, capacità | + **posizione** (locatore o GPS) e rapporto di segnale (regola fissa) |
| STATUS | risposta al mittente | anche in broadcast, con soppressione dei duplicati |
| Rendezvous | R10 fisso | gradino di ascolto da decidere (punto 4) |
| Flag dei frame | LAST, RETX... | + RELAYED (come nella v2) e salti |

## 10. Registro delle decisioni
| Data | Decisione | Fonte |
|---|---|---|
| 23/11/2026 | Il beacon contiene il **solo nominativo**. Poi, fra stazioni che si sono ascoltate, si scambiano nominativo, rapporto e posizione. | autore |
| 23/11/2026 | **Nominativo, rapporto di segnale e posizione (locatore o GPS)** sono elementi fissi di ogni collegamento. Nessuna privacy. | autore, [regole-radioamatoriali.md](regole-radioamatoriali.md) |
| 23/11/2026 | Il primo contatto può essere il solo nominativo. | autore |
| 23/11/2026 | Più ripetitori contemporanei, ricezione da più stazioni con identificazione dei pacchetti mancanti. | autore |
| 22/11/2026 | La precisione dell'orologio richiesta è bassa: NTP o GPS bastano (anche per gli slot). | autore, [applicazione.md](applicazione.md) |

## 11. Da decidere
1. **Quante stazioni** per zona (10? 50? 100?): determina tutto il beacon.
2. **Gradino di ascolto** (fisso R10 o R12, oppure adattivo con R14 dove i vicini sono pochi), dopo le misure dei gradini stretti fra schede vere.
3. **Anti collisione:** CAD più ritardo casuale, oppure slot dal nominativo, oppure entrambi.
4. **Intervallo del beacon** e se adattivo.
5. **Ripetizione:** scelta geografica o per rapporto di segnale; numero massimo di salti.
6. **Codici a fontana** oppure ritrasmissione selettiva dei pacchetti mancanti.
7. **Ruolo del firmware:** il nodo mesh fa beacon, polling, ripetizione e invio insieme. Va riconciliato con il principio "ogni firmware fa una cosa sola" o definito come ruolo a sé.
8. **Convivenza con la voce v2** sullo stesso canale (frequenza propria per il mesh?).

## 12. Piano
1. **Misura** in laboratorio dei gradini lenti (R11-R14) fra le due T3: fin dove si sentono senza correzione di frequenza.
2. **Simulatore mesh** (sul PC): carico del beacon con 10-100 stazioni, anti collisione, scelta dei ripetitori, ricostruzione da più sorgenti, fontana contro ritrasmissione.
3. **Frame**: aggiungere posizione e rapporto a HELLO e OFFER, identificativo globale dell'oggetto, salti, RELAYED.
4. **Firmware di prova** del beacon e del polling su due-tre schede.
