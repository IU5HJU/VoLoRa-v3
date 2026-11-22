# Il tempo del GPS: settimane, rollover e secondi intercalari

Pagina didattica nata da un caso vero: il **22/11/2026** un GPS Bluetooth **Nokia LD-3W** (ricevitore del 2006) dava la data **08/04/2007**, ma con l'ora del giorno giusta. Capire perché serve a non fidarsi ciecamente di un orologio, soprattutto in un progetto che sincronizza prove radio su orari concordati (vedi [applicazione.md](applicazione.md) e [gps-bluetooth.md](gps-bluetooth.md)).

> **Cosa è calcolato e cosa è ipotesi.** Le date, i numeri di settimana e i rollover sono **calcolati** con [`tools/gps_settimana.py`](../tools/gps_settimana.py). Il fatto che il riferimento interno del Nokia sia il 29/10/2006 è un'**ipotesi coerente con tutti i numeri**, ma non l'ho verificata sul firmware del ricevitore. I valori storici dei secondi intercalari sono quelli noti (14 s nel 2006, 18 s dal 2017).

## 1. Come il GPS dice la data
Il GPS **non usa un calendario**. Conta il tempo dal **6 gennaio 1980** (una domenica) come:

- **numero di settimana**: quante settimane intere sono passate dall'origine;
- **secondi nella settimana**: da 0 a 604 800 (7 × 86 400), poi si ricomincia.

I satelliti trasmettono questi due numeri. L'anno, il mese e il giorno li calcola il ricevitore.

## 2. Il problema: 10 bit
Nel messaggio di navigazione tradizionale il **numero di settimana ha solo 10 bit**: può valere da 0 a 1023. Dopo **1024 settimane** (= 7168 giorni, **19,6 anni**) il contatore ricomincia da zero, e dal segnale solo non si può sapere *a quale giro* si è.

Il ricevitore deve decidere da solo. Nel firmware ha una **data di riferimento** (il *pivot*) e assume che la data vera cada nelle **1024 settimane successive**. Finché la data vera sta dentro quella finestra, tutto è giusto. Appena la supera, la data **salta indietro di 1024 settimane**.

## 3. I numeri del caso Nokia LD-3W

| | Data | Giorno | Settimana GPS | Trasmessa (mod 1024) |
|---|---|---|---|---|
| Data vera | 22/11/2026 | domenica | 2446 | **398** |
| Data mostrata | 08/04/2007 | domenica | 1422 | **398** |

- Il satellite trasmette **398** in entrambi i casi. Il ricevitore ha scelto il giro sbagliato.
- La **data a freddo** che il Nokia mostrava prima del fix era il **29/10/2006**: verosimilmente il riferimento scritto in fabbrica (settimana 1399, trasmessa 375).
- Da quel riferimento, la finestra di 1024 settimane **finisce il 14/06/2026** (calcolato). Fino a quella data il Nokia dava la data giusta. Dal 14 giugno 2026 sbaglia di 1024 settimane. 22/11/2026 meno 1024 settimane è esattamente l'**08/04/2007**, che è dentro la finestra: coerente.

### Perché l'ora del giorno era giusta
I **secondi nella settimana** e il **giorno della settimana** non dipendono dal giro. 1024 settimane sono un multiplo esatto di 7 giorni: il 08/04/2007 era una domenica come il 22/11/2026. Ecco perché l'ora coincideva con quella del computer e **solo l'anno** era sbagliato.

## 4. I rollover nella storia
| Rollover | Data (calcolata) |
|---|---|
| Primo | 22/08/1999 |
| Secondo | **07/04/2019** |
| Terzo | **21/11/2038** (20/11 in UTC, perché il tempo GPS è avanti di 18 s) |

Il secondo ha messo in difficoltà alcuni apparecchi con firmware vecchio. I segnali più recenti (CNAV) usano **13 bit** per la settimana: 8192 settimane, cioè fino al 2137.

## 5. Un secondo problema: i secondi intercalari
Il **tempo GPS non ha secondi intercalari**: dal 1980 è rimasto uniforme. L'**UTC** invece ne ha ricevuti. Oggi il tempo GPS è **avanti di 18 secondi** rispetto all'UTC.

| Dal | GPS − UTC |
|---|---|
| 01/01/2006 | 14 s |
| 01/01/2009 | 15 s |
| 01/07/2012 | 16 s |
| 01/07/2015 | 17 s |
| 01/01/2017 | 18 s |

Il ricevitore converte in UTC con un parametro trasmesso dal satellite. Quel parametro arriva **solo dopo un ascolto lungo**: da avvio a freddo il ricevitore può metterci fino a circa **12,5 minuti**. Prima di riceverlo usa un valore di default del suo firmware, che per un ricevitore del 2006 potrebbe essere **14 s**. In quel caso l'ora dichiarata UTC sarebbe sbagliata di **4 s**, anche con la data giusta. È un'ipotesi da verificare sul tuo ricevitore.

## 6. Come l'applicazione si difende
- **Corregge il rollover.** Usa la data del **computer** come nuovo riferimento: se la data GPS è indietro di un numero intero di 1024 settimane (con la tolleranza di due giorni), aggiunge i cicli mancanti. È lo stesso lavoro che fa il ricevitore, con un riferimento più recente. La riga di stato mostra "data GPS corretta (rollover di 1024 settimane)".
- **Scarta le ore impossibili.** Un'ora GPS che resta lontana più di due giorni dal computer, dopo la correzione, non entra nell'orologio.
- **Lo mette in dubbio.** L'ora GPS da NMEA ha comunque un'incertezza dichiarata di ±0,4 s (ritardo del ricevitore), e un GPS Bluetooth ne ha di più. Per l'orario di partenza è meglio NTP.
- **Mostra la differenza GPS−NTP**, che serve a diagnosticare:

| Differenza GPS − NTP | Probabile significato |
|---|---|
| poche centinaia di millisecondi | ritardo normale del ricevitore e del Bluetooth |
| un numero **intero** di secondi (per esempio 4 o 18) | secondi intercalari non applicati dal ricevitore |
| enorme (anni, mesi) | rollover non corretto o data non valida |
| grande e non intera | altro: da studiare |

## 7. Per fare i conti da solo
```bash
python3 tools/gps_settimana.py 2026-11-22
```
```bash
python3 tools/gps_settimana.py --correggi 2007-04-08 --riferimento 2026-11-22
```
Oppure a mano:
```python
import datetime as d
origine = d.date(1980, 1, 6)
x = d.date(2026, 11, 22)
n = (x - origine).days // 7
print(n, n % 1024)            # 2446 398
print(x - d.timedelta(weeks=1024))   # 2007-04-08
```

### Esercizi
1. Calcola la settimana GPS della tua data di nascita e il suo valore a 10 bit. Cade prima o dopo il rollover del 1999?
2. Un ricevitore ha come riferimento il 06/04/2019. Fino a che data dà la data giusta? E che data mostra se quella vera è il 15/12/2038? *(Risposta: fino al 20/11/2038; il 15/12/2038 mostra il 01/05/2019. Verificalo con lo script.)*
3. Perché una data sbagliata di 1000 settimane (non 1024) non può essere corretta dal metodo dell'app?

## 8. Glossario
- **Tempo GPS**: scala di tempo continua dal 06/01/1980, senza secondi intercalari.
- **Rollover (della settimana)**: ritorno a zero del contatore di settimana a 10 bit ogni 1024 settimane.
- **Pivot**: data di riferimento nel firmware per scegliere il giro giusto.
- **NMEA**: formato testuale delle frasi dei ricevitori (`$GPRMC`, `$GPGGA`...).
- **PPS**: impulso al secondo con cui alcuni ricevitori segnano l'inizio esatto del secondo (pochi nanosecondi).
- **Secondo intercalare**: secondo aggiunto all'UTC per tenerlo vicino alla rotazione della Terra.

## 9. Per approfondire
- Il documento di riferimento dell'interfaccia del segnale GPS (**IS-GPS-200**), che descrive il messaggio di navigazione e il numero di settimana a 10 bit.
- La specifica **NMEA 0183** per le frasi `RMC`, `GGA` e `ZDA`.
