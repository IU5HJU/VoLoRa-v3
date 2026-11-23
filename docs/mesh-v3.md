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
7. **Altrimenti via stazione terza, in stile mesh.** Più stazioni possono ripetere **contemporaneamente**, cioè far parte dello stesso gruppo di ripetitori (a turni sullo stesso canale: vedi il punto 8b).
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
Da scegliere e confrontare sul simulatore. **Esito del 23/11/2026:** l'ascolto prima di parlare da solo non basta con i **terminali nascosti** ([terminali-nascosti.md](terminali-nascosti.md)): per beacon e turni si usano gli **slot dall'orologio**. Gli strumenti:
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
- **Variante con codici a fontana.** Invece di chiedere i pezzi mancanti, ogni ripetitore trasmette pezzi **codificati** diversi e il ricevitore ricostruisce l'immagine appena ne ha poco più del necessario, **da chiunque arrivino**. Non serve coordinare **chi manda cosa**; il **quando** sì: i ripetitori trasmettono a turni (punto 8b). Costo: codifica e decodifica più pesanti sull'ESP32 e un poco di sovrapposizione. Da valutare sul simulatore contro la ritrasmissione selettiva. **Prima prova (23/11/2026):** il codice a fontana su GF(2) è in [`tools/fontana.py`](../tools/fontana.py); con generazioni di 128 pezzi servono in media **1,6 simboli in più**, anche con perdite del 30-50 % e con più membri (ESI = contatore × M + indice). Non è ancora provato su schede, né misurato il costo di calcolo sull'ESP32.
- **Integrità:** CRC32 dell'oggetto verificato in fondo, indipendente dalla fonte dei pezzi.

## 8b. Gruppo di ripetitori a fontana: protocollo comune e regola "pochi e veloci"
Appunto dell'autore del 23/11/2026: (1) le stazioni che trasmettono a fontana devono potersi comunicare **un protocollo comune**; (2) è preferibile **meno stazioni ma più veloci**: una stazione in scarsissima portata, che richiederebbe un protocollo molto lento, va **esclusa** per dare priorità a chi si ascolta meglio; (3) nel pacchetto deve esserci l'**informazione** che permette questa scelta.

### Il vincolo fisico (e una correzione al ragionamento precedente)
Su **una frequenza** trasmette una stazione per volta, e il ricevitore ascolta **un gradino per volta**. Quindi i ripetitori di un gruppo trasmettono **a turni** e **allo stesso gradino**. Ne seguono due cose:
- **Più ripetitori non moltiplicano la velocità.** Danno **copertura** e **diversità** (percorsi diversi, un ripetitore che cade non ferma il trasferimento), non più velocità sullo stesso canale. La velocità è quella del **gradino comune**.
- **Il gradino comune è quello del membro più debole.** Un solo ripetitore con collegamento scarso trascina tutti a un gradino lento. È esattamente la regola voluta dall'autore.

Esempio calcolato: cinque candidati, ciascuno con il gradino più veloce a cui ha almeno 6 dB di margine verso il ricevitore (R4, R5, R6, R7 e R10). Velocità netta dell'unico canale (SX1278):

| Stazioni nel gruppo | Gradino comune | Velocità | Rispetto alla migliore |
|---|---|---|---|
| 1 (A) | R4 | 19,99 kbit/s | 100 % |
| 2 (A, B) | R5 | 9,99 kbit/s | 50 % |
| 3 (A, B, C) | R6 | 5,68 kbit/s | 28 % |
| 4 (A, B, C, D) | R7 | 3,18 kbit/s | 16 % |
| 5 (A, B, C, D, E) | R10 | 0,17 kbit/s | **1 %** |

La quinta stazione fa scendere la velocità di **18 volte**. Va esclusa. Anche la seconda e la terza costano molto: per questo la regola deve avere dei **parametri** (punto "Regola di selezione").

### Come si stabilisce il protocollo comune
Quattro passi, tutti con frame del livello 2 (vedi punto 2 del documento):

1. **RICHIESTA-RIPETITORI** (dal mittente): "chi può aiutarmi a portare l'oggetto X al destinatario Y?" Contiene l'identificativo globale dell'oggetto, il destinatario, la dimensione.
2. **OFFERTA** (da ogni candidato): nominativo, **posizione** (GPS o locatore: regola fissa), **gradino massimo** a cui sente il mittente con almeno 6 dB di margine, **gradino massimo** a cui è sentito dal destinatario (se noto), i due **margini in dB**, i **codici supportati** (maschera di bit: ritrasmissione selettiva, fontana, versioni), la memoria libera.
3. **GRUPPO** (dal mittente): l'**elenco ordinato** dei membri ammessi e degli **esclusi** (che restano in riserva), il **gradino comune**, il **codice scelto** (il migliore supportato da tutti i membri, altrimenti la ritrasmissione selettiva), i **parametri del codice** (numero di simboli sorgente, dimensione del simbolo, seme), l'**assegnazione dei turni** e l'ora di inizio.
4. **CONFERMA o VETO** (dal destinatario): "ti sento a quel gradino" oppure "non sento il membro X a quel gradino". Il destinatario misura davvero i ripetitori che sente, e il suo veto vale.

Chi non è nell'elenco **tace** per quell'oggetto: la priorità è delle stazioni che si ascoltano meglio.

### Regola di selezione (proposta)
1. Ordina i candidati per **gradino massimo** verso il destinatario (il più veloce prima), usando come qualità di una stazione il peggiore fra i due margini (verso il mittente e verso il destinatario).
2. Scegli il **gruppo più piccolo di almeno N_min stazioni** (di base 2, per avere ridondanza) il cui **gradino comune non è più lento di una tolleranza T gradini** rispetto al migliore (di base 1).
3. Gli altri sono **esclusi** e restano in **riserva**: entrano se un membro cade.
4. **Isteresi:** un membro escluso rientra solo se il suo margine supera di almeno 3 dB la soglia per due finestre di fila.

I due parametri **N_min** e **T** vanno tarati sul simulatore e poi sul campo. **Prima taratura sul [simulatore mesh](simulatore-mesh.md) (23/11/2026):** usare tutti i candidati è la scelta peggiore (circa 64 minuti contro 4 a 25 km); N_min = 2 con T = 1 alza la probabilità di completare da 85 % a 91-93 % con un costo di tempo contenuto; una tolleranza grande (T = 4) è un errore (34 minuti). Modello stimato, non misure.

### Informazione nel pacchetto
- Nell'OFFERTA: **classe di qualità** = gradino massimo con 6 dB di margine (4 bit) e i **margini in dB** verso mittente e destinatario (1 byte ciascuno).
- Nel GRUPPO: per ogni nominativo un campo **AMMESSO / ESCLUSO / RISERVA** e il turno assegnato.
- Nello **STATUS** del destinatario (in broadcast): una **classifica** per stazione di quanti simboli utili sono arrivati, così il mittente può togliere o riammettere un membro durante il trasferimento.

### I simboli a fontana e i turni
- Ogni simbolo ha un identificativo **ESI** che, con il seme comune, definisce da quali pezzi è composto. Per non sovrapporsi, ogni stazione usa gli identificativi **ESI = contatore × M + posizione nel gruppo** (M = numero di membri): nessuna coordinazione sui contenuti.
- Il **quando** si coordina con i turni: assegnati nel GRUPPO e legati all'**orologio** (basta un'ora esatta entro 1 secondo, già deciso).

### Cose da decidere
1. Valori di **N_min** e **T**.
2. **Chi coordina**: il mittente (come proposto, ha il contenuto), oppure il destinatario (misura meglio le stazioni che sente).
3. Quali **famiglie di codici** supportare nella prima versione (di partenza: ritrasmissione selettiva e un solo codice a fontana).
4. Se i membri **si sentono fra loro**: se no, i turni devono bastare da soli per non collidere.

## 8b2. Terminali nascosti
Due stazioni che non si sentono fra loro ma sono sentite dallo stesso ricevitore si sovrappongono anche se ciascuna ascolta prima di parlare. Per questo il protocollo non si affida all'ascolto: **turni dall'orologio** assegnati nel GRUPPO, **VETO** del destinatario, **slot** per beacon e risposte. Spiegazione completa, risultati del simulatore ed esercizi: [terminali-nascosti.md](terminali-nascosti.md).

## 8c. Formato dei frame del mesh (23/11/2026)
Codificati e decodificati in [`tools/frame_mesh.py`](../tools/frame_mesh.py), provati in `tests/sim/test_frame_mesh.py` (andata e ritorno, frame troncati scartati). **Non provati su schede.** Tutti i numeri sono big endian, il byte 0 è `0x30 | tipo`.

**Campi comuni**
- **Nominativo compatto:** 6 byte = 8 caratteri da 6 bit (cifre, lettere, `/` e `-`). Un nominativo di 8 caratteri o meno entra sempre.
- **Posizione (7 byte):** byte 0 = 0 e **locatore** a 6 caratteri (per esempio `JN53ab`), oppure byte 0 = 1 e **latitudine e longitudine a 24 bit** (risoluzione circa 1,2 m e 2,4 m): è la regola fissa, locatore **o** GPS assoluta.
- **Identificativo globale dell'oggetto (2 byte):** CRC16 del nominativo di origine più un contatore: lo stesso per mittente, ripetitori e destinatario.
- **Salti e ripetuto:** nel flag del DATA (punto 4 di [protocollo-immagini.md](protocollo-immagini.md)).

| Frame | Tipo | Byte | Contenuto |
|---|---|---|---|
| BEACON | 13 | **7** | solo il nominativo compatto |
| POLL | 14/1 | 14 | chi chiama (6), chi è interrogato (6) |
| POLL-REPLY (livello 2) | 14/2 | 22 | nominativo (6), **posizione (7)**, **RSSI e SNR** del POLL (2), maschera dei gradini (2), codici (1), memoria (2) |
| RICHIESTA-RIPETITORI | 14/3 | 19 | id oggetto (2), nominativo di origine (6), destinatario (6), dimensione (3) |
| OFFERTA | 14/4 | 23 | id oggetto (2), nominativo (6), **posizione (7)**, gradino massimo verso mittente e verso destinatario (4+4 bit), **i due margini in dB** (2), codici supportati (1), memoria (2) |
| GRUPPO | 14/5 | 16 + 7 per membro | id oggetto (2), codice (1), gradino comune (1), simboli sorgente K (2), dimensione del simbolo (1), seme (2), **ora di inizio UTC** (4), numero di membri (1); per ogni membro nominativo (6) e **stato** (ammesso, escluso, riserva) con **turno** (1) |
| CONFERMA | 14/6 | 6 | id oggetto (2), esito 0 (1), gradino (1) |
| VETO | 14/6 | 12 | come CONFERMA con esito 1 e il nominativo del membro che il destinatario non sente al gradino scelto |

Lunghezze reali: BEACON 7, POLL 14, POLL-REPLY 22, RICHIESTA 19, OFFERTA 23, GRUPPO a due membri 30. A R14 ogni byte costa molto tempo in aria: per questo il beacon è di soli 7 byte e i frame con la posizione compaiono dal livello 2 in poi (dopo il primo contatto).

## 9. Cosa cambia nel protocollo immagini già scritto
| Punto | Oggi | Con il mesh |
|---|---|---|
| Identificativo di sessione | 16 bit casuali, due stazioni | identificativo di oggetto globale (CRC16 di origine + contatore) e salti nel flag del DATA — **fatto in `tools/frame_mesh.py` (punto 8c), provato sul PC** |
| HELLO / OFFER | nominativo, capacità | + **posizione** (locatore o GPS) e rapporto di segnale (regola fissa) — **fatto nel codec del simulatore (flag 16), provato sul PC** |
| STATUS | risposta al mittente | anche in broadcast, con soppressione dei duplicati |
| Rendezvous | R10 fisso | gradino di ascolto da decidere (punto 4) |
| Flag dei frame | LAST, RETX... | + RELAYED (flag 16, solo per i frame V3; non è il bit `RELAYED` della v2) e salti (bit 5-7) — **fatto** |

## 10. Registro delle decisioni
| Data | Decisione | Fonte |
|---|---|---|
| 23/11/2026 | Il beacon contiene il **solo nominativo**. Poi, fra stazioni che si sono ascoltate, si scambiano nominativo, rapporto e posizione. | autore |
| 23/11/2026 | **Nominativo, rapporto di segnale e posizione (locatore o GPS)** sono elementi fissi di ogni collegamento. Nessuna privacy. | autore, [regole-radioamatoriali.md](regole-radioamatoriali.md) |
| 23/11/2026 | Il primo contatto può essere il solo nominativo. | autore |
| 23/11/2026 | Più ripetitori contemporanei, ricezione da più stazioni con identificazione dei pacchetti mancanti. | autore |
| 23/11/2026 | I ripetitori a fontana devono comunicarsi **un protocollo comune**; **meno stazioni ma più veloci**: una stazione in scarsissima portata, che imporrebbe un gradino lento, è **esclusa**; il pacchetto contiene l'informazione per decidere. (Punto 8b.) | autore |
| 23/11/2026 | **Densità attesa: circa 5 stazioni per zona.** | autore |
| 23/11/2026 | **Il gruppo di ripetitori è coordinato dal mittente** (il destinatario può mettere il veto). | autore |
| 23/11/2026 | Regola "pochi e veloci" di partenza: **almeno 2 membri, tolleranza di 1 gradino** (da tarare sul simulatore). | autore |
| 23/11/2026 | Primo passo del piano: **simulatore mesh sul PC**. | autore |
| 23/11/2026 | **L'infrastruttura v2 esistente non si modifica.** Il V3 è retrocompatibile **solo** per voce, messaggio vocale e testo del protocollo v2; tutto il resto (immagini, beacon, mesh, voto) è aggiunto con frame V3. Il voto è fra nodi V3; un ripetitore v2 non vota. Vedi [compatibilita-v2.md](compatibilita-v2.md). | autore |
| 23/11/2026 | **Internet non è un mezzo affidabile** in un progetto radioamatoriale: è solo un aiuto per la sperimentazione. Nessun annuncio o coordinamento fra i nodi passa da Internet: va via radio (stessa ragione per cui l'orologio è NTP **o** GPS). Il voto fra due nodi in isofrequenza avviene via radio sul canale di servizio (frame VOTO); ritardo massimo di partenza 200 ms (compensato dal loop del microfono della v2). | autore |
| 23/11/2026 | La banda di riferimento resta **430-440 MHz** (gamma del servizio di radioamatore; la divisione in fette fra i servizi non interessa allo studio, e cambia nei paesi vicini). Non è larga e non è libera da altri servizi: si lavora il più possibile in **isofrequenza**. Nella voce, due nodi che sentono insieme la mobile non devono trasmettere tutti e due; chi instrada per primo si decide con un'elezione per qualità. Il voting vero non è obbligatorio. (Vedi [voting-isofrequenza.md](voting-isofrequenza.md).) | autore |
| 23/11/2026 | I **terminali nascosti** vanno gestiti con turni dall'orologio e veto del destinatario, non con il solo ascolto: simulato nei beacon e nel gruppo di ripetitori. Spiegazione in [terminali-nascosti.md](terminali-nascosti.md). | autore, simulatore |
| 23/11/2026 | Va studiata una **tecnologia di voting** per la modalità VOCE (probabilmente VoLoRa v2): due nodi a copertura **parzialmente** sovrapposta; una sovrapposizione ampia e stabile sulla stessa frequenza non è possibile (lo gestiscono i radioamatori). Logica proposta: [voting-isofrequenza.md](voting-isofrequenza.md). (Punto 10b.) | autore |
| 22/11/2026 | La precisione dell'orologio richiesta è bassa: NTP o GPS bastano (anche per gli slot). | autore, [applicazione.md](applicazione.md) |

## 10b. Voting nella modalità VOCE (da studiare)
Requisito dell'autore (23/11/2026): quando le stazioni usano la modalità **VOCE** (da individuare, probabilmente quella del **VoLoRa v2**), il protocollo V3 dovrà prevedere una **tecnologia di voting**.

- **Perché.** La larghezza di banda di LoRa è grande: è più corretto **non occupare più frequenze per lo stesso servizio**. Più nodi dello stesso servizio possono avere una **copertura parzialmente sovrapposta**, e la periferica deve poter **scegliere** quale usare.
- **Cosa deve poter fare la periferica radio in modalità normale:** collegarsi al nodo migliore fra **due nodi a copertura parzialmente sovrapposta** e cambiare quando le condizioni cambiano, con isteresi per non rimbalzare. **Con la regola di compatibilità v2** ([compatibilita-v2.md](compatibilita-v2.md)) la periferica v2 non cambia: la scelta è **lato nodo** (elezione per qualità, memoria del vincitore, voto via radio); la periferica sceglie davvero solo se i nodi hanno frequenze diverse.
- **Vincolo noto (regola dei radioamatori):** **due nodi con copertura radio ampiamente e stabilmente sovrapposta sulla stessa frequenza non sono possibili**: si disturberebbero. Una sovrapposizione **limitata** (una zona dove la mobile passa) invece è il caso voluto: vedi l'aggiornamento qui sotto. La gestione è affidata ai radioamatori che installano i nodi, come si fa con i ripetitori. Il protocollo non deve cercare di risolvere la sovrapposizione sulla stessa frequenza, ma deve rendere possibile la scelta quando le frequenze (o i turni) sono diversi.
- **Ancora da studiare:** la frequenza del canale di servizio fra i nodi, quante ripetizioni del VOTO, il cambio **durante** un turno di parola (di base no), il nominativo perso se manca il pacchetto START della v2, e il comportamento con un nodo che si ascolta male. La metrica (margine in dB), l'isteresi (3 dB) e il ritardo (200 ms) sono nella proposta.
- **Aggiornamento del 23/11/2026 (secondo requisito dell'autore).** La banda di riferimento è **430-440 MHz** (la gamma del servizio di radioamatore; la divisione in fette fra i servizi non interessa allo studio). È condivisa con altri servizi e non larga: i canali larghi non si possono moltiplicare, quindi si lavora il più possibile in **isofrequenza**. Quando la stazione mobile è quieta e comincia a trasmettere, può essere ricevuta da **due nodi insieme**: **non devono trasmettere tutti e due** (doppio accesso), la stazione deve poter sapere a quale nodo si collega e i nodi devono sapere **chi dei due instrada per primo**. Il voting vero non è obbligatorio; basta questo. Logica proposta (elezione per qualità con ritardo, annuncio fra nodi, memoria del vincitore con isteresi), simulatore e risultati: [voting-isofrequenza.md](voting-isofrequenza.md).
- **Stato:** logica proposta e simulata sul PC (due nodi, una mobile). Non provata su schede.

## 11. Da decidere
1. ~~**Quante stazioni** per zona~~ **Deciso: circa 5.** Con 5 stazioni il beacon a R14 collide poco: nel [simulatore mesh](simulatore-mesh.md) il beacon senza coordinamento arriva nell'80 % dei casi e con slot adattivo nel 100 %.
2. **Gradino di ascolto** (fisso R10 o R12, oppure adattivo con R14 dove i vicini sono pochi), dopo le misure dei gradini stretti fra schede vere.
3. **Anti collisione:** ~~CAD più ritardo casuale~~ Il solo ascolto non basta (terminali nascosti, [terminali-nascosti.md](terminali-nascosti.md)): **slot dall'orologio**, con ascolto come aiuto. Da confermare con le prove.
4. **Intervallo del beacon** e se adattivo.
5. **Ripetizione:** scelta geografica o per rapporto di segnale; numero massimo di salti.
6. **Codici a fontana** oppure ritrasmissione selettiva dei pacchetti mancanti. Il codice a fontana è in `tools/fontana.py` (circa 1,6 simboli in più per generazione di 128 pezzi): la scelta resta aperta fino alle prove su schede.
7. **Ruolo del firmware:** il nodo mesh fa beacon, polling, ripetizione e invio insieme. Va riconciliato con il principio "ogni firmware fa una cosa sola" o definito come ruolo a sé.
8. **Convivenza con la voce v2** sullo stesso canale: **canale proprio per il V3** (e CAD), vedi [compatibilita-v2.md](compatibilita-v2.md); la coesistenza con le stazioni v2 va misurata sul campo.

## 12. Piano
1. **Misura** in laboratorio dei gradini lenti (R11-R14) fra le due T3: fin dove si sentono senza correzione di frequenza. *Strumenti pronti nell'app (F10, serie programmata), guida in [prova-gradini-lenti.md](prova-gradini-lenti.md); **misure ancora da fare**.*
2. **Simulatore mesh** (sul PC): *fatto* — beacon con terminali nascosti, gruppo di ripetitori, fontana vera, voto fra due nodi ([simulatore-mesh.md](simulatore-mesh.md), [voting-isofrequenza.md](voting-isofrequenza.md)). Restano le risposte OFFERTA con terminali nascosti e l'errore dell'orologio nei turni.
3. **Frame**: *fatto sul PC* (punto 8c, `tools/frame_mesh.py`): posizione, rapporto, identificativo globale, salti, BEACON, POLL, POLL-REPLY, RICHIESTA, OFFERTA, GRUPPO, CONFERMA/VETO, VOTO. Non provati su schede.
4. **Firmware di prova** del beacon e del polling su due-tre schede.
