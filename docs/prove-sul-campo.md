# Prove sul campo a distanza reale (protocollo)

Scopo: confrontare le **misure a banco** ([piano-misure.md](piano-misure.md)) con il comportamento reale a distanza, e provare i modi che il banco non raggiunge (sensibilità sotto circa -100 dBm). Le cifre sotto sono **stime di progetto** da confermare con le prime prove.

## 1. Quanta distanza serve davvero
- **Perdita in spazio libero a 433,5 MHz:** `FSPL (dB) = 85,2 + 20 · log10(distanza in km)`. Esempio: 10 km danno circa 105 dB, 50 km circa 119 dB.
- **Orizzonte radio:** circa `4,1 × (√h1 + √h2)` km con le altezze in metri (4,1 con la rifrazione normale; è solo un'indicazione). Esempio: 2 m e 100 m di antenna danno circa 48 km.
- **Collegamento stimato:** potenza ricevuta = potenza trasmessa + guadagni delle antenne − perdita in spazio libero − perdite varie (cavi, ostacoli). Si confronta con la sensibilità stimata in [scala-modi.md](scala-modi.md) per prevedere dove un modo smette di funzionare.
- **Conseguenza:** in vista i modi più robusti non si portano al limite: l'orizzonte arriva prima. Con 10 dBm e antenne a 0 dBi, il limite del modo L9 (circa -137 dBm) sarebbe oltre 100 km in spazio libero, quindi ostacoli o attenuatori servono per misurarlo.

## 2. L'idea dell'attenuatore in campo (da verificare)
Inserire un attenuatore fisso (10, 20 o 30 dB) in serie all'antenna del trasmettitore **simula una distanza maggiore** senza spostare le stazioni: 20 dB corrispondono a una distanza 10 volte maggiore in spazio libero. Così si può portare un modo al suo limite a una distanza praticabile. **Non è ancora stato provato**: va confrontato con due misure a distanze diverse senza attenuatore. Il vantaggio ulteriore è che la potenza irradiata scende, quindi si disturba meno.
Attenzione: il misuratore di potenza e il NanoVNA devono misurare la perdita vera dell'attenuatore e dei cavi, non l'etichetta.

## 3. Cosa serve
Vedi [materiale.md](materiale.md) (punto 3) e [guida-colleghi.md](guida-colleghi.md). Per ogni stazione: scheda con firmware di misura, nominativo del proprietario, antenna a 433 MHz con ROS misurato, PC o telefono per la seriale, GPS e metro per le altezze.

## 4. Procedura base
Due stazioni, A (trasmette) e B (riceve), alla stessa frequenza e con gli stessi parametri.
1. **A casa, a banco:** tarare le due schede con la misura M2 ([piano-misure.md](piano-misure.md)) sul modo che si userà.
2. **Percorso:** scegliere un percorso con visibilità (o ostacoli noti) e annotare le due posizioni (locatore a 6 caratteri o distanza) e le altezze delle antenne.
3. **Potenza e antenna:** misurare la potenza trasmessa con il misuratore e il ROS dell'antenna con il NanoVNA, **a casa**, prima di partire.
4. **Misura:** su B `RX <secondi>`, su A `TX 200 300`. Per ogni modo almeno **200 pacchetti** da 255 byte.
5. **Più distanze, stesso modo:** ripetere a 3-4 distanze, o con 3-4 attenuatori in serie, per tracciare la curva "perdita pacchetti contro potenza ricevuta".
6. **Registrare**: tutto quello che c'è nella scheda di rilievo del punto 5. L'RSSI e l'SNR medi vengono dalla scheda ricevente (`RXSUM`).
7. **Se la scheda ha un GPS** (T-Beam), annotare l'ora di ogni serie per incrociarla con la posizione.

## 5. Scheda di rilievo (una per serie di misure)
Si compila a mano o con il modello [`misure/modello-rilievo.csv`](misure/modello-rilievo.csv).

| Campo | Esempio / nota |
|---|---|
| Data e ora | 2026-12-05 10:30 |
| Stazione A | nominativo, locatore a 6 caratteri, altezza antenna in m |
| Stazione B | idem |
| Distanza A-B | km (anche stimata sulla mappa) |
| Percorso | in vista / ostacoli (quali) / tra le colline |
| Schede | T3 o T-Beam SX1262, versione del firmware (`INFO`) |
| Antenne | tipo, guadagno dichiarato, ROS misurato |
| Frequenza e modo | `MODE LORA 125 9 5`, 433,475 MHz |
| Potenza impostata e misurata | dBm |
| Attenuatore in serie | dB misurati (0 se non c'è) |
| Meteo | sereno, pioggia, temperatura |
| Pacchetti | inviati / ricevuti / rovinati |
| RSSI e SNR medi | da `RXSUM` |
| `fei_hz` | deriva di frequenza (solo LoRa) |
| Note | interferenze, comportamento strano, foto |

## 6. Cosa si ricava
- **Sensibilità reale in campo** per ogni modo, confrontata con banco e stima.
- **Margine di collegamento** per distanza e percorso, utile alla scala dei modi della V3 e alla negoziazione.
- **Verifica dell'idea dell'attenuatore:** le curve con attenuatore devono coincidere con quelle a distanza maggiore senza attenuatore.
- **Interferenze reali** in 430-440 MHz nella zona (utile per la coesistenza, [punti-aperti.md](punti-aperti.md)).

## 7. Sicurezza e buon vicinato
- Nominativo proprio, potenza minima necessaria (di norma a bassa potenza: **2-10 dBm**), nessuna trasmissione continua senza bisogno.
- Prima di trasmettere **ascolta** la frequenza con la scheda o con l'SDR.
- Non trasmettere su frequenze di ripetitori, satelliti o beacon: in 430-440 MHz ce ne sono. Il progetto ha deciso di non porre limiti di banda ma la **responsabilità di non disturbare resta di chi trasmette**.
