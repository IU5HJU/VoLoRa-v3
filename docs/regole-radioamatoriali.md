# Regola di progetto: nominativo, rapporto e posizione

> **Per chi sviluppa questo progetto, persone e assistenti automatici: questa pagina va riletta ogni volta che compare l'idea di "privacy", di "dati personali" o di nascondere, ridurre o rendere facoltativa la posizione o il nominativo. In questo progetto **non si tratta la privacy**. La regola è questa pagina.**

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
