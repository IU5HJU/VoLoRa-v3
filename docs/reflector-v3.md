# Il reflector V3

> **Stato (26/11/2026): progetto scritto, con un riferimento in Python provato sul PC e contro il VERO `vlnode` della v2.** Non c'è ancora un reflector di produzione né un gateway V3 sulle schede; l'interoperabilità è provata con il programma `vlnode` della v2 su veri socket UDP, **non con schede**.

**Decisione dell'autore (26/11/2026):** il reflector V3 **sostituirà il reflector v2**. Poiché l'infrastruttura v2 non si modifica ([compatibilita-v2.md](compatibilita-v2.md)), il nuovo reflector è un **sostituto compatibile**: i nodi v2 già installati continuano a collegarsi **senza cambiare nulla** (stesso indirizzo, stessa porta, stesso id, stessa chiave); i nodi V3 ottengono in più il trasporto del V3.

## 1. Cosa ho letto e cosa ho provato
- **Letto** nel codice v2: `lib/voicecore/node_link.*` (il collegamento VoLoRa-IP), `reflector_core.*` (regole di inoltro), `docs/reflector.md`, `docs/studio-nodo-internet.md` (documenti del submodule, non modificati).
- **Scritto** in [`tools/nodelink.py`](../tools/nodelink.py) un porting del collegamento e in [`tools/reflector_v3.py`](../tools/reflector_v3.py) il reflector (logica e un piccolo server UDP).
- **Provato** in due modi: (1) `tests/sim/test_reflector_v3.py`: logica con client finti (23 verifiche: collegamento, inoltro, arbitraggio della voce, firma, ripetizione, estensione V3); (2) **`tests/interop/test_reflector_vs_vlnode.py`: due `vlnode` veri della v2** (compilati dal submodule) si collegano al reflector V3 su socket UDP veri, il testo e la voce di uno arrivano all'altro con il flag `RELAYED` e **nessuna firma viene rifiutata**.

## 2. Il collegamento (identico alla v2)
Datagramma UDP: `'V' 'L' | versione (1, = 1) | tipo (1) | canale (1) | id nodo (4) | id di avvio (4) | contatore (4) | lunghezza (1) | contenuto | firma (8)`, firma = **HMAC-SHA256 troncato a 8 byte** con la chiave di 16 byte del client, su tutto ciò che precede. Tipi: 1 HELLO, 2 CHALLENGE (sfida), 3 RESPONSE, 4 PACKET (un pacchetto radio così com'è), 5 KEEPALIVE. Il collegamento è **attivo solo dopo l'autenticazione a vicenda** (sfida dopo un riavvio); HELLO ogni 2 s finché non è attivo, KEEPALIVE ogni 20 s, caduto dopo 60 s. **I client scrivono per primi**: nessuna porta aperta sul loro router. **Non cambia un bit.**

## 3. Comportamento per la v2 (identico)
- Un solo **modo voce** per reflector (1 Range o 4 Standard), il **testo** (modo 7) passa sempre, gli altri modi si scartano.
- **Chi parla per primo tiene il canale** fino al pacchetto di fine (`END`) o a 3 s senza pacchetti; la voce degli altri nel frattempo si scarta (e si conta). La parità passa solo se il canale è libero o è di chi parla.
- **Ogni pacchetto inoltrato ha il flag `RELAYED`**, mai al mittente. Con due gateway che ricevono la stessa mobile (isofrequenza) vale lo stesso arbitraggio: il secondo viene scartato.
- **Un id sconosciuto si ignora senza rispondere** (nessuna amplificazione); firma sbagliata e contatore vecchio si scartano.
- **File dei client**: `id  chiave(32 cifre esadecimali)  nominativo [nome]`, uguale alla v2: **nessuna riga cambia**.

## 4. L'estensione V3
Un client V3 si **dichiara** nei suoi HELLO e KEEPALIVE, dopo i 9 byte di stato della v2 (5 di stato + 4 dell'indirizzo pubblico, a zero se ignoto): `'V' '3'`, **revisione** (1), **capacità** (1: bit 0 vuole i frame V3, bit 1 manda l'annuncio della rubrica). I client v2 e il reflector v2 leggono solo i primi 9 byte, quindi **l'estensione non disturba** (provato con i `vlnode` veri). Il reflector risponde con la stessa estensione **solo ai client che l'hanno dichiarata**.

**Regola d'oro: un client v2 non vede mai un frame V3 e non può inserirne.** Il frame V3 ha il byte 0 `0x3X` (versione 3 nel nibble alto): lo scartano i decodificatori v2, ma il reflector non lo manda comunque.

**Cosa trasporta il V3** (e cosa no). Le **beacon, i POLL e le identificazioni dei nodi restano locali** (radio): su Internet non servono e consumerebbero banda. Su Internet viaggiano gli **oggetti** (immagini, file) fra stazioni che non si sentono in radio:
| Frame (sottotipi del frame 14, [mesh-v3.md](mesh-v3.md)) | Verso | Contenuto |
|---|---|---|
| `REFL_ANNUNCIO` (80) | gateway → reflector | quali stazioni il gateway **sente** nella sua zona radio: fino a 20 voci `(nominativo, età in secondi)`, ogni minuto circa |
| `REFL_INOLTRO` (81) | gateway → reflector → gateway | **busta**: nominativo di destinazione, di origine, ttl e **dentro il frame V3** (OFFER, DATA, STATUS, DONE…) |
| `REFL_ESITO` (82) | reflector → gateway | `consegnato`, `non trovato` o `rifiutato` (ttl esaurito) |

**Instradamento.** Il reflector tiene una **rubrica**: per ogni gateway V3 le stazioni dell'ultimo annuncio, con scadenza di **10 minuti**. Una busta va al gateway che ha sentito la destinazione **più recentemente** (mai al mittente), con il `ttl` ridotto di uno, e il mittente riceve l'esito. Il gateway di destinazione trasmette il frame in radio nella sua zona con le regole V3 (una stazione che non sente più la destinazione risponde con il suo STATUS, e la sessione prosegue).

## 5. Perché è un sostituto, non un'aggiunta
- **Lo stesso programma, lo stesso file, la stessa porta.** Sul server si ferma il vecchio e si avvia il nuovo con lo **stesso file dei client**: i nodi v2 si ricollegano da soli (dopo il riavvio la sfida li fa rientrare). **Ritorno indietro** semplice: si riavvia il vecchio con lo stesso file.
- **Prima in parallelo:** si avvia il nuovo su **un'altra porta** con un file di prova, si collegano un nodo v2 e uno V3, e solo dopo si sostituisce.
- **Il V3 è un di più:** se il reflector V3 non c'è (Internet giù), i gateway V3 ripiegano sulla **rete mesh** ([configurazione-nodo.md](configurazione-nodo.md)).

## 6. Sicurezza
Una chiave **per client** (si può togliere un client senza toccare gli altri); firma su ogni datagramma; contatore anti-ripetizione; sfida dopo un riavvio; **nessuna risposta a chi non è in elenco**. I frame V3 sono accettati **solo** dai client che li hanno dichiarati e **solo** quelli del reflector (annuncio e busta): gli altri frame V3 si scartano. Il contenuto **non è cifrato** (come la radio: la firma impedisce di inserire pacchetti, non di leggerli). La chiave SYSOP dei comandi via radio è un'altra cosa.

## 7. Valutazione del reflector C++ della v2 (26/11/2026)
**Domanda:** estendere il C++ della v2 (stessa installazione, stesse pagine web) o tenere Python?

**Com'è fatto** (letto e compilato in una copia, il submodule non si tocca):
| Parte | File | Righe |
|---|---|---|
| Collegamento VoLoRa-IP | `node_link.h/.cpp` | 143 + 194 |
| Logica del reflector (senza socket né orologio) | `reflector_core.h/.cpp` | 144 + 280 |
| File dei client, password, HTTP | `reflector_config`, `admin_auth`, `http_mini`, `sha256` | circa 600 |
| Server UDP e pagine web | `tools/vlreflector.cpp`, `vlreflector_page.h`, `vlreflector_public.h` | 735 + 212 + 96 |
| Prove | `test_reflector_core` (79 controlli), `test_node_link` (67), `test_reflector_config`, `reflector_smoke.sh` | 480 + 301 + 78 + 138 |

- **Provato qui:** i test del reflector e del collegamento **passano con ASan e UBSan** (79 e 67 controlli, 0 falliti); il reflector si compila **senza avvisi** (`-Wall -Wextra`) con **soli 8 file** di `lib/voicecore` (`admin_auth`, `http_mini`, `packet`, `position`, `reflector_config`, `reflector_core`, `node_link`, `sha256`) più il server: binario da circa 200 kB, nessuna dipendenza dalla parte audio/radio.
- **Struttura buona per estenderla:** la logica (`ReflectorCore`) è separata dai socket (`IReflectorNet`) e il server la usa solo con la sua interfaccia pubblica (client, statistiche, chi parla): **le pagine web non vanno toccate** per far funzionare il V3.

**Dove si tocca** (solo due moduli):
1. **`NodeLink`** (circa 25 righe): il payload di stato di HELLO e KEEPALIVE è un buffer fisso da 9 byte (`uint8_t p[9]`): va reso più lungo per l'estensione e va letto quanto c'è oltre i 9 byte (oggi si ignora). La lettura dei primi 9 byte non cambia: è quello che ho provato con i `vlnode` veri.
2. **`ReflectorCore`** (circa 200 righe): campi in più per client (dichiarazione V3, rubrica delle stazioni sentite con scadenza), un ramo **prima** di `decodePacket` (che scarta ogni pacchetto con versione diversa da 2 e conterebbe i frame V3 come "non validi"), i due frame `REFL_ANNUNCIO` e `REFL_INOLTRO` e l'esito, nuovi contatori. Le destinazioni si confrontano sui **6 byte** del nominativo compatto, senza portare in C++ la tabella dei 6 bit.
3. **Facoltativo:** una colonna "V3" e la rubrica nella pagina di amministrazione (`vlreflector_page.h`).

**Il modo di tenerlo: una patch sopra la v2, non una copia.** Il reflector V3 si costruisce **applicando una patch (circa 300 righe) ai file della v2 del submodule** in una cartella di compilazione: il submodule resta intatto, la modifica è piccola e rivedibile, e **se la v2 cambia la patch non si applica e la CI lo dice**. Si evita la copia che col tempo si scosta dall'originale.

**Confronto**
| | C++ con patch sulla v2 | Python (il riferimento di oggi) |
|---|---|---|
| Pagine web, password, ricarica con SIGHUP, systemd | **già pronte e provate** | da riscrivere (circa 1300 righe) |
| Prove | si riusano le 146 verifiche e lo smoke test | solo le mie 23 e l'interoperabilità |
| Sostituzione del servizio | stesso nome, opzioni, file, servizio systemd | comando diverso |
| Lavoro | patch di circa 300 righe e prove (circa 150 righe) | nessuno ora, ma molto per arrivare alle stesse funzioni |
| Rischio | patch da tenere allineata alla v2 (la v2 è ferma al tag `v0.1.0-rc.1`) | meno collaudato |
| Velocità, memoria | più che sufficienti per UDP a pochi pacchetti al secondo | idem |

**Raccomandazione:** **C++ con patch sulla v2**, e tenere il Python come **riferimento di prova** (oracolo) per confrontare il comportamento nei test. È la strada con il minor rischio di rompere la compatibilità, perché riusa tutto ciò che è già provato e tocca solo i due moduli necessari.

## 8. Non fatto, e da decidere
- **Server di produzione:** deciso il C++ con patch sulla v2 (punto 7); la patch è scritta e provata sul PC (punto 9). Il Python resta riferimento di prova. Manca una prova su un server vero con nodi veri.
- **Pagine di amministrazione e pubblica** (chi è collegato, chi parla): non portate; vanno uguali alla v2, con in più una colonna "V3" e la rubrica. Quella pubblica non mostra indirizzi, chiavi, id.
- ~~**Limiti di velocità** per client e di dimensione dei trasferimenti V3~~ **Deciso e scritto il 26/11/2026** (punto 10), valori di partenza da fissare con le prove.
- **Più modi voce insieme** (oggi un reflector inoltra un solo modo voce: limite della v2 tenuto per compatibilità).
- ~~**Stanze**~~ **Deciso il 26/11/2026: non ora.** Si resta con il canale 0, come la v2.
- **Collegamento con reflector esterni** (SvxLink, YSF, DMR): resta quello che dice lo studio della v2.
- **Prova su schede:** nessun gateway V3 esiste ancora; il lato "client V3" è solo nelle prove.

## 9. La patch C++ (26/11/2026)
- **Dove:** `reflector/v3.patch` (diff unificato, `patch -p1`) su sei file della v2: `node_link.h/.cpp`, `reflector_core.h/.cpp`, `tools/vlreflector.cpp` e `tools/vlreflector_page.h`. Il submodule non si tocca: `reflector/build.sh <cartella>` copia i file della v2, applica la patch e compila `vlreflector` (stesse opzioni del v2) più le prove, con `-Wall -Wextra`, ASan e UBSan. Se la v2 cambia quei file, `patch` fallisce e la CI lo segnala.
- **Cosa aggiunge:** estensione di stato nel NodeLink (`setStatusExtension`, `peerExtension`: i byte dopo i 9 di stato in HELLO e KEEPALIVE, che i client v2 ignorano); nel `ReflectorCore` la dichiarazione V3 del client, la rubrica con scadenza di 10 minuti (6 byte grezzi del nominativo, massimo 20 voci per annuncio), `REFL_ANNUNCIO` / `REFL_INOLTRO` (ttl ridotto di uno) / `REFL_ESITO` e i contatori `v3Forwarded`, `v3Refused`, `v3Announces`. Un client che non ha dichiarato V3 non può iscrivere né ricevere frame V3 (contati come rifiutati, non come pacchetti v2 rovinati).
- **Pagina di amministrazione:** nella tabella dei nodi c'è la colonna **V3** ("sì" se il nodo ha dichiarato il V3), lo stato JSON porta `v3` per nodo e i contatori `v3Announces`, `v3Forwarded`, `v3Refused`; la riga di fine servizio li riporta. La pagina pubblica non cambia.
- **Provato sul PC:** le prove della v2 sui moduli patchati restano identiche (79 e 67 controlli); 26 controlli nuovi in `reflector/tests/test_reflector_v3.cpp`; `tests/interop/test_reflector_cpp.py` con due veri `vlnode` v2 (testo, voce RELAYED, nessuna firma errata) e client V3 su socket UDP veri (annuncio, busta, esito consegnato e non trovato, client v2 escluso).
- **Nota:** il reflector comunica la sua dichiarazione V3 nel KEEPALIVE successivo (fino a 20 s); i frame V3 non la aspettano, perché il reflector riconosce già il client dal suo HELLO.
- **Non provato:** nessuna scheda vera; nessun server in esercizio; la colonna V3 è provata sullo stato JSON e sul testo della pagina, non in un browser.

## 10. Limiti per client V3 (26/11/2026)
Scritti nella patch C++ (`reflector/v3.patch`) e nel riferimento in Python (`tools/reflector_v3.py`), con gli **stessi valori**. Provati sul PC; **i valori sono di partenza**, da fissare con le prove su un server vero.

| Limite | Valore di partenza | Cosa succede oltre |
|---|---|---|
| Buste (`REFL_INOLTRO`) per client | **1200 al minuto** (20 al secondo: sopra il massimo della radio, un frame da 255 byte a R3 dura 58 ms) | la busta non viene inoltrata; il mittente riceve `REFL_ESITO` **RIFIUTATO** |
| Annunci della rubrica per client | **12 al minuto** (uno ogni 5 s) | l'annuncio è scartato, la rubrica resta quella di prima |
| Byte inoltrati per client | **256 kB ogni 10 minuti** (rete di sicurezza se manca l'OFFER) | come le buste: RIFIUTATO |
| Oggetto dentro la busta | **64 kB**, come la radio e il ponte telefono-scheda | un frame OFFER del protocollo immagini con dimensione maggiore è rifiutato (**RIFIUTATO**) |

I conteggi sono **per client** e a **finestra fissa** (un minuto per le buste e gli annunci, 10 minuti per i byte): chi supera il limite non influenza gli altri. Cambiare la chiave di un client azzera i suoi contatori. Lo stato JSON della pagina di amministrazione e la riga di fine servizio riportano `v3RateLimited` e `v3TooBig`.

**Limite del controllo del tetto:** il reflector legge solo il frame OFFER (dimensione a 24 bit); un oggetto che dichiara una dimensione piccola e poi manda più pezzi del dichiarato non è fermato dal tetto per oggetto, ma dal tetto di byte per client. Il controllo completo, che ricorda la dimensione di ogni oggetto, non è scritto.
