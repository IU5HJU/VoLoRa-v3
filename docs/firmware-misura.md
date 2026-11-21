# Firmware di misura (fase 1)

**Non è il firmware V3.** È un piccolo firmware per misurare le radio: sensibilità, tempo in aria, perdite e deriva di frequenza di ogni modo LoRa e FSK ([piano-misure.md](piano-misure.md)). Sta in [`firmware/misura/`](../firmware/misura) e si pilota dal PC con [`tools/misura.py`](../tools/misura.py).

## Stato (21/11/2026): scritto, non ancora provato su una scheda
- La **logica** (comandi, tempo in aria, pacchetto di prova, statistiche) gira anche sul PC: `cd firmware/misura && make test` (tutte le prove passate).
- Il firmware **passa il controllo di sintassi** contro le intestazioni vere di RadioLib (7.8.1, quelle del repository LilyGO) per T3/SX1278 e T-Beam/SX1262, con uno stub minimo di Arduino. **Non è stato compilato con PlatformIO** (da questa sessione il download della piattaforma ESP32 è bloccato) né caricato su una scheda: il primo `pio run` e la prima prova sulle schede possono rivelare errori. Il `platformio.ini` fissa RadioLib 7.5.0 e la piattaforma 6.10.0 della v2, per confrontare i risultati.
- `tools/misura.py` è provato solo con `--simulate` (schede finte che seguono una curva attorno alla sensibilità stimata: prova la sequenza, non la fisica). Il collegamento seriale vero **non è provato**.

## Schede e pin
Pin delle radio ripresi dalla v2 (`src/board_pins_*.h`): SCK 5, MISO 19, MOSI 27, CS 18, DIO0 26, RST 23, DIO1 33, DIO2/BUSY 32. SX1262: TCXO sul DIO3 a 1,6 V come nella v2 (`-DMISURA_TCXO_V=0` se la radio non parte). La microSD e l'audio non sono usati.

```
pio run -e t3 -t upload          # T3 V1.6.1 (SX1278): togliere la microSD, antenna o carico collegati prima dell'USB
pio run -e tbeam1262 -t upload   # T-Beam V1.2 con SX1262
```
Seriale a **921600 baud**, una riga per comando. La parola di sincronismo LoRa è 0x5D, diversa da quella della v2, per non disturbare stazioni v2 vicine.

## Comandi
| Comando | Cosa fa |
|---|---|
| `CALL <nominativo>` | **obbligatorio prima di trasmettere** (3-8 lettere o cifre); va nel pacchetto |
| `MODE LORA <bw kHz> <sf> <cr 5-8>` | per esempio `MODE LORA 250 7 5` |
| `MODE FSK <kbit/s> <dev kHz> <rxbw kHz> [shape 0\|3\|5\|10]` | l'`rxbw` deve essere una banda ammessa dalla radio: **SX1278 fino a 250 kHz, SX1262 fino a 467 kHz** (RadioLib) |
| `FREQ <MHz>` | solo 430-440 MHz |
| `POWER <dBm>` | da -9 a 22 (la radio rifiuta ciò che non può fare) |
| `PAYLOAD <26-255>` | byte del pacchetto di prova |
| `PREAMBLE <n>` | simboli LoRa o byte FSK |
| `TX <n> <intervallo ms> [seq iniziale]` | manda n pacchetti; per ognuno stampa `TX seq=.. toa_us=.. calc_us=..` (tempo misurato dall'avvio al fine trasmissione, contro la formula) e alla fine `TXSUM` |
| `RX <secondi>` | ascolta; per ogni pacchetto `RX seq rssi snr fei status bit_err`; alla fine `RXSUM ok bad lost dup bit_err rssi snr fei_hz` |
| `CW <secondi 1-30>` | portante per il misuratore di potenza: pacchetti FSK tutti 0xFF a 4,8 kbit/s uno dopo l'altro (metodo della v2 per il Morse), 99 % del tempo trasmessi; la portante sta alla frequenza più 1 kHz |
| `VERBOSE 0\|1`, `SHOW`, `INFO`, `HELP` | |
| un tasto qualsiasi | ferma TX, RX o CW |

Il pacchetto di prova: intestazione `V3M1`, numero di sequenza, lunghezza, nominativo, riempimento pseudocasuale deterministico (dal numero di sequenza) e CRC32. Il ricevitore conta così i pacchetti buoni, i **bit sbagliati** (anche dei pacchetti rovinati) e i persi dai buchi nella sequenza. Il `fei_hz` (errore di frequenza misurato dal chip, solo LoRa) serve alla misura della deriva del quarzo (M6) senza bisogno di sapere se la scheda ha il TCXO.

## Il pilota dal PC
```
python3 tools/misura.py scala --tx /dev/ttyUSB0 --rx /dev/ttyUSB1 --call IU5HJU --modes L4,L5,F3 --count 200 --out risultati.csv
python3 tools/misura.py analizza risultati.csv
python3 tools/misura.py scala --simulate --modes L4 --att 100,110,120 --out prova.csv   # senza schede
```
Per ogni modo chiede l'attenuazione totale (quella **misurata** col NanoVNA), configura le due schede, manda i pacchetti e scrive una riga di CSV con potenza ricevuta calcolata, perdite, RSSI, SNR, deriva e tempi. `analizza` dà per ogni modo la sensibilità (potenza ricevuta più bassa con perdita ≤ 10 %) e la differenza dalla stima di [scala-modi.md](scala-modi.md). Serve `pip install pyserial`.

## Limiti da conoscere prima di misurare
1. **Attenuazione disponibile.** Con attenuatori da 0 a 40 dB e un trasmettitore a +2 dBm (T3, minimo ragionevole) si arriva a -38 dBm: per i gradini sensibili (da -114 a -149 dBm) servono **100-140 dB** di attenuazione totale. Una catena di attenuatori fissi aggiuntivi (20-30 dB, SMA) si può comporre, ma sopra circa **100 dB** l'isolamento delle scatole diventa il limite: oltre non si misura più la sensibilità ma la perdita per accoppiamento. Per la misura dei gradini L8-L13 servirà un altro metodo (percorso lungo in aria con il calcolo del collegamento, o più avanti il laboratorio).
2. **Misuratore di potenza da 1 mW (0 dBm):** si tara l'uscita a +2 dBm e oltre; sotto lo 0 dBm la potenza si ricava dalla perdita **misurata** della catena di attenuatori.
3. **RxBw in FSK:** l'SX1278 arriva a **250 kHz** di banda di ricezione, l'SX1262 a 467 kHz. L'FSK a 300 kbit/s con deviazione di 100 kHz (banda necessaria circa 500 kHz) non entra: va provato con banda e deviazione più strette o solo sull'SX1262.
4. **Pacchetti FSK da più di 64 byte sull'SX1278:** il comando `TX` stampa il codice di errore della radio. È la misura M5 (limite del FIFO). La v2 trasmette fino a 255 byte in FSK con la portante del Morse; resta da verificare per la ricezione.
5. La **deriva con il caldo e il freddo** va annotata a mano (il firmware non legge la temperatura).
