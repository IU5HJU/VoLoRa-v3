# Prove in laboratorio con due schede V3 (procedura)

**Regola di partenza (27/11/2026):** per le prove la **pagina del telefono sta nella scheda** e non serve Internet ("Internet non è affidabile"). Le due schede e un telefono bastano.

## Stato delle prove (cosa è provato su schede vere)
- **27/11/2026, due schede T3, pagina da Internet via Bluetooth:** un **testo** inviato dal telefono parte via radio e **arriva sul secondo telefono** correttamente (prima prova V3 su schede vere; segnalata dall'autore, senza registro).
- **Immagine dalla galleria: l'invio fallisce** (stesso giorno). Motivo **sconosciuto**: mancava il registro. Dopo questa data la scheda dice il motivo (riepilogo `E_DIAG`, vedi sotto): al prossimo tentativo mandami il registro.
- Tutto il resto (GPS, BOOST/IOF, display, frequenza, Wi-Fi della scheda) è provato **solo sul PC**.

## Cosa serve
- Due schede uguali con il firmware **`mobile_t3`** (T3) o **`mobile_tbeam1262`** (T-Beam), caricate dalla [pagina di installazione](../site/firmware-v3.html) (gruppo "Mobile Wi-Fi"). Due telefoni, oppure uno solo che si ricollega all'altra scheda.
- Antenna a 433 MHz **o** un attenuatore da 30-40 dB fra i connettori (con le schede vicine il ricevitore si satura: vedi [piano-misure.md](piano-misure.md)). Mai senza carico.
- Un computer con un monitor seriale a 115200 baud, solo per leggere il registro.

## Preparazione (una volta)
1. Su ogni scheda, sulla seriale: `CALL IU5HJU` (e `CALL IZ5FSN` sull'altra). La scheda si riavvia e il Wi-Fi prende il nome `VoLoRa-<NOMINATIVO>`.
2. `FREQ` su tutte e due: devono dire la stessa frequenza (di partenza 433,700 MHz).
3. `WIFI` mostra rete, **password a 8 cifre** (anche sul display) e indirizzo `http://192.168.4.1`.
4. `LOG CLEAR` per partire da un registro pulito.

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
