# Prova in laboratorio dei gradini lenti (R10-R14)

Scopo: sapere **su schede vere** se i gradini lenti della scala ([scala-modi.md](scala-modi.md)) funzionano fra le due T3, in particolare R13 e R14 (larghezza di banda 15,6 e 7,8 kHz). Finora i loro numeri sono **stime**: l'unico dato misurato è lo scarto dei due quarzi (circa 1,55 kHz, cioè il 20 % di 7,8 kHz), che fa temere che senza correzione di frequenza (AFC) o senza TCXO R13-R14 non si agganci.

| Gradino del protocollo | Modo dell'app | Larghezza di banda | SF |
|---|---|---|---|
| R10 | L9 | 125 kHz | 12 |
| R11 | L10 | 62,5 kHz | 12 |
| R12 | L11 | 31,25 kHz | 12 |
| R13 | L12 | 15,6 kHz | 12 |
| R14 | L13 | 7,8 kHz | 12 |

## Prova con due schede su un solo PC (scheda Misure)
1. Collega le due T3, scrivi il nominativo, **F1** (INFO) e **F2** (nominativo).
2. Metti le schede **vicine** con **attenuatore in serie** (se hai il 40 dB: 40 dB) e potenza bassa (2 dBm). Prima prova **senza** attenuatore alto: si vuole sapere se il gradino si aggancia, non la sensibilità.
3. Nel campo **Serie (F10)** scrivi `R10,R11,R12,R13,R14`; **Pacchetti per modo** 10; **Byte** 26 (un pacchetto piccolo: a R14 un pacchetto da 255 byte dura minuti).
4. Premi **F10**. L'app imposta le due schede, calcola da sola l'intervallo dal tempo in aria (con 10 pacchetti a modo la serie R10-R14 dura circa 11 minuti, di cui circa 6 per R14) e aggiunge una riga per modo. **Esc** ferma.
5. Leggi la tabella:
   - **Ricevuti** 10 su 10 a tutti: il gradino si aggancia.
   - **Deriva Hz** (FEI): lo scarto di frequenza visto dal ricevitore. Se a R13-R14 è vicino a metà della larghezza di banda (circa 8 kHz per R13, 4 kHz per R14) il gradino sta per perdersi.
   - **ToA mis./calc.**: il tempo in aria misurato contro quello calcolato (vedi la formula già verificata, +1,2 %).
6. Se R13 o R14 **non si agganciano**, ripeti **invertendo** chi trasmette (selettore Trasmette A/B): lo scarto cambia segno, un lato può andare meglio dell'altro. Annota anche la **temperatura** (le schede scaldano).
7. Poi aumenta l'attenuazione di 10 dB alla volta e rifai la serie solo con i gradini che si agganciano, per trovare la **sensibilità** di ciascuno (campo Att dB e F10).

## Prova con un collega (scheda Prove sul campo)
Stessa serie, ma con **una scheda per stazione** e partenza concordata dall'orologio:
1. Concordate T0 (UTC), le frequenze e la serie, per esempio `R11,R12,R13,R14`. Chi vuole può usare **Copia le condizioni per il collega**: con la serie compilata il testo diventa "PROVA VoLoRa SERIE …".
2. In **Prove sul campo** compilate il campo **Serie di modi** (stessi modi, stessi **pacchetti per modo** e **byte** della scheda Misure). L'app calcola il piano da T0: ogni modo parte dopo il precedente con la coda e una pausa di 20 s. **I due piani sono uguali perché dipendono solo da T0 e dai parametri.**
3. Uno sceglie **Trasmetto**, l'altro **Ricevo**; entrambi **Programma la prova**. La serie va avanti da sola, una riga per modo.
4. A fine serie: **Copia tutte** (le mie righe), poi l'altro **Incolla i dati del collega…** con più righe insieme: l'app le abbina da sola per **modo e T0** e calcola la perdita per ogni modo (e la distanza, se le posizioni ci sono).
5. Per salvare: **Salva CSV** nella scheda campo, poi GitHub come sempre ([guida-colleghi.md](guida-colleghi.md)).

## Cosa aspettarsi e come leggere il risultato
- **Stima** (non misurata): a R10 la sensibilità è circa -137 dBm; ogni dimezzamento della banda guadagna circa 3 dB, fino a circa -149 dBm a R14 con un oscillatore perfetto.
- **Lo scarto dei quarzi comanda**: se R13-R14 non si agganciano a distanza breve, non è un problema di segnale ma di frequenza; vuol dire che senza AFC (correzione automatica della frequenza) o TCXO quei gradini non sono usabili fra queste schede. Questo è un **risultato valido**, da riportare nel registro delle misure.
- Il risultato si riporta in [`docs/misure/`](misure/) con il modello CSV e si confronta con la stima di [scala-modi.md](scala-modi.md).

## Stato
Gli strumenti (serie F10, serie programmata, unione automatica) sono **provati con le schede finte sul PC**. **Non** sono provati con le T3 vere: i risultati sui gradini lenti sono ancora da misurare.
