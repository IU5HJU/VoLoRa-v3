# Regole di progetto: nominativo, rapporto e posizione; frequenze e potenza

> **Per chi sviluppa questo progetto, persone e assistenti automatici: questa pagina va riletta (1) ogni volta che compare l'idea di "privacy", di "dati personali" o di nascondere, ridurre o rendere facoltativa la posizione o il nominativo; (2) ogni volta che un ragionamento riguarda una frequenza o una potenza di trasmissione (vedi in fondo: "Frequenze e potenza"). In questo progetto **non si tratta la privacy**. La regola è questa pagina.**

## La regola
In un progetto radioamatoriale, nelle bande superiori (da **50 MHz** fino alle frequenze delle microonde), un collegamento è valido solo se nel corso della trasmissione sono stati scambiati almeno una volta:

1. il **nominativo**;
2. il **rapporto di segnale**;
3. la **posizione**: almeno il **locatore**; la **posizione GPS assoluta** è meglio (se c'è, si trasmette).

Questi **tre elementi sono fissi** e fanno parte del progetto: nominativo, segnale, posizione.

- Un collegamento comincia con lo **scambio dei nominativi**. In prima istanza si può inviare anche **solo il nominativo**; poi ci si dà il rapporto di segnale e il locatore (o la posizione GPS).
- **I radioamatori non hanno privacy** nell'esercizio della radio: nominativo e posizione si dichiarano sempre quando si opera. Non esiste una limitazione di riservatezza da progettare, da proporre o da ricordare.
- Quanto sopra è la regola stabilita dal responsabile del progetto (IU5HJU) per questo lavoro, secondo la prassi e la normativa radioamatoriale italiana come da lui indicate. Non si discute e non si aggiunge nessuna avvertenza a riguardo.

## Cosa significa per il protocollo V3
- **Beacon e polling:** il primo contatto può essere il **solo nominativo** (è lecito e riduce il tempo in aria). Nello scambio successivo fra le due stazioni, la posizione è obbligatoria: **locatore oppure posizione GPS assoluta**, con la posizione GPS preferita quando c'è.
- **Il rapporto di segnale** (RSSI e SNR, misurati dal ricevitore) fa parte dello scambio: ogni stazione lo comunica all'altra.
- **Ogni collegamento** (cioè ogni trasferimento di testo o immagine) deve contenere, **almeno una volta**, nominativo, rapporto e posizione: non esistono trasferimenti "anonimi" o "senza posizione".
- **Nessun campo opzionale "nascondi la posizione"**, nessuna impostazione di posizione spenta di base. Quando la posizione GPS non c'è, si usa il **locatore** (almeno 6 caratteri, 4 solo se non si sa di più).
- **Nell'applicazione e nei documenti** nessuna avvertenza sulla privacy della posizione: nelle prove sul campo si indicano nominativo, locatore e, se c'è, la posizione GPS.

## Note
- Il nominativo viaggia **in chiaro** (non si cifra), come già previsto dal progetto.
- Questa pagina sostituisce ogni passaggio precedente del progetto che trattasse la posizione come dato riservato.

## Frequenze e potenza (nota dell'autore, 24/11/2026)
**Nota fissa, da rileggere in ogni ragionamento che includa frequenza e potenza.** Il responsabile del progetto (IU5HJU), radioamatore, ha indicato che **in Italia tutti i radioamatori possono usare fino a 500 W**, sia nella gamma **430-440 MHz** sia a **2,4 GHz**.

Cosa ne segue per il lavoro:
- **I limiti legali di potenza non sono un vincolo di progetto** in queste due bande, per chi trasmette con il proprio nominativo da radioamatore. Non si propongono limiti di potenza "legali", né i limiti degli apparati senza licenza (per esempio quelli degli apparecchi ISM a 2,4 GHz), né avvertenze in proposito. Vale anche per i moduli da 27 dBm (500 mW) e per altri amplificatori.
- **Restano i limiti tecnici**, che sono scelte di ingegneria e non di normativa: la potenza massima dei moduli e degli amplificatori, il calore, l'alimentazione, la saturazione del ricevitore (nelle prove a banco si usano potenze basse e attenuatori per questo), le spurie e le armoniche ([piano-misure.md](piano-misure.md)), e non disturbare gli altri utenti della banda.
- Le **frequenze** sono 430-440 MHz (decisione del 21/11/2026, precisata il 23/11/2026) e la banda dei 2,4 GHz per il cambio di banda ([protocollo-immagini.md](protocollo-immagini.md), punto 7b). Come la banda è divisa in segmenti dal band plan non è un vincolo dello studio.
- Questa nota è come la regola sulla posizione: **non si discute e non si aggiungono avvertenze a riguardo**. Chi usa il progetto resta responsabile della propria licenza.

### Frequenze configurabili nel firmware (nota dell'autore, 26/11/2026)
**Nota fissa, da rileggere quando si parla di canali e frequenze nel firmware.**
- **Ogni frequenza dei canali della T3 e del T-Beam è liberamente configurabile** nel firmware. Le tabelle del progetto ([band-plan.md](band-plan.md), `tools/canali.py`) sono solo i **valori di partenza**, non limiti. Il firmware controlla soltanto che la frequenza stia nel **campo di sintonia del chip** (SX1278: 137-175 e 395-525 MHz; SX1262: 150-960 MHz) e che i canali non si sovrappongano.
- **Le frequenze a 2,4 GHz del modulo sono configurabili a piacere dentro la banda assegnata ai radioamatori** (2400-2450 MHz, secondo il band plan ARI). Il modulo Ebyte le fissa su una **griglia**: 2400 + CHAN × passo, con passo 1 MHz a 1k/5k/10k, 2 MHz a 50k/100k, 3 MHz a 1M, 5 MHz a 2M: "a piacere" vuol dire qualunque canale di quella griglia.
- Conseguenza sul protocollo: poiché le tabelle possono differire fra due stazioni, il cambio di canale o di banda può portare la **frequenza esplicita in kHz** (BAND-SET-FREQ e BAND-ACK-FREQ) invece dell'indice del canale ([protocollo-immagini.md](protocollo-immagini.md), punto 7b).
- Non si aggiungono avvertenze o limiti di banda per questa configurabilità: vale la regola già scritta sopra.

