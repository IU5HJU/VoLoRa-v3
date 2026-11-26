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

## 7. Non fatto, e da decidere
- **Server di produzione.** Il riferimento è in Python; la v2 ha un reflector in C++ con le pagine web. **Da decidere:** estendere il C++ della v2 (stesso codice, la stessa installazione) o tenere Python.
- **Pagine di amministrazione e pubblica** (chi è collegato, chi parla): non portate; vanno uguali alla v2, con in più una colonna "V3" e la rubrica. Quella pubblica non mostra indirizzi, chiavi, id.
- **Limiti di velocità** per client e di dimensione dei trasferimenti V3 (un'immagine su Internet può essere più grande di quello che passa in radio).
- **Più modi voce insieme** (oggi un reflector inoltra un solo modo voce: limite della v2 tenuto per compatibilità).
- **Stanze** (il campo `canale` del collegamento v2 non è usato; i nodi accettano solo il loro canale): si potrebbero usare per separare zone, da decidere.
- **Collegamento con reflector esterni** (SvxLink, YSF, DMR): resta quello che dice lo studio della v2.
- **Prova su schede:** nessun gateway V3 esiste ancora; il lato "client V3" è solo nelle prove.
