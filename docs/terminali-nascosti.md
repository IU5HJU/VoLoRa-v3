# I terminali nascosti: cosa sono e come li gestisce il protocollo

Pagina didattica. Spiega un problema classico delle reti radio e perché il protocollo V3 ([mesh-v3.md](mesh-v3.md)) è costruito in un certo modo per evitarlo.

> **Cosa è calcolato e cosa è ipotesi.** Le percentuali di questa pagina vengono dal [simulatore mesh](simulatore-mesh.md) (`tools/sim_mesh.py`): sono un **modello**, non misure su schede. Il fenomeno in sé è noto da sempre nelle reti radio; i numeri dipendono dalle ipotesi del modello (collegamenti stimati, ombreggiamento casuale).

## 1. L'idea
Tre stazioni in fila: **A — B — C**.
- A e B si sentono.
- B e C si sentono.
- **A e C sono troppo lontane e non si sentono.**

A e C sono **terminali nascosti** l'uno all'altro: ciascuna è nascosta all'altra, mentre B le vede entrambe.

## 2. Cosa succede
1. A vuole trasmettere a B. Ascolta il canale: libero. Trasmette.
2. C vuole trasmettere a B. Ascolta il canale: **non sente A**, quindi lo trova libero. Trasmette.
3. I due segnali arrivano **insieme a B** e si sovrappongono. B non riceve né l'uno né l'altro.

Nessuna delle due ha sbagliato. Il controllo del canale ha funzionato, ma ha controllato **il posto sbagliato**. Quello che conta è se il canale è libero **dove ascolta il destinatario**, non dove ascolta chi trasmette.

Succede lo stesso con i ripetitori radioamatoriali: due stazioni che chiamano il ripetitore da lati opposti non si sentono fra loro. Il ripetitore le sente tutte e due, ed è per questo che il suo ruolo è anche quello di far sapere a tutti chi sta parlando.

## 3. Perché pesa di più nel nostro progetto
- Con i gradini lenti (R13, R14) i pacchetti **durano secondi o decine di secondi**: la finestra in cui due stazioni possono sovrapporsi è larga.
- I collegamenti lunghi sono proprio quelli dove due stazioni sono molto distanti fra loro.
- **Beacon, polling e risposte alla richiesta di ripetitori** sono tutti casi in cui tante stazioni parlano allo stesso nodo.
- Un **gruppo di ripetitori** trasmette al destinatario tutto insieme, e i ripetitori possono non sentirsi.

## 4. Cosa mostra il simulatore
**Beacon** (50 stazioni a R14, un beacon ogni 10 minuti, ascolto prima di parlare), beacon senza collisione:

| Coppie di stazioni che non si sentono | Beacon senza collisione |
|---|---|
| 0 % (tutte si sentono) | circa 60 % |
| 20 % | circa 28 % |
| 50 % | circa 13 % |

**Gruppo di ripetitori** (4 candidati, 25 km, regola N_min = 2, T = 1, 1500 scenari, 15 % di probabilità di caduta per ripetitore):

| Come i membri si dividono il canale | Efficienza | Tempo mediano | Completa |
|---|---|---|---|
| **Turni dall'orologio** (scelta del protocollo) | 100 % | 3 min | 92,2 % |
| **Ascolto prima di parlare** | 92 % | 4 min | 84,8 % |

- La regola "pochi e veloci" sceglie i ripetitori **meglio posizionati**, che tendono a essere vicini fra loro: solo in circa **l'11 % dei gruppi** due membri non si sentono. Il simulatore lo ha trovato; non era scontato.
- **Quando però succede, l'ascolto rende solo il 34 % del canale**: i due membri parlano insieme, si sovrappongono al destinatario e si perdono. Solo la **cattura** (se un segnale supera l'altro di almeno 6 dB al ricevitore, LoRa decodifica comunque il più forte) ne salva una parte.
- Con i **turni dall'orologio** il problema non esiste, perché nessuno ha bisogno di sentire nessuno.

## 5. Come il protocollo li gestisce
| Rischio | Soluzione nel protocollo |
|---|---|
| Più ripetitori trasmettono al destinatario | **Turni assegnati dal mittente nel frame GRUPPO** e agganciati all'**orologio** (NTP o GPS, basta un secondo). I membri non devono sentirsi. |
| Un membro che il destinatario non sente | Il **destinatario decide**: manda **VETO** con il nominativo del membro che non sente al gradino scelto. È l'unico che sa chi arriva davvero. |
| Le risposte alla RICHIESTA-RIPETITORI si sovrappongono | **Slot dal nominativo più ascolto** (chi sente uno già in onda aspetta il primo slot libero). Simulato: 98 % delle OFFERTE arrivano al primo giro con 8 slot, contro il 28 % dei soli slot e il 78 % dell'ascolto da solo ([simulatore-mesh.md](simulatore-mesh.md)). |
| Due nodi sentono insieme la stessa mobile | **Voto via radio** su un canale di servizio fra i nodi (frame VOTO, vince il margine migliore): [voting-isofrequenza.md](voting-isofrequenza.md) |
| Beacon di molte stazioni | **Slot dall'orologio** e slot adattivo: l'ascolto da solo non basta. |
| Resta qualche collisione | **Fontana:** ogni simbolo ha un ESI diverso (contatore × M + posizione), quindi un simbolo perso non fa mancare un pezzo preciso: ne basta un altro. |

In una frase: **non ci si affida al fatto che le stazioni si sentano; ci si affida a un orologio comune e al destinatario, che è l'unico a sapere cosa arriva davvero.**

## 6. Per fare i conti da solo
```bash
python3 tools/sim_mesh.py nascosti
```
```bash
python3 tools/sim_mesh.py beacon --stazioni 50
```
Per provare a mano: in `tools/sim_mesh.py` la funzione `Scenario.hears(a, b, rid)` dice se due stazioni si sentono a un dato gradino; `efficienza_canale()` confronta i turni con l'ascolto; `CAPTURE_DB = 6` è la soglia della cattura.

### Esercizi
1. Disegna tre stazioni A, B, C in fila con A e C fuori portata. Quale delle tre vede il problema? Perché B non lo risolve da sola?
2. Perché il VETO lo manda il destinatario e non il mittente?
3. Se gli orologi di due ripetitori differiscono di 2 secondi, i turni possono ancora collidere? (*Risposta: sì, con turni più corti dell'errore. Per questo i turni sono lunghi come un frame intero più un intervallo di guardia, e basta un orologio entro un secondo.*)

## 7. Glossario
- **Terminale nascosto:** stazione che il trasmettitore non sente ma il ricevitore sì.
- **Ascolto prima di parlare (LBT):** si trasmette solo se il canale sembra libero. Funziona solo se ci si sente.
- **Cattura:** il ricevitore decodifica il segnale più forte (almeno 6 dB sopra) anche se ce n'è un altro in contemporanea.
- **Slot / turno:** momento assegnato in base all'orologio.
- **VETO:** frame con cui il destinatario esclude un membro che non sente.

## 8. Limiti
- Gli stessi di [simulatore-mesh.md](simulatore-mesh.md): collegamenti stimati e ombreggiamento casuale, **non misure**. Il numero di coppie nascoste in una zona vera dipende dal terreno.
- Nel gruppo si simula l'ascolto con una regola semplice (parla chi non sente nessuno di quelli già partiti; gli altri collidono); l'ascolto vero dei moduli LoRa ha una finestra di rilevamento di due simboli (modellata solo nei beacon).
- Le risposte OFFERTA con terminali nascosti sono simulate (26/11/2026); l'errore dell'orologio nei turni anche. La fase 1 (mittente verso i membri) non ha il problema: trasmette solo il mittente.
- Non è provato su schede.
