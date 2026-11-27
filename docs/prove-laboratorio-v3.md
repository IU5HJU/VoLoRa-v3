# Prove in laboratorio con due schede V3 (procedura)

**Regola di partenza (27/11/2026):** per le prove la **pagina del telefono sta nella scheda** e non serve Internet ("Internet non è affidabile"). Le due schede e un telefono bastano.

## Stato delle prove (cosa è provato su schede vere)
Prove dell'autore (IU5HJU) con due schede T3, segnalate a voce (senza registro allegato):
- **27/11/2026, pagina da Internet via Bluetooth:** un **testo** inviato dal telefono parte via radio e **arriva sul secondo telefono** (prima prova V3 su schede vere). Un'**immagine dalla galleria falliva** (motivo "telefono sparito").
- **27/11/2026, app Android (APK) via Bluetooth:** installata e funzionante dopo due correzioni emerse dalle prove:
  1. **la ricerca delle schede non trovava niente** finché non si attivava la posizione del telefono: Android 12+ vuole il permesso di posizione per cercare, a meno che il manifest dichiari `neverForLocation` (corretto in `app/scripts/patch-android.py`). **Verificato dall'autore con la posizione disattivata:** l'app **chiede di abilitare la posizione** e poi tutto funziona (probabilmente Android o il telefono la richiedono comunque per la ricerca Bluetooth; non so la versione di Android);
  2. **l'immagine falliva** con `Write timeout` e collegamento caduto: la pagina scriveva pacchetti da 240 byte con un MTU di 185; ora i pacchetti seguono l'MTU negoziato (commit 1bca5a4). Dopo questa correzione l'autore riferisce "adesso funziona" (cosa esattamente, in quali condizioni e con quale immagine: non registrato).
- Non provati su schede o telefoni: il **Wi-Fi della scheda** con la pagina dentro (iPhone), **GPS**, **BOOST/IOF**, **display**, **frequenza configurabile**, il **motivo dell'ultimo riavvio** nel registro.

## Cosa serve
- Due schede uguali con il firmware **`mobile_t3`** (T3) o **`mobile_tbeam1262`** (T-Beam), caricate dalla [pagina di installazione](../site/firmware-v3.html). In laboratorio senza app si usa il **Wi-Fi della scheda** (si accende dalla voce "Wi-Fi" del menu a bordo, o con `WIFI ON`; all'avvio è spento); con l'app Android si usa il Bluetooth. Due telefoni, oppure uno solo che si ricollega all'altra scheda.
- Antenna a 433 MHz **o** un attenuatore da 30-40 dB fra i connettori (con le schede vicine il ricevitore si satura: vedi [piano-misure.md](piano-misure.md)). Mai senza carico.
- Un computer con un monitor seriale a 115200 baud, solo per leggere il registro.

## Quanta attenuazione serve (il ricevitore non deve saturare)
Il livello che arriva al ricevitore è circa **potenza trasmessa − attenuazione totale** (attenuatori, cavi, connettori). Il datasheet dell'SX1278 dà **+10 dBm** come massimo assoluto all'ingresso e quello dell'SX1262 **0 dBm** come massimo di funzionamento, ma molto prima il ricevitore si satura (AGC al limite, RSSI sempre al massimo, pacchetti persi): per le prove si cerca un **RSSI fra −60 e −100 dBm**. Il minimo che il protocollo sa decodificare è circa −120 dBm (R10) e arriva a −136 dBm con i gradini lenti.
- Con **+17 dBm e 20 dB** arrivano circa **−3 dBm**: troppo.
- Con `POWER 2` (il minimo dell'SX1278; l'SX1262 scende a −9) e 20 dB arrivano circa −18 dBm: ancora troppo. **Il comando `POWER` da solo non basta**: il campo è di 15 dB.
- Servono in tutto **60-100 dB** fra le due schede: per esempio **tre attenuatori da 20 dB** in serie (60 dB: con `POWER 2` arrivano circa −58 dBm, con 17 dBm circa −43 dBm) oppure due da 30 dB più i 20 dB che hai (80 dB: −63 dBm a +17 dBm, −78 dBm a +2 dBm). Per provare i gradini lenti e le perdite si sale a 90-100 dB o si abbassa `POWER`.
- Senza attenuatori in più: **tolgi il cavo** e usa le antenne a distanza (stanze diverse, qualche metro) oppure una scheda con il carico da 50 Ω e l'altra con l'antenna. Mai accendere una scheda senza antenna o carico.
- Controlla sempre il valore: sul display e nel registro (`ricevuto da … RSSI … SNR …`) compare l'RSSI. Se è sopra circa −40 dBm o i pacchetti si perdono "a caso" con il segnale fortissimo, il ricevitore è saturo: aggiungi attenuazione.
- Gli attenuatori reggono la potenza: 17 dBm sono 50 mW. Non usare BOOST o IOF MODE con gli attenuatori in linea senza controllarne la potenza massima.

## Preparazione (una volta)
1. Su ogni scheda, sulla seriale: `CALL IU5HJU` (e `CALL IZ5FSN` sull'altra). La scheda si riavvia: il Bluetooth si chiama `VoLoRa-V3 <NOMINATIVO>` e il Wi-Fi (quando lo accendi) `VoLoRa-<NOMINATIVO>`.
2. `FREQ` su tutte e due: devono dire la stessa frequenza (di partenza 433,700 MHz).
3. `WIFI ON` accende il Wi-Fi (spegne il Bluetooth) e mostra rete, **password a 8 cifre** (anche sul display) e indirizzo `http://192.168.4.1`; `WIFI` ne mostra lo stato.
4. `POWER` mostra la potenza normale (di partenza +17 dBm); `POWER 2` la porta al minimo dell'SX1278 (sul T-Beam `POWER -9`). **Sulla scheda mobile la potenza ridotta si salva** e all'avvio un avviso la ricorda; `POWER 17` torna alla normale. BOOST e IOF MODE restano separati (+20 e +22 dBm).
5. `LOG CLEAR` per partire da un registro pulito.

## Collegare il telefono alla scheda (senza Internet)
1. Impostazioni Wi-Fi del telefono → rete `VoLoRa-IU5HJU` → password a 8 cifre. Se compare "senza Internet, restare collegati?" rispondi **sì**. (La scheda risponde alle sonde di Android, iOS e Windows come se ci fosse Internet, proprio perché il telefono non lasci la rete; non è mai stato provato su un telefono vero.)
2. Apri **http://192.168.4.1** nel browser. La pagina è nella scheda: si collega da sola (compare "Collegato alla scheda (Wi-Fi)" e il nominativo).
3. Metti la **posizione**: GPS del telefono o locatore (6 caratteri). Sul T-Beam con `GPS ON` e un fix la posizione GPS della scheda ha la precedenza.
4. Per ricevere dall'altra scheda serve **un telefono collegato anche a lei**: la seconda scheda rifiuta gli oggetti se non ha il telefono. Con un solo telefono: collega prima la scheda che riceve, controlla che la pagina sia aperta, poi collega il telefono alla scheda che invia (oppure usa due telefoni).

## Sequenza di prova
Per ogni passo scrivi sulla scheda che invia `LOG CLEAR`, esegui, poi **scarica il registro** (pagina → "Registro della scheda", oppure `LOG` sulla seriale) e mandalo.

| # | Cosa si invia | Che cosa guardare |
|---|---|---|
| 1 | Testo breve ("prova 1") | Arriva sull'altro telefono; tempo; gradino finale; riepilogo `fine invio ... motivo 0` |
| 2 | Testo di 1000 caratteri | Come sopra; più frame |
| 3 | File di 3-5 kB (qualunque) | Arriva identico (la pagina controlla il CRC); numero di richieste di blocchi |
| 4 | File di 20 kB | Tempo, gradino raggiunto, perdite |
| 5 | **Immagine** dalla galleria, "5 kB" | Se fallisce: il **motivo** nel riepilogo (vedi tabella) |
| 6 | Immagine "10 kB" | idem, livelli consegnati |
| 7 | Telefono scollegato a metà (spegni il Wi-Fi 5 s) | La pagina si ricollega; l'invio riprende |
| 8 | `BOOST ON RISCHIO` e ripeti il 3 | Il display mostra la lettera B; potenza +20 dBm (solo con attenuatore!) |

## Il motivo di un fallimento (riepilogo di fine invio)
Alla fine di ogni invio la scheda manda un riepilogo (`E_DIAG`): la pagina lo scrive nel registro e sotto "Trasmissione radio fallita". Nel registro della scheda: `fine invio obj N: motivo M, livelli L, byte B, R<gradino>, P% confermato, S s`.

| Motivo | Significa | Prima cosa da controllare |
|---|---|---|
| 0 | consegnato | — |
| 1 | nessuna risposta al primo contatto (HELLO) | stessa frequenza? antenna? l'altra scheda è accesa e ha un nominativo? |
| 2 | negoziazione del gradino fallita | segnale troppo debole o troppo forte (saturazione): attenuatore |
| 3 | **offerta non accettata** | l'altra scheda **non ha il telefono collegato**, o l'oggetto è più grande di 32 kB |
| 4 | tempo massimo (600 s) scaduto | stima troppo lunga: oggetto più piccolo o segnale migliore (gradino più veloce) |
| 5 | nessun progresso | collegamento troppo instabile |
| 6 | collegamento perso e non ritrovato | schede spostate, antenna, interferenza |
| 7 | conferma finale non arrivata | l'oggetto può essere arrivato lo stesso (guarda l'altro telefono) |
| 100 | telefono sparito (60 s senza dati) | schermo spento? Wi-Fi caduto? la pagina chiede di tenere lo schermo acceso durante l'invio |
| 101 | annullato | — |

## Cosa mandare dopo la prova
- Il **registro** di tutte e due le schede (`registro-scheda.txt` dalla pagina, o `LOG` dalla seriale).
- Modello del telefono e browser; se il Wi-Fi ha tenuto o ha chiesto "senza Internet".
- Per l'immagine: la dimensione scelta e quanto era grande l'originale.
- Quanto tempo ha impiegato ogni passo e se i display hanno mostrato quello che dice [display-v3.md](display-v3.md).
