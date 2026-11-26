# Il band plan ARI e il progetto (70 cm, 13 cm, 23 cm)

> **Fonte:** schermate della pagina ari.it/bandplan.html inviate dall'autore il 26/11/2026 (piano attuale, parziale). Per il 13 cm vedi anche [modulo-2g4-uart.md](modulo-2g4-uart.md), punto 9. Il documento ARI Milano del 2004 è superato dove differisce.
>
> **Regola del progetto (21/11/2026, precisata il 23/11/2026):** il band plan **non è un vincolo dello studio**: le modalità si scelgono per prestazioni e robustezza. Questa pagina serve a **scegliere i canali nello spirito radioamatoriale**, cioè dove si disturba meno. Nessun avviso di potenza ([regole-radioamatoriali.md](regole-radioamatoriali.md)).

## 1. Il 70 cm nella schermata (colonne: MHz, larghezza a −6 dB, modo, note)
| MHz | Larghezza | Modo | Note |
|---|---|---|---|
| 430,000-431,975 | 20 kHz | tutti i modi | uscite ripetitori FM 430,025-430,375 (shift 1,6 MHz, passo 12,5 kHz, RU002-RU030); ingressi 431,225-431,600 e 431,625-431,975 |
| 432,000-432,025 | 500 Hz | CW/MGM | finestra EME |
| 432,025-432,100 | 500 Hz | CW/MGM | centro CW 432,050; PSK31 432,088 |
| 432,100-432,400 | 2,7 kHz | CW/SSB/MGM | centro SSB 432,200; appoggio microonde 432,350; chiamata FSK441 432,370 |
| 432,400-432,490 | 500 Hz | CW/MGM | finestra beacon esclusiva |
| 432,491-432,493 | 500 Hz | EMGM | modi digitali sperimentali |
| 432,500-432,975 | 12 kHz | tutti i modi | nuova frequenza APRS 432,500; uscite ripetitori 432,825-433,200 |
| 433,000-433,575 | 12 kHz | FM/Digital Voice | SSTV 433,400; **chiamata Digital Voice 433,450**; **chiamata FM 433,500**; simplex FM 433,400-433,575 (passo 25 kHz) |
| **433,600-434,000** | **20 kHz** | **tutti i modi** | **433,625-433,775 canali per comunicazioni digitali**; FAX 433,700 |
| 435,000-436,000 | 20 kHz | satellite | |
| 436,000-438,000 | 20 kHz | satellite | |
Il piano finisce a 438,000 MHz nella schermata: **434-435 MHz e 438-440 MHz non compaiono** (coerente con quanto trovato in rete: in Italia 430-434 e 435-438 MHz). Il nostro riferimento 430-440 MHz resta quello dello studio; **per le prove in Italia** valgono i segmenti sopra.

Nel 2 m (in alto): 145,794-145,806 MHz comunicazioni spaziali (ISS); 145,806-146,000 finestra esclusiva satellite.

## 2. Dove cadono i nostri canali
- **Voce v2 (433,475 MHz di base):** dentro 433,000-433,575, segmento FM/Digital Voice di 12 kHz, fra la chiamata Digital Voice (433,450) e la chiamata FM (433,500). Non si cambia (la v2 non si modifica).
- **Larghezze nostre contro il piano:** il piano indica **20 kHz come massimo** in ogni segmento; i nostri modi occupano di più: R10 125 kHz, R11 62,5 kHz, R12 31,25 kHz, R13 15,6 kHz, R14 7,8 kHz, R3-R9 da 125 a 500 kHz, FSK da circa 250 a 400 kHz. Solo **R13 e R14** stanno nei 20 kHz. Per decisione dell'autore non è un vincolo, ma conviene **scegliere dove**.
- **Il segmento che meglio ci ospita è 433,600-434,000 MHz** ("tutti i modi", 20 kHz, 400 kHz in tutto), che ha già i **canali per comunicazioni digitali 433,625-433,775 (150 kHz)**. Evita le uscite e gli ingressi dei ripetitori FM (430-432, 432,825-433,200) e i segmenti stretti (CW/SSB/beacon/EME).
- **I satelliti (435-438 MHz)** sono l'altra ampia fascia, ma vanno lasciati liberi.

## 3. Proposte per i canali ancora da definire (profilo 0)
Tutte **da decidere**; in 433,600-434,000 MHz ci stanno al più tre canali da 125 kHz o uno da 250-400 kHz:

| Uso | Larghezza | Proposta di centro | Note |
|---|---|---|---|
| Incontro e beacon (R10, 125 kHz) | 125 kHz | **433,700 MHz** (433,6375-433,7625) | dentro i canali digitali; la frequenza FAX 433,700 è un'attività stretta, da controllare con l'ascolto |
| Canale di servizio del voto (gradino veloce) | 125 kHz | 433,850 MHz (433,7875-433,9125) | R8/R9 (125 kHz): R3-R7 sono più larghi di 125 kHz e non ci stanno |
| Trasferimenti veloci (immagini) | 250-400 kHz | da negoziare, oltre i 434 MHz non c'è segmento | per R3-R7 e FSK serve altro spazio: vedi sotto |

I **modi larghi** (R3-R7, FSK da 150 kHz) **non entrano** nei 400 kHz insieme agli altri canali: per i trasferimenti veloci restano due strade: (a) usare 433,600-434,000 per un solo canale largo alla volta, concordato fra le stazioni, oppure (b) **cambiare banda** (2,4 GHz, profilo 2), che è proprio l'idea del cambio di banda.

## 4. 13 cm e 23 cm
- **13 cm:** tutta la fascia 2400-2450 MHz è "Satellite" nel piano attuale; ATV in 2427-2443 MHz se non c'è traffico satellitare; i segmenti digitali (2355-2365 e 2392-2400 MHz) sono sotto il campo del modulo. Dettagli e canali candidati in [modulo-2g4-uart.md](modulo-2g4-uart.md), punto 9.
- **23 cm (1,296994-1,298 GHz):** uscite ripetitori con shift 6 MHz, simplex FM, chiamata Digital Voice 1,297725, gateway Internet voce 1,297900-1,297975. Possibile banda "più performante" per voce e dati, da studiare.

## 5. Cosa non ho potuto vedere
Le schermate sono parziali: del 70 cm manca il tratto sopra 438 MHz e fra 434 e 435 MHz; del 13 cm il testo tagliato della prima nota; del 23 cm solo la parte finale.
