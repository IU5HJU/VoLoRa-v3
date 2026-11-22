# GPS Bluetooth su Linux (provato con il Nokia LD-3W)

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

## 4. Nell'applicazione
Scheda **Prove sul campo**, porta `/dev/rfcomm0`, velocità qualsiasi (il Bluetooth la ignora: va bene `9600`), niente PPS, poi **Collega GPS**. Prima chiudi eventuali `cat` aperti. Se compare `No module named 'serial'` l'app è partita fuori dall'ambiente con `pyserial` (vedi [applicazione.md](applicazione.md)).

## 5. Il fix e due difetti dei ricevitori vecchi
- **Fix.** Dopo anni di inattività il ricevitore parte "a freddo": all'aperto, con cielo libero, servono da uno a qualche minuto (a volte una decina). Prima del fix `GPGGA` ha qualità `0` e `GPRMC` ha `V`; la data interna può essere quella di fabbrica (nel nostro caso 29/10/2006).
- **Rollover della settimana GPS.** I ricevitori costruiti prima del 2019 contano le settimane con 10 bit: ogni 1024 settimane (19,6 anni) la data ritorna indietro. Il Nokia LD-3W dava il 22/11/2026 come **08/04/2007**. L'ora del giorno è giusta, la data no. L'applicazione **corregge il rollover** usando l'anno del computer (aggiunge 1024 settimane o multipli, se la data cade entro due giorni da quel multiplo) e **scarta** ogni ora GPS che resta lontana più di due giorni dal computer. Nella riga di stato compare `data GPS corretta (rollover di 1024 settimane)`.

Per capire il difetto della data (e dei secondi intercalari) a fondo: [gps-tempo.md](gps-tempo.md).

## 6. Limiti per le prove
- La **posizione** è affidabile (nel test: 9 satelliti, HDOP 1,0).
- L'**ora** da un GPS Bluetooth ha un ritardo variabile (qualche centinaio di millisecondi o più) e nessun PPS: l'app la considera con un'incertezza di ±0,4 s. Per l'orario di partenza delle prove conviene **NTP** (Internet, anche dal telefono in hotspot) o un GPS con PPS.
