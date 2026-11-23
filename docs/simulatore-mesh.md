# Simulatore mesh V3 (bozza)

Programma da riga di comando ([`tools/sim_mesh.py`](../tools/sim_mesh.py), prove in [`tests/sim/test_sim_mesh.py`](../tests/sim/test_sim_mesh.py)) per provare sul PC due pezzi della logica di [mesh-v3.md](mesh-v3.md): i **beacon con le collisioni** e la **scelta del gruppo di ripetitori** con la regola "pochi e veloci".

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
- **Un canale.** I terminali nascosti sono simulati nei beacon e nella fase 2 del gruppo (tra i membri), **non** nelle risposte OFFERTA e non nella fase 1. I turni sono considerati perfetti (errore di orologio nullo).
- **Due fasi in sequenza** (mittente ai ripetitori, poi ai destinatari), senza sovrapposizione. Un'implementazione che passa i pezzi ai ripetitori mentre li rilancia sarebbe più veloce.
- **Caduta dei ripetitori** indipendente e uguale per tutti.
- **La fontana** nel Monte Carlo è ancora un costo di tempo (1,25 %), ma quel valore ora viene dal codice vero ([`tools/fontana.py`](../tools/fontana.py): combinazioni casuali su GF(2), decodifica con eliminazione di Gauss, ESI = contatore × M + indice, prova con tre membri e perdita 50 %). Non è provato su schede.

## Prossimi passi
Simulare i terminali nascosti nelle risposte OFFERTA, un errore dell'orologio nei turni, una sovrapposizione fra le due fasi e la perdita dei pacchetti dentro le fasi; poi collegare la scelta del gruppo ai frame di [mesh-v3.md](mesh-v3.md) (RICHIESTA-RIPETITORI, OFFERTA, GRUPPO).
