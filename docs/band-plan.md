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

## 3. Tabella dei canali del profilo 0 (deciso il 26/11/2026)
> **Valori di partenza, non limiti.** Nel firmware le frequenze di T3 e T-Beam sono liberamente configurabili e quelle del modulo a 2,4 GHz sono configurabili a piacere dentro 2400-2450 MHz ([regole-radioamatoriali.md](regole-radioamatoriali.md)). Il codice in `tools/canali.py` controlla solo il campo del chip e le sovrapposizioni.

Decisioni dell'autore: **canale di incontro 433,700 MHz** (125 kHz) e **canale di servizio del voto a 144,850 MHz in banda 2 m** (corretto il 26/11/2026: prima era 433,850 MHz; il voto è in [voting-isofrequenza.md](voting-isofrequenza.md)). La tabella è in [`tools/canali.py`](../tools/canali.py), provata in `tests/sim/test_canali.py`. Il `canale` del BAND-SET con profilo 0 è l'indice di questa tabella.

| Canale | Frequenza (MHz) | Larghezza max | Gradini ammessi | Uso |
|---|---|---|---|---|
| 0 | 433,700 | 125 kHz | R2, R8-R14 | incontro: beacon, polling, HELLO e trasferimenti stretti |
| 1 | 433,850 | 125 kHz | R2, R8-R14 | trasferimenti stretti con ascolto prima di parlare (era il canale del voto) |
| 2 | 433,955 | 62,5 kHz | R11-R14 | trasferimenti con i gradini stretti |
| 3-15 | — | — | — | riservati (deciso il 26/11/2026): per ogni altro canale si usa la frequenza esplicita (BAND-SET-FREQ) |

- **Tutti e tre i canali stanno nel segmento 433,600-434,000 MHz** (tutti i modi, canali digitali 433,625-433,775) e oltre il segmento FM/Digital Voice della v2 (fino a 433,575 MHz). Guardia minima fra i canali: 11,25 kHz.
- **L'incontro (R10) è sul canale 0**, come deciso: HELLO e beacon sempre lì. I trasferimenti negoziano il canale nell'HELLO (BAND-SET con profilo 0).
- **Cosa entra in 125 kHz:** i gradini con larghezza occupata fino a 125 kHz: FSK R2 (50 kbit/s, 100 kHz di banda occupata, circa 38 kbit/s netti) e LoRa R8-R14. **Il più veloce è R2 in FSK**, poi R8 (circa 1,6 kbit/s netti).
- **Non entrano i gradini larghi:** R0, R1 (FSK 150k e 100k) e R3-R7 (LoRa 250-500 kHz) non hanno un canale nel segmento. Per i trasferimenti veloci restano il **cambio di banda a 2,4 GHz (profilo 2)** o un accordo temporaneo fra le stazioni per usare tutto il segmento (non nella tabella).
- **Il canale 1 non ospita più il voto**: il voto è a 144,850 MHz (2 m). In 70 cm il canale 1 è un secondo canale da 125 kHz per i trasferimenti stretti.
- **Il canale di servizio a 2 m, 144,850 MHz,** non è nelle schermate del piano che ho visto (compare solo 145,794-146,000 MHz): **da controllare sul piano dei 2 m**. La **terza armonica** (434,550 MHz) cade in 70 cm a circa 0,6 MHz dal canale 2: filtro passa-basso sulla radio a 2 m.
- **A 433,700 MHz il piano indica la frequenza FAX** (attività stretta): ascolto prima di trasmettere.

## 4. 13 cm e 23 cm
- **13 cm:** tutta la fascia 2400-2450 MHz è "Satellite" nel piano attuale; ATV in 2427-2443 MHz se non c'è traffico satellitare; i segmenti digitali (2355-2365 e 2392-2400 MHz) sono sotto il campo del modulo. Dettagli e canali candidati in [modulo-2g4-uart.md](modulo-2g4-uart.md), punto 9.
- **23 cm (1,296994-1,298 GHz):** uscite ripetitori con shift 6 MHz, simplex FM, chiamata Digital Voice 1,297725, gateway Internet voce 1,297900-1,297975. Possibile banda "più performante" per voce e dati, da studiare.

## 5. Cosa non ho potuto vedere
Le schermate sono parziali: del 70 cm manca il tratto sopra 438 MHz e fra 434 e 435 MHz; del 13 cm il testo tagliato della prima nota; del 23 cm solo la parte finale.
