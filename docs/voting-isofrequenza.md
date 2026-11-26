# Voting e isofrequenza: chi ritrasmette quando due nodi sentono la stessa stazione

> **Stato (23/11/2026): requisito dell'autore, logica proposta e provata solo con un simulatore sul PC. Nessuna parte è provata su schede.** I numeri sono di un modello (collegamenti stimati, ombreggiamento casuale), non misure. Questa è una **bozza da discutere**, non una decisione.

## 1. Perché serve
La banda dei 430 MHz è **stretta e condivisa con altri servizi**: i canali larghi (fino a 250 kHz per i gradini più ampi) non si possono moltiplicare senza scontrarsi con quelli esistenti. Per questo bisogna **lavorare il più possibile in isofrequenza**: più nodi sulla **stessa frequenza**, con coperture che si sovrappongono solo in parte.

**Banda di riferimento dello studio (precisata il 23/11/2026):** **430-440 MHz**, la gamma attribuita al servizio di radioamatore. Come dentro la banda sono divise le fette fra i vari servizi **non interessa allo studio**: interessa restare dentro le frequenze del servizio di radioamatore. Lo studio è in italiano ma deve poter servire anche nei paesi vicini, dove la norma è un po' diversa (per questo non si fissa un band plan nazionale). Il limite della propria licenza resta di chi trasmette.

Il caso da risolvere è la **modalità voce** (probabilmente il protocollo VoLoRa v2) con una stazione mobile che si sposta:

- Se un nodo sta già trasmettendo, l'altro non può essere sentito in ricezione e tace: **qui non c'è problema**.
- Se **tutto è quieto** e la mobile comincia a trasmettere, **due nodi la possono ricevere nello stesso istante**, e **tutti e due** potrebbero ritrasmetterla: **doppio accesso**, sulla stessa frequenza, verso la rete e verso gli altri ripetitori. **Non deve accadere.**
- La stazione deve poter sapere **a quale nodo si sta collegando**, e i nodi devono sapere **chi dei due instrada per primo**.

Quando i nodi si **sentono** fra loro (stessa frequenza e coperture sovrapposte nella stessa zona) vale la regola dei radioamatori: due nodi così non si installano. Qui interessa il caso di nodi **distanti**, con una **zona di sovrapposizione limitata**, dove la mobile passa.

## 2. Cosa c'è già nella v2 (letto in `third_party/VoLoRa-v2/docs/protocollo.md`)
- **CAD prima del PTT:** se il canale è occupato il PTT è rifiutato.
- **Sessione casuale per ogni PTT** (2 byte) e nominativo nel pacchetto: due copie della stessa trasmissione si riconoscono.
- **Bit `RELAYED`** (bit 7 del byte dei flag, byte 4): un ripetitore **non ripete mai** un pacchetto con quel bit. Evita i cicli.
- **Prima trasmissione sentita:** il ricevitore adotta la prima sessione che sente e ignora le altre finché dura (poi 3 s di silenzio o `END`).
- **Annuncio di ripetitore occupato** (modo 6), per i messaggi lunghi.

**Non ho trovato nella v2 una regola per scegliere fra due nodi che sentono la stessa stazione.** Quello che c'è serve a riconoscere le copie e a non fare cicli; l'elezione è nuova.

**Regola di compatibilità (23/11/2026):** l'infrastruttura v2 **non si modifica** ([compatibilita-v2.md](compatibilita-v2.md)). Il voto è quindi fra **nodi V3**; la mobile v2 non cambia di un byte; un ripetitore v2 non può votare.

## 3. Logica proposta

### 3.1 Elezione per qualità (lato nodo, non serve nulla alla mobile)
Ogni nodo che **decodifica la prima trasmissione** di una stazione, a riposo:
1. misura la **qualità** del segnale (margine sopra la sensibilità del gradino, in dB);
2. calcola un **ritardo di partenza** che **diminuisce con la qualità**: il segnale migliore parte per primo (in modo che tra 0 e W, di base 200 ms, ci stia l'intervallo di circa 20 dB);
3. durante l'attesa **ascolta**: se vede partire un altro nodo, o se riceve il suo **annuncio** (punto 3.2), **annulla** la propria ritrasmissione;
4. se nessuno lo ha preceduto, parte; il suo pacchetto porta `RELAYED` e gli altri nodi non lo ripetono.

La decisione vale per **tutta la sessione** (tutto il PTT): non si cambia nodo a metà frase.

### 3.2 Annuncio fra nodi (quando non si sentono in RF)
Due nodi distanti **non si sentono sulla frequenza della mobile**: sono **terminali nascosti** ([terminali-nascosti.md](terminali-nascosti.md)) e l'ascolto da solo non basta. L'annuncio **non può passare da Internet**: in un progetto radioamatoriale Internet è solo un aiuto per la sperimentazione, non un mezzo di comunicazione affidabile (stessa ragione per cui l'orologio si prende da NTP se c'è Internet e dal GPS se non c'è). **L'annuncio va via radio.**

**Il voto via radio** (decisione dell'autore, 23/11/2026):
1. Il nodo parla su un **canale di servizio fra i nodi**, **non** sulla frequenza della mobile: mentre la mobile trasmette, un nodo che trasmettesse sulla stessa frequenza la coprirebbe. Il canale di servizio è una frequenza in più dentro 430-440 MHz, **una per tutta la zona**, con antenne in alto o direzionali.
2. Alla fine del primo pacchetto della mobile (istante comune a tutti i nodi che l'hanno sentita) ogni nodo manda un **VOTO** da 12 byte nel **proprio slot** (ordine per identificativo), con **nominativo della mobile, sessione, margine in dB e identificativo del nodo**.
3. **Vince il margine più alto; a parità l'identificativo più basso** (spareggio fisso, senza caso). Chi perde non ritrasmette; chi vince ritrasmette con `RELAYED`.
4. **Se un nodo non sente il voto dell'altro, ritrasmette comunque**: meglio un doppio accesso occasionale che perdere l'audio. Il voto si può **ripetere** per ridurre il caso.
5. La scheda che ritrasmette (quella di trasmissione del nodo, a riposo fino a quel momento) può fare da radio di servizio senza una terza scheda: *ipotesi da verificare sul ripetitore v2 a due schede*.

**Vincolo di progetto:** due nodi in isofrequenza con una zona in comune devono **sentirsi sul canale di servizio** a un gradino abbastanza veloce da far entrare il voto nei 200 ms (punto 4). Se non si sentono, la zona di sovrapposizione **non è ammessa**: lo sa chi installa i nodi, che è la regola dei radioamatori.

### 3.3 Il nodo "ricorda" la stazione (la seconda trasmissione)
Per rispondere a "alla seconda trasmissione, quale dei due usare?": ogni nodo tiene per qualche minuto, **per nominativo**, **chi ha vinto l'ultima volta** e con quale qualità. Alla trasmissione successiva il vincitore precedente **resta** il vincitore, finché l'altro nodo non lo supera di una **isteresi** (di base 3 dB). Il nominativo è già nel pacchetto v2 (nel pacchetto START): **alla mobile non serve nessun campo nuovo.**

### 3.4 Che cosa sa la mobile
La mobile **vede quale nodo risponde**: la ritrasmissione porta `RELAYED` e il nominativo del nodo (il beacon o l'identificazione periodica del nodo, come nella v2). Se un giorno i nodi hanno **frequenze diverse**, la mobile può invece **scegliere** dal beacon (qualità del segnale, carico) con la stessa isteresi: è il vero voting lato periferica, con i beacon in **slot dall'orologio** così che non si sovrappongano.

### 3.5 Il resto della rete
Anche se per errore partono tutti e due, la rete riconosce la copia: **stessa sessione e stesso nominativo** (come già fa la v2), e il secondo non viene instradato. Il doppio accesso che resta è quello **in aria** sulla frequenza condivisa: è quello da evitare.

## 4. Cosa mostra il simulatore
Programma: [`tools/sim_voting.py`](../tools/sim_voting.py), prove in [`tests/sim/test_voting.py`](../tests/sim/test_voting.py). Due nodi a 20 km, gradino della voce R6 (ipotesi), la mobile in un punto casuale; si contano solo i casi in cui **tutti e due** la decodificano (circa 1200 su 3000 scenari nella prova da riga di comando).

| Politica | Annuncio | Nodi si sentono in RF | Doppio accesso | Nodo migliore (se uno solo) | Ritardo medio |
|---|---|---|---|---|---|
| nessuna regola | – | – | **100 %** | – | – |
| ritardo casuale | RF | sì | 8,6 % | 47 % (sorteggio) | 63 ms |
| ritardo casuale | RF | no | **100 %** | – | – |
| **per qualità** | RF | sì | 9,3 % | **98 %** | 73 ms |
| per qualità | RF | **no** | **100 %** | – | – |
| per qualità | rete (50 ms) *(solo per esperimenti)* | no | 39 % | 100 % | 54 ms |

Lettura:
- **Senza regola il doppio accesso è sicuro.** Con l'ascolto basta pochissimo se i nodi si sentono.
- **Il ritardo per qualità non evita il doppio accesso meglio del caso, ma sceglie il nodo giusto** (98 % contro 47 %): questo è il vantaggio.
- **Se i nodi non si sentono e non hanno un altro canale, il doppio accesso è inevitabile.** Serve un **percorso radio fra i nodi** (il canale di servizio): Internet non vale, perché non è affidabile.
- Quello che resta con il solo ritardo (circa 9 % in RF, 39 % con un annuncio a 50 ms con W = 200 ms) sono i casi in cui la qualità dei due è **quasi uguale**: i due ritardi cadono nella stessa finestra. Si riduce **allungando W**:

| W (ritardo massimo) | Doppio accesso via rete | Doppio accesso in RF | Ritardo medio via rete |
|---|---|---|---|
| 100 ms | 70 % | 18 % | 14 ms |
| 200 ms | 39 % | 9 % | 54 ms |
| 400 ms | 22 % | 5 % | 131 ms |
| 800 ms | 11 % | 2 % | 289 ms |

**Il voto via radio ha due canali di servizio possibili** (deciso il 26/11/2026; il nodo ne sceglie uno in base all'hardware):

| | **A. 144,900 MHz (2 m)** | **B. 433,850 MHz (70 cm)** |
|---|---|---|
| Chip | solo **SX1278** (137-175 MHz) | **qualunque** (SX1278 e SX1262) |
| Antenne | **una sola** antenna collineare bibanda + duplexer 2 m / 70 cm | **due antenne separate** (la radio del voto e quella principale sono nella stessa banda) |
| Banda occupata | 9,6 kHz (FSK stretta, segmento MGM da 12 kHz) | 100-125 kHz (FSK R2 o LoRa 125 kHz) |
| Distanza utile del voto | affidabile fino a circa 30 km | affidabile oltre 50 km |
| Disturbo alla radio principale | basso: bande diverse, duplexer | **alto**: 150 kHz di distanza dal canale 0 (433,700 MHz) |
| Terza armonica | 434,700 MHz (filtro passa-basso) | — |

**Regola:** due nodi votano **solo sullo stesso canale**. Ogni nodo annuncia il proprio canale e le capacità nel frame **NODO** (`NODE_INFO`, 14 byte, sottotipo 8 del frame 14); la **zona** ha un canale preferito (di partenza il 2 m) e basta che **un solo nodo con SX1262** ci sia perché la zona debba usare i 70 cm. Senza canale in comune i due nodi non votano e valgono le regole della sovrapposizione non ammessa. Funzioni in [`tools/canali.py`](../tools/canali.py): `service_options(chip)`, `common_service(...)`.

**Risultati del simulatore** (VOTO da 12 byte, un voto su 33 perso, antenne in alto con 10 dB di perdita extra, un solo tentativo):

| Distanza | A. 2 m: nodi che si sentono | A. durata / doppio accesso | B. 70 cm: nodi che si sentono | B. modo, durata / doppio accesso |
|---|---|---|---|---|
| 5 km | 100 % | 90 ms / 3,1 % | 100 % | FSK R2, 27 ms / 3,1 % |
| 10 km | 100 % | 90 ms / 3,0 % | 100 % | LoRa 125/SF7, 102 ms / 3,0 % |
| 20 km | 100 % | 90 ms / 4,0 % | 100 % | 102 ms / 2,4 % |
| 30 km | 97 % | 90 ms / 5,7 % | 100 % | 102 ms / 3,9 % |
| 50 km | 81 % | 90 ms / 19,5 % | 100 % | 185 ms / 1,2 % |
| 70 km | 46 % | 125 ms / 55 % | 98 % | 309 ms (**fuori dai 200 ms**) / 5,9 % |

In 2 m la perdita è minore di 9,5 dB ma il modo è stretto (9,6 kHz) e meno sensibile, quindi il voto arriva meno lontano; in 70 cm si può usare un LoRa da 125 kHz, più sensibile. Il canale A è la scelta comoda (una antenna); il B è la scelta per nodi più lontani e per le T-Beam con SX1262.

Dove i nodi non si sentono sul canale di servizio il voto non è possibile (doppio accesso sicuro): la **zona di sovrapposizione non è ammessa**. Con questo modello il voto è affidabile **fino a circa 30 km**; oltre servono antenne con più guadagno o un modo più sensibile (più lento: FSK 2,4k, 70 ms per frame).

**Come è fatto un nodo (hardware).** *Variante A (2 m):* due schede (RX a 433 MHz e TX/servizio), **un duplexer 2 m / 70 cm** e **una collineare bibanda**. *Variante B (70 cm):* due schede e **due antenne** ben separate; la radio del voto trasmette a 150 kHz dalla radio principale: **durante il voto (circa 100 ms) il ricevitore principale è in forte disturbo** (blocking), si può perdere un pacchetto di voce (la v2 ha la correzione d'errore) e va misurato. Per la variante A, cose da controllare:
- **Terza armonica:** 3 × 144,900 = **434,700 MHz**, che cade in 70 cm, a circa 0,7 MHz dai nostri canali: serve un **filtro passa-basso** sulla radio a 2 m (o la sezione VHF del duplexer, se ha una buona reiezione a 434 MHz). La T3 a 433 MHz ha il suo filtro tarato su 433, non su 145.
- **Quale chip:** il voto a 144,900 MHz lo può fare solo un **SX1278** (T3 e T-Beam con SX1278: campo 137-175 MHz). **L'SX1262 parte da 150 MHz**: un T-Beam con SX1262 **non** può fare la radio di servizio a 2 m (può fare la radio principale a 433 MHz). Da confermare sul datasheet (il limite viene da RadioLib).
- **Le schede a 433 MHz a 144 MHz:** l'adattamento e il filtro della T3 sono per i 433 MHz; il rendimento a 144,9 MHz va **misurato** (stessa cosa del punto aperto 7 per i 430 e 440 MHz).
- **Isolamento del duplexer** fra le due porte: la radio a 2 m trasmette mentre quella a 70 cm ascolta la mobile; va misurato quanto disturba il ricevitore a 433 MHz.

Il doppio accesso residuo (circa 1-4 %) è soprattutto la **perdita del VOTO del vincitore** (3 % nel modello): si abbassa **ripetendo il voto**, a spese della durata. **È il metodo scelto:** vota il margine, non il caso, e non dipende da Internet. Il voto lungo il percorso a 50 km quasi riempie i 200 ms: oltre, serve un gradino più veloce (antenne migliori) o la zona di sovrapposizione non è ammessa.

**Ritardo massimo W:** **200 ms vanno bene** (decisione dell'autore, 23/11/2026): nella v2 il ritardo è compensato da un **loop continuo del microfono prima della trasmissione**, quindi non si sente.

Per il solo ritardo (senza voto) c'è un **compromesso** fra ritardo e doppio accesso. Il ritardo si paga una sola volta, alla **prima trasmissione a riposo**; durante la frase e nelle trasmissioni successive vale la memoria del vincitore (punto 3.3). **Deciso:** il ritardo iniziale di 200 ms è accettabile.

**Percorso:** una stazione che si muove da un nodo all'altro, scegliendo ogni volta il nodo migliore, **cambia nodo in media 9 volte**; con l'**isteresi di 3 dB 3,7 volte**, con 6 dB 1,3. L'isteresi serve (la scelta non deve rimbalzare con il fading), ma non va esagerata: oltre una certa soglia si resta troppo a lungo con il nodo peggiore.

## 4b. Un nodo senza canale di voto (scheda singola)
**Caso:** un nodo con una sola radio, che non può avere il canale di servizio (né a 2 m, né a 70 cm). Il suo frame NODO dice `caps = 0`. Con la regola attuale "si vota solo sullo stesso canale" **non vota**: è un nodo **muto**. Cosa succede in una zona di sovrapposizione con un nodo A che vota?

**Comportamento senza regole nuove (strategia "come votante").** Il muto sceglie il ritardo per qualità come gli altri e ascolta in RF, ma non può scambiare VOTI: l'elezione è solo RF. Se i due nodi si sentono sulla frequenza principale, l'ascolto evita quasi sempre il doppio accesso, ma non sempre (le due partenze cadono nella stessa finestra): **circa 9-15 % di doppi accessi**; se non si sentono, **doppio accesso sicuro**.

**Proposta: il muto aspetta e ascolta.** Chi non può votare ritrasmette **solo dopo la finestra del voto** (200 ms) più 100 ms, cioè dopo **300 ms**, e **solo se in RF non ha sentito partire un altro nodo** (nessun pacchetto con `RELAYED` dell'altro). I nodi che votano restano sulla loro regola: chi vince parte entro 200 ms. Il muto è così **sempre secondo**:
- **Doppio accesso 0-1 % se i due nodi si sentono** sulla frequenza principale (fino a 30 km nel modello); **9 % a 50 km**, dove non si sentono più.
- **Se la mobile è coperta solo dal muto** (zona senza sovrapposizione) ritrasmette con **circa 170-270 ms di ritardo in più**: il ritardo della v2 è compensato dal loop del microfono (200 ms deciso), quindi è un costo accettabile ma da misurare.
- **Il muto non vince mai**, anche quando ha il segnale migliore: la qualità del collegamento con la mobile ne soffre in circa metà dei casi di sovrapposizione.

**Alternativa: voto in time-sharing sul canale a 70 cm (433,850 MHz) con la sola radio.** Il nodo a scheda singola vota come gli altri (doppio accesso circa 3 %), ma **mentre vota (circa 100 ms) non ascolta la mobile**: può perdere un pacchetto di voce (la v2 ha la correzione d'errore), ed è utile solo se anche gli altri nodi della zona votano a 70 cm.

| Distanza fra i nodi | Solo RF (come votante) | Il muto aspetta e ascolta | Time-sharing a 70 cm | Zona con la sola copertura del muto | Ritardo in più del muto |
|---|---|---|---|---|---|
| 5 km | 15 % | 0 % | 3,1 % | 3 % | 267 ms |
| 10 km | 9 % | 0 % | 2,8 % | 12 % | 241 ms |
| 20 km | 9 % | 0 % | 2,4 % | 30 % | 204 ms |
| 30 km | 12 % | 1 % | 3,2 % | 37 % | 187 ms |
| 50 km | 21 % | 9 % | 6,1 % | 43 % | 171 ms |

**Cosa resta vero:** se i due nodi non si sentono nemmeno sulla frequenza principale, il muto non ha modo di sapere che l'altro ha già ritrasmesso (Internet non è un mezzo affidabile): **doppio accesso sicuro**; la zona di sovrapposizione fra un nodo muto e uno che vota va evitata, o i due nodi devono potersi sentire in RF.

## 5. Cose da decidere o studiare
1. ~~Ritardo massimo~~ **Deciso il 23/11/2026: 200 ms** (compensati dal loop del microfono della v2). Resta la scala in dB (20 dB nel modello).
2. ~~Canale per l'annuncio~~ **Deciso il 23/11/2026: via radio**, mai da Internet. **Deciso il 25/11/2026: frequenza dedicata nella banda 430-440 MHz**, una per zona, concordata fra chi installa i nodi, con gradino veloce (R3-R7) e antenne in alto. **Deciso il 26/11/2026: 144,900 MHz in banda 2 m, fisso** (corregge 433,850 MHz: un nodo con due radio richiedeva due antenne; poi corregge 144,850 MHz, canale dei gateway voce digitale; vedi sopra). **Radio di servizio deciso il 26/11/2026: la scheda di trasmissione del nodo** (a riposo fino alla ritrasmissione); da verificare sul ripetitore a due schede.
3. ~~Quante **ripetizioni** del VOTO~~ **Deciso il 26/11/2026: un solo tentativo** (doppio accesso residuo circa 3 %, voto di 27-185 ms entro 50 km). Due tentativi darebbero circa 0,1 % ma il voto durerebbe 204 ms a 30 km. Resta da fissare il **tempo di guardia** fra gli slot (10 ms nel modello).
4. Il formato del VOTO è in [`tools/frame_mesh.py`](../tools/frame_mesh.py) (`enc_vote`, sottotipo 7 del frame MESH, 12 byte); da integrare in [mesh-v3.md](mesh-v3.md), punto 8c.
5. Quanto tempo il nodo ricorda il vincitore e la soglia dell'isteresi (di base 3 dB).
6. Il **cambio di nodo durante un turno di parola** (di base: no).
7. La **prova su schede**: due nodi in laboratorio, una scheda mobile.

## 6. Limiti del modello
- Collegamenti stimati e ombreggiamento casuale: i valori **assoluti** dipendono da queste ipotesi, **quelli relativi** (qualità contro caso, con o senza voto) no.
- Gradino della voce, finestra di rilevamento (10 ms), errore di misura dell'SNR (1 dB) la perdita di un VOTO (3 %), la perdita extra fra i nodi (10 dB) e l'annuncio a 50 ms (solo per esperimenti) sono **ipotesi**.
- Due soli nodi e una sola mobile; niente traffico concorrente; l'orologio dei nodi non serve a questa logica.
- Non è provato su schede.

## 7. Per fare i conti da solo
```bash
python3 tools/sim_voting.py
```
```bash
python3 tests/sim/test_voting.py
```
