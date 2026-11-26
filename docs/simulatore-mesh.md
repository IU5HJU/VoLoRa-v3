# Simulatore mesh V3 (bozza)

Programma da riga di comando ([`tools/sim_mesh.py`](../tools/sim_mesh.py), prove in [`tests/sim/test_sim_mesh.py`](../tests/sim/test_sim_mesh.py)) per provare sul PC due pezzi della logica di [mesh-v3.md](mesh-v3.md): i **beacon con le collisioni** (anche con i **terminali nascosti**) e la **scelta del gruppo di ripetitori** con la regola "pochi e veloci" (anche con i terminali nascosti fra i membri). Il codice a fontana è in [`tools/fontana.py`](../tools/fontana.py); l'elezione fra due nodi in isofrequenza ha un simulatore a parte ([voting-isofrequenza.md](voting-isofrequenza.md)).

> **Stato (23/11/2026): scritto e provato sul PC. Il modello è un'ipotesi, NON misure.** I collegamenti usano la perdita in spazio libero più una perdita extra media (ostacoli) con ombreggiamento casuale, e le sensibilità **stimate** di [scala-modi.md](scala-modi.md). Dice come si comporta la **logica**, non quanto va lontano la radio. Nessuna parte è provata su schede.

## Cosa simula
1. **Beacon** (solo nominativo, 7 byte): ALOHA puro, **slot dal nominativo** (fissi), **slot adattivo** (chi collide sceglie uno slot libero), **ascolto prima di parlare** (con finestra di rilevamento di due simboli). Di base tutte le stazioni si sentono fra loro; il parametro `nascosti` è la probabilità che due stazioni non si sentano (terminali nascosti).
2. **Gruppo di ripetitori:** mittente a (0, 0), destinatario a distanza D, ripetitori sparsi a caso. Ogni collegamento usa il **gradino più veloce con almeno 6 dB di margine**. Un solo canale: **i membri trasmettono a turni al gradino comune, il più lento dei membri**. Fase 1: il mittente passa l'oggetto ai membri. Fase 2: i membri mandano al destinatario simboli a fontana (sovrapposizione misurata con il codice vero: 1,6 simboli ogni 128 pezzi, circa 1,25 %). Ogni ripetitore può cadere con probabilità p (di base 15 %).
3. **Politiche confrontate:** solo il **diretto**; il **miglior ripetitore singolo**; **tutti** i candidati; la **regola** (almeno N_min membri, gradino comune non più lento del migliore di oltre T gradini); **diretto o regola** (il più veloce dei due).

## Risultati: i beacon (gradino R14, un beacon ogni 10 minuti, 7 byte = 15,9 s)
| Stazioni | puro (formula) | puro (simulato) | slot dal nominativo | slot adattivo | ascolto prima |
|---|---|---|---|---|---|
| 5 | 76.7 % | 79.9 % | 89.8 % | 100.0 % | 98.6 % |
| 20 | 34.7 % | 35.1 % | 59.3 % | 100.0 % | 89.7 % |
| 50 | 7.1 % | 6.9 % | 26.0 % | 32.1 % | 59.0 % |

- **Con circa 5 stazioni per zona (la decisione dell'autore) il beacon a R14 va bene**: il caso peggiore (nessun coordinamento) dà il 79,9 % di beacon senza collisione, lo **slot adattivo** il 100 %. Con 20 stazioni il puro scende al 35 %, ma slot adattivo e ascolto restano oltre il 94 %.
- A **50 stazioni** a R14 non ci sono abbastanza slot (circa 37 nel periodo): lo slot adattivo non basta; l'**ascolto prima di parlare** tiene il 60-70 %, e **con i terminali nascosti lo peggiorano molto**: nella prova a 50 stazioni (R14) è circa 60 % se tutte si sentono, circa 28 % con il 20 % di coppie nascoste, circa 13 % con il 50 %. Con zone grandi non ci si può fidare dell'ascolto: servono gli slot dall'orologio. Con tante stazioni serve un gradino meno estremo (R12 o R10).
- La **simulazione concorda con le formule** del documento (puro simulato 79,9 % contro 76,7 % di formula a 5 stazioni; 35,0 % contro 34,7 % a 20).

## Risultati: la regola "pochi e veloci"
Oggetto da 20 kB, perdita extra media 25 dB, un ripetitore su 7 cade. Tempo mediano e probabilità di completare il trasferimento.

**3 ripetitori candidati, 15 km:**

| politica | copertura | tempo mediano | completa |
|---|---|---|---|
| diretto | 99 % | 3 min | 100.0 % |
| migliore | 100 % | 63 s | 85.0 % |
| tutti | 100 % | 21 min | 99.6 % |
| regola | 100 % | 75 s | 90.9 % |
| diretto o regola | 100 % | 45 s | 93.6 % |

**3 ripetitori candidati, 25 km:**

| politica | copertura | tempo mediano | completa |
|---|---|---|---|
| diretto | 97 % | 17 min | 100.0 % |
| migliore | 100 % | 3 min | 85.0 % |
| tutti | 100 % | 64 min | 99.5 % |
| regola | 100 % | 4 min | 91.5 % |
| diretto o regola | 100 % | 2 min | 94.0 % |

**3 ripetitori candidati, 35 km:**

| politica | copertura | tempo mediano | completa |
|---|---|---|---|
| diretto | 94 % | 17 min | 100.0 % |
| migliore | 100 % | 5 min | 85.0 % |
| tutti | 100 % | 1.9 h | 99.2 % |
| regola | 100 % | 18 min | 91.9 % |
| diretto o regola | 100 % | 4 min | 94.3 % |

**8 ripetitori candidati, 25 km:**

| politica | copertura | tempo mediano | completa |
|---|---|---|---|
| diretto | 97 % | 17 min | 100.0 % |
| migliore | 100 % | 66 s | 85.0 % |
| tutti | 100 % | 3.3 h | 100.0 % |
| regola | 100 % | 2 min | 92.9 % |
| diretto o regola | 100 % | 75 s | 93.9 % |

Lettura:
1. **Usare tutti i candidati è la peggiore scelta**: a 25 km impiega circa **64 minuti contro 4** della regola. È la tua intuizione, confermata: il candidato più debole trascina tutto il gruppo a un gradino lento.
2. **Il miglior ripetitore singolo è il più veloce** ma ha l'affidabilità più bassa (85 % con la probabilità di caduta scelta).
3. **La regola** costa un po' di tempo in più del singolo migliore (per esempio 4 minuti contro 3) e **alza la probabilità di completare** (circa 91-93 % contro 85 %): la ridondanza non dà velocità, dà affidabilità.
4. **A 25-35 km la ripetizione è molto più veloce del diretto** (4 minuti contro 17 a 25 km).
5. **"Diretto o regola"**, cioè tentare il diretto quando è più rapido, non è mai peggiore.

## Taratura di N_min e della tolleranza T
Stessi scenari, 25 km, 3 e 8 ripetitori candidati:

**3 ripetitori:**

| N_min | tolleranza | tempo mediano | completa |
|---|---|---|---|
| 1 | 0 | 3 min | 85.0 % |
| 2 | 0 | 3 min | 87.5 % |
| 2 | 1 | 4 min | 91.3 % |
| 2 | 2 | 7 min | 94.2 % |
| 3 | 1 | 3 min | 87.1 % |
| 3 | 2 | 4 min | 89.8 % |
| 3 | 4 | 34 min | 95.0 % |

**8 ripetitori:**

| N_min | tolleranza | tempo mediano | completa |
|---|---|---|---|
| 1 | 0 | 66 s | 85.0 % |
| 2 | 0 | 75 s | 88.2 % |
| 2 | 1 | 2 min | 92.9 % |
| 2 | 2 | 2 min | 95.6 % |
| 3 | 1 | 76 s | 89.8 % |
| 3 | 2 | 3 min | 94.0 % |
| 3 | 4 | 5 min | 98.6 % |

- **N_min = 2, T = 1** (la partenza decisa) è un buon compromesso: affidabilità da 85 % a 91-93 % con un costo di tempo contenuto.
- **Una tolleranza grande è un errore**: con N_min = 3 e T = 4 il tempo con 3 ripetitori sale a **34 minuti**, perché il gruppo accetta un membro lentissimo. Conferma la regola: più membri non devono costare molto.
- N_min = 2 con T = 2 migliora ancora l'affidabilità (94-96 %), a un costo di tempo che da 4 minuti sale a 7 (3 ripetitori).

## Risultati: i terminali nascosti nel gruppo di ripetitori
Spiegazione per chi non li conosce: [terminali-nascosti.md](terminali-nascosti.md). Il simulatore (`python3 tools/sim_mesh.py nascosti`) confronta, sugli stessi scenari, i membri che si dividono il canale con i **turni dall'orologio** (scelta del protocollo) e membri che **ascoltano prima di parlare**. Due membri che non si sentono parlano insieme e si perdono al destinatario, salvo la cattura (6 dB).

| 4 candidati, 25 km, regola 2/1, 1500 scenari | Efficienza | Tempo mediano | Completa |
|---|---|---|---|
| turni dall'orologio | 100 % | 3 min | 92,2 % |
| ascolto prima di parlare | 92 % | 4 min | 84,8 % |

- Solo circa l'**11 % dei gruppi scelti** ha una coppia che non si sente (la regola sceglie i ripetitori migliori, in genere vicini), ma **in quei casi l'ascolto rende il 34 %**.
- I turni dall'orologio rendono il 100 % in ogni caso: è il motivo per cui il GRUPPO assegna i turni e il VETO lascia al destinatario l'ultima parola.

## Limiti del modello
- **Tutto stimato:** sensibilità, perdita extra e ombreggiamento. I numeri relativi (la regola contro tutti i candidati) sono più affidabili di quelli assoluti.
- **Un canale.** I terminali nascosti sono simulati nei beacon, nella fase 2 del gruppo (tra i membri) e nelle risposte OFFERTA; **non** nella fase 1. L'errore dell'orologio è simulato a parte (punto sotto), non nel Monte Carlo del gruppo, dove i turni restano perfetti.
- **Due fasi in sequenza** (mittente ai ripetitori, poi ai destinatari), senza sovrapposizione. Un'implementazione che passa i pezzi ai ripetitori mentre li rilancia sarebbe più veloce.
- **Caduta dei ripetitori** indipendente e uguale per tutti.
- **La fontana** nel Monte Carlo è ancora un costo di tempo (1,25 %), ma quel valore ora viene dal codice vero ([`tools/fontana.py`](../tools/fontana.py): combinazioni casuali su GF(2), decodifica con eliminazione di Gauss, ESI = contatore × M + indice, prova con tre membri e perdita 50 %). Non è provato su schede.

## Risultati: le risposte OFFERTA con terminali nascosti (26/11/2026)
Programma: `python3 tools/sim_mesh.py offerte`. La RICHIESTA-RIPETITORI arriva a tutti; ogni candidato che sente il mittente risponde con un'OFFERTA da 24 byte a R10 (1,48 s). Cinque ripetitori sparsi, 25 km, i candidati si sentono o no secondo il collegamento (nel 38 % degli scenari almeno una coppia è nascosta). Chi non è stato sentito ripete al giro dopo (massimo 3 giri); alla collisione sopravvive il segnale più forte di 6 dB.

| Come rispondono | Slot | Al primo giro | Tutte al primo giro | Le 2 migliori entro 3 giri | Tempo mediano per le 2 migliori | Durata del giro |
|---|---|---|---|---|---|---|
| ascolto e ritardo casuale | 8 | 93 % | 78 % | 100 % | 11,0 s | 13 s |
| slot dal nominativo | 8 | 73 % | 28 % | 99 % | 11,3 s | 13 s |
| slot dal nominativo | 16 | 85 % | 54 % | 100 % | 21,1 s | 26 s |
| slot dal nominativo | 32 | 92 % | 73 % | 100 % | 39,0 s | 52 s |
| slot per qualità (il migliore per primo) | 8 | 60 % | 24 % | 94 % | 8,0 s | 13 s |
| **slot dal nominativo + ascolto** | 8 | **98 %** | **93 %** | 100 % | 11,3 s | 13 s |
| slot dal nominativo + ascolto | 16 | 99 % | 97 % | 100 % | 19,4 s | 26 s |

- **I soli slot dal nominativo vanno male con pochi slot:** con 5 candidati e 8 slot due scelgono quasi sempre lo stesso (problema dei compleanni): solo il 28 % arriva intero al primo giro. Servirebbero 32 slot, e il giro durerebbe 52 s.
- **L'ascolto da solo regge** (78 % al primo giro intero) perché solo una parte delle coppie è nascosta.
- **La combinazione vince:** slot dal nominativo **più ascolto** (chi sente uno già in onda aspetta il primo slot libero) dà il 98 % al primo giro con 8 slot e 13 s per giro. È la **proposta** per le OFFERTE; il simulatore lo conferma, non l'ho ancora fissato come decisione.
- **Gli slot per qualità** danno le due migliori offerte prima (8 s) ma perdono più offerte (94 % entro 3 giri): utili se basta avere le prime due; ai tentativi successivi si aggiunge un sorteggio altrimenti si ripetono le stesse collisioni.

## Risultati: l'errore dell'orologio nei turni (26/11/2026)
Programma: `python3 tools/sim_mesh.py turni`. Tre membri trasmettono a turno; ognuno parte all'ora del proprio orologio, sbagliata di un errore gaussiano. Un turno si perde se si sovrappone al vicino. **Guardia minima per il 98 % di turni utili** e **efficienza** (turni utili × turno / (turno + guardia)):

| Errore dell'orologio (σ) | Turno 2 s | Turno 5 s | Turno 10 s | Turno 30 s |
|---|---|---|---|---|
| NTP, 20 ms | guardia 0,10 s, 95 % | 0,10 s, 98 % | 0,10 s, 99 % | 0,10 s, 100 % |
| 100 ms | 0,35 s, 84 % | 0,35 s, 93 % | 0,35 s, 96 % | 0,35 s, 98 % |
| GPS Bluetooth, 400 ms | 1,25 s, 60 % | 1,25 s, 79 % | 1,25 s, 87 % | 1,25 s, 94 % |
| 1 s | 3,10 s, 38 % | 3,10 s, 61 % | 3,10 s, 75 % | 3,10 s, 89 % |

- **La guardia serve circa 5σ.** Senza guardia, con orologio NTP, solo il 39 % dei turni è utile; con 0,2 s di guardia il 100 %.
- **La regola "basta un secondo" (applicazione.md) regge, ma i turni devono essere lunghi:** con errore di 1 s un turno da 2 s rende il 38 %, uno da 30 s l'89 %. Un turno non è un frame: è una raffica di frame, per esempio 10-30 s. Con NTP basta qualunque turno da qualche secondo.
- **Conseguenza per il GRUPPO:** la durata del turno e la guardia vanno scelte dalla qualità dell'orologio dei membri (incertezza che l'applicazione già calcola per ogni sorgente); proposta: guardia = 5σ del peggiore dei membri e turno almeno 10 volte la guardia.

## Prossimi passi
Una sovrapposizione fra le due fasi del gruppo e la perdita dei pacchetti dentro le fasi; poi collegare la scelta del gruppo ai frame di [mesh-v3.md](mesh-v3.md) (RICHIESTA-RIPETITORI, OFFERTA, GRUPPO).
