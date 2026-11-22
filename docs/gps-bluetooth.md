# GPS Bluetooth su Linux (provato con il Nokia LD-3W)

## In breve: collegamento automatico dall'applicazione (23/11/2026)
Dopo **l'accoppiamento una tantum** (punto 2 qui sotto) l'applicazione si collega da sola, **senza `rfcomm`, senza `sudo` e senza terminali**:
1. Scheda **Prove sul campo**: premi **Aggiorna**; nel menu a tendina del GPS compare **`Bluetooth: Nokia LD-3W (indirizzo)`**.
2. Sceglilo e premi **Collega GPS**. L'app apre il collegamento RFCOMM da sola (prova i canali 1-5) e mostra fix, satelliti e posizione.
3. Spunta **"Collega il GPS all'avvio"**: alla prossima apertura l'app ricorda la scelta e si collega da sola. **"Riconnetti da solo"** (acceso di base) rifà il collegamento se cade o se il GPS si spegne.
4. Con il GPS fermo e NTP raggiungibile premi **"Calibra il ritardo del GPS con NTP"**: l'app misura quanto ritarda la frase NMEA (nel tuo caso circa 377 ms) e lo ricorda; da allora l'ora GPS ha un'incertezza di circa ±0,1 s invece di ±0,4 s, anche senza Internet. Il ritardo vale per **questo GPS e questo tipo di collegamento**: ripeti la calibrazione se cambi apparecchio.

**Come funziona.** Se il Python dell'app ha il supporto Bluetooth (`socket.AF_BLUETOOTH`: il Python di sistema di Ubuntu sì), usa un socket RFCOMM diretto. Altrimenti (per esempio con un Python di conda) lancia un piccolo **ponte** con il Python di sistema (`app/volora_misure/bt_bridge.py`). Se non esiste nessun Python con il Bluetooth, l'app lo dice: lancia l'applicazione con `/usr/bin/python3`. **Non provato col Bluetooth vero**: la logica ha prove con socket e processi finti.

Il resto della pagina descrive la procedura **manuale** (utile per capire cosa succede e per diagnosticare).

Procedura trovata il 22/11/2026 con un **Nokia LD-3W** (ricevitore SiRF del 2006, solo Bluetooth) su un portatile Ubuntu. Vale per qualunque GPS Bluetooth con servizio **Serial Port (SPP)**. Il collegamento passa da una seriale virtuale `/dev/rfcomm0` che l'applicazione legge come una normale porta seriale.

## 1. Controllo dell'adattatore
```bash
rfkill list
```
```bash
bluetoothctl show
```
Devono risultare un adattatore sbloccato (`Soft blocked: no`) e `Powered: yes`. Con **due adattatori** (interno più una chiavetta) tutto si complica: lascia collegato solo quello che vuoi usare (`bluetoothctl list` deve mostrarne uno).

## 2. Accoppiamento (una volta sola)
Con il GPS acceso, carico e vicino, in una sessione `bluetoothctl`:
```
agent on
default-agent
scan on
```
Quando compare il dispositivo (per esempio `Nokia LD-3W`), `scan off`, poi:
```
pair INDIRIZZO
trust INDIRIZZO
```
Se chiede il PIN, la riga è `[agent] Enter PIN code:` e il PIN di questi ricevitori è di solito `0000`. L'errore `org.bluez.Error.AlreadyExists` vuol dire che il dispositivo è già accoppiato: va bene, si passa oltre (`info INDIRIZZO` mostra `Paired: yes`).

## 3. La porta seriale
```bash
sudo rfcomm connect /dev/rfcomm0 INDIRIZZO 1
```
Il canale `1` è quello tipico del servizio seriale. Il comando resta in primo piano e scrive `Connected /dev/rfcomm0 ... on channel 1`: **va lasciato aperto** finché si usa il GPS. Se dà `Connection refused` il canale è un altro; `Host is down` vuol dire che il GPS non risponde (spento, fuori portata o già collegato a un altro apparecchio). `sdptool browse` può tornare **vuoto** anche quando il collegamento funziona: non è un'indicazione di guasto. `hcitool name INDIRIZZO` conferma se il GPS risponde.

In un altro terminale:
```bash
timeout 8 cat /dev/rfcomm0
```
Devono scorrere righe `$GPGGA`, `$GPRMC`, `$GPGSV`.

## 4. Nell'applicazione (procedura manuale)
Scheda **Prove sul campo**, porta `/dev/rfcomm0`, velocità qualsiasi (il Bluetooth la ignora: va bene `9600`), niente PPS, poi **Collega GPS**. Prima chiudi eventuali `cat` aperti. Se compare `No module named 'serial'` l'app è partita fuori dall'ambiente con `pyserial` (vedi [applicazione.md](applicazione.md)).

## 5. Il fix e due difetti dei ricevitori vecchi
- **Fix.** Dopo anni di inattività il ricevitore parte "a freddo": all'aperto, con cielo libero, servono da uno a qualche minuto (a volte una decina). Prima del fix `GPGGA` ha qualità `0` e `GPRMC` ha `V`; la data interna può essere quella di fabbrica (nel nostro caso 29/10/2006).
- **Rollover della settimana GPS.** I ricevitori costruiti prima del 2019 contano le settimane con 10 bit: ogni 1024 settimane (19,6 anni) la data ritorna indietro. Il Nokia LD-3W dava il 22/11/2026 come **08/04/2007**. L'ora del giorno è giusta, la data no. L'applicazione **corregge il rollover** usando l'anno del computer (aggiunge 1024 settimane o multipli, se la data cade entro due giorni da quel multiplo) e **scarta** ogni ora GPS che resta lontana più di due giorni dal computer. Nella riga di stato compare `data GPS corretta (rollover di 1024 settimane)`.

Per capire il difetto della data (e dei secondi intercalari) a fondo: [gps-tempo.md](gps-tempo.md).

## 6. Limiti per le prove
- La **posizione** è affidabile (nel test: 9 satelliti, HDOP 1,0).
- L'**ora** da un GPS Bluetooth ha un ritardo variabile (qualche centinaio di millisecondi o più) e nessun PPS: l'app la considera con un'incertezza di ±0,4 s. Per l'orario di partenza delle prove conviene **NTP** (Internet, anche dal telefono in hotspot) o un GPS con PPS.
