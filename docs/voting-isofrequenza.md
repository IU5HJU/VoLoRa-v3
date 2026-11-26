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

**Il voto via radio** sul canale di servizio **433,850 MHz, 125 kHz** ([band-plan.md](band-plan.md)). Modi ammessi: FSK R2 e LoRa a 125 kHz (SF7-SF12). VOTO da 12 byte, un voto su 33 perso, antenne in alto con 10 dB di perdita extra, un solo tentativo; stesso modello. *(Risultati rifatti il 26/11/2026: la prima stima usava i gradini R3-R7, più larghi di 125 kHz, che sul canale scelto non stanno.)*

| Distanza fra i nodi | Modo del voto | Durata del voto (2 slot) | Entra in 200 ms | Doppio accesso | Nodo migliore |
|---|---|---|---|---|---|
| 3 km | FSK R2 | 27 ms | sì | 2,7 % | 97 % |
| 5 km | FSK R2 | 27 ms | sì | 3,1 % | 97 % |
| 10 km | LoRa 125/SF7 | 102 ms | sì | 3,0 % | 97 % |
| 20 km | LoRa 125/SF7 | 102 ms | sì | 2,4 % | 95 % |
| 30 km | LoRa 125/SF7 | 102 ms | sì | 3,9 % | 95 % |
| 50 km | LoRa 125/SF7 (o SF8) | 185 ms | sì | 1,2 % | 95 % |

Il doppio accesso residuo (circa 1-4 %) è soprattutto la **perdita del VOTO del vincitore** (3 % nel modello): si abbassa **ripetendo il voto**, a spese della durata. **È il metodo scelto:** vota il margine, non il caso, e non dipende da Internet. Il voto lungo il percorso a 50 km quasi riempie i 200 ms: oltre, serve un gradino più veloce (antenne migliori) o la zona di sovrapposizione non è ammessa.

**Ritardo massimo W:** **200 ms vanno bene** (decisione dell'autore, 23/11/2026): nella v2 il ritardo è compensato da un **loop continuo del microfono prima della trasmissione**, quindi non si sente.

Per il solo ritardo (senza voto) c'è un **compromesso** fra ritardo e doppio accesso. Il ritardo si paga una sola volta, alla **prima trasmissione a riposo**; durante la frase e nelle trasmissioni successive vale la memoria del vincitore (punto 3.3). **Deciso:** il ritardo iniziale di 200 ms è accettabile.

**Percorso:** una stazione che si muove da un nodo all'altro, scegliendo ogni volta il nodo migliore, **cambia nodo in media 9 volte**; con l'**isteresi di 3 dB 3,7 volte**, con 6 dB 1,3. L'isteresi serve (la scelta non deve rimbalzare con il fading), ma non va esagerata: oltre una certa soglia si resta troppo a lungo con il nodo peggiore.

## 5. Cose da decidere o studiare
1. ~~Ritardo massimo~~ **Deciso il 23/11/2026: 200 ms** (compensati dal loop del microfono della v2). Resta la scala in dB (20 dB nel modello).
2. ~~Canale per l'annuncio~~ **Deciso il 23/11/2026: via radio**, mai da Internet. **Deciso il 25/11/2026: frequenza dedicata nella banda 430-440 MHz**, una per zona, concordata fra chi installa i nodi, con gradino veloce (R3-R7) e antenne in alto. **Deciso il 26/11/2026: 433,850 MHz** (canale 1 della tabella, 125 kHz, [band-plan.md](band-plan.md)). Il modo veloce deve stare nei 125 kHz: FSK R2 o LoRa 125 kHz (simulatore ripetuto con questi modi il 26/11/2026: il voto entra nei 200 ms fino a 50 km). **Radio di servizio deciso il 26/11/2026: la scheda di trasmissione del nodo** (a riposo fino alla ritrasmissione); da verificare sul ripetitore a due schede.
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
