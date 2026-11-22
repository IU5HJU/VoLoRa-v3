# Guida per chi collabora alle misure

Benvenuto. Questo documento dice come provare il firmware di misura, come eseguire le misure e come mandare i risultati. Il progetto è uno **studio**: il firmware di misura non è il V3 ed è **scritto ma ancora non provato su schede**, quindi può avere errori. Segnalali.

> **Regole ferme:**
> - **Antenna o carico da 50 Ω collegati prima di alimentare o di caricare il firmware.** Mai trasmettere senza.
> - Trasmetti **solo con il tuo nominativo** e con le potenze e le frequenze consentite dalla tua licenza. Il progetto lavora fra 430 e 440 MHz, ma **il limite della tua licenza resta tuo**.
> - Il nominativo viaggia in chiaro nei pacchetti e i contenuti non sono cifrati.
> - Togli la **microSD** dalla T3 quando carichi il firmware.

## 1. Cosa serve
Le schede e gli strumenti sono in [materiale.md](materiale.md). Per cominciare bastano **due schede dello stesso tipo** (due T3, oppure due T-Beam con SX1262), due antenne o carichi da 50 Ω, un PC e cavi USB.

## 2. Preparare il PC
1. Installa PlatformIO (estensione di VS Code o `pip install platformio`).
2. Clona il repository e scarica il submodule della v2 (non serve per la misura ma il repository lo richiede):
   ```bash
   git clone --recurse-submodules https://github.com/IU5HJU/VoLoRa-v3
   cd VoLoRa-v3/firmware/misura
   ```
3. Controlla la logica sul PC (serve solo `g++`):
   ```bash
   make test
   ```
   Deve stampare `misura_core: tutte le prove passate`.

## 3. Caricare il firmware
**Dal browser (il modo più semplice, senza PlatformIO):** quando la pagina è pubblicata, apri la [pagina di installazione](https://iu5hju.github.io/VoLoRa-v3/) con Chrome, Edge od Opera, collega la scheda, scegli la scheda e premi "Installa il firmware". *(La pagina esiste solo dopo il primo giro riuscito del workflow su GitHub e dopo aver attivato Pages: Settings, Pages, Source: GitHub Actions. Finché non c'è, usa i comandi qui sotto.)*

**Da riga di comando:**
Con l'**antenna collegata** e la **microSD tolta**:
```bash
pio run -e t3 -t upload          # LoRa32 T3 V1.6.1
pio run -e tbeam1262 -t upload   # T-Beam V1.2 con SX1262
```
Se la compilazione dà errori, **non provare a correggerli da solo senza dirlo**: apri una segnalazione (vedi il punto 7) con il testo completo dell'errore, la scheda e il sistema operativo. Se la radio SX1262 non parte, riprova aggiungendo `-DMISURA_TCXO_V=0` ai `build_flags` dell'ambiente.

## 4. Prima prova: le due schede si sentono?
*(Più comodo: l'[applicazione con interfaccia grafica](applicazione.md), `python3 app`, fa le stesse cose con due monitor e tasti rapidi. Qui sotto il metodo a mano.)*

Apri la seriale a **921600 baud** sulle due schede (`pio device monitor -p PORTA`). Sulla prima:
```
CALL IL_TUO_NOMINATIVO
MODE LORA 250 7 5
RX 60
```
Sulla seconda (entro 60 s):
```
CALL IL_TUO_NOMINATIVO
MODE LORA 250 7 5
TX 20 500
```
Sulla prima devono comparire le righe `RX seq=...` e alla fine `RXSUM ok=20 ...`. Se `ok=0`, controlla frequenza, modo, antenne e che le due schede abbiano lo stesso firmware. Tutti i comandi sono in [firmware-misura.md](firmware-misura.md) (o `HELP`).

## 5. Le misure
> **Prove a distanza con una scheda ciascuno:** vedi la scheda "Prove sul campo" dell'applicazione ([applicazione.md](applicazione.md)): sincronizza l'orologio con NTP o GPS, programma la prova a un orario UTC concordato e scambia con il collega la riga dei risultati.


- **A banco (via cavo, nelle scatole):** segui [piano-misure.md](piano-misure.md) (sezioni 2, 2b, 2c e 3), per esempio:
  ```bash
  python3 tools/misura.py scala --tx /dev/ttyUSB0 --rx /dev/ttyUSB1 --call IL_TUO_NOMINATIVO --modes L4,L5,L7 --count 200 --out risultati.csv
  python3 tools/misura.py analizza risultati.csv
  ```
  Lo script chiede ogni volta l'attenuazione totale **misurata con il NanoVNA** (non quella scritta sull'etichetta). Serve `pip install pyserial`.
- **Sul campo (a distanza reale):** segui [prove-sul-campo.md](prove-sul-campo.md) e compila la scheda di rilievo.

## 6. Mandare i risultati
Per ogni misura servono: **data, scheda e versione del firmware** (`INFO`), **file CSV**, la scheda di rilievo ([prove-sul-campo.md](prove-sul-campo.md)), eventuali foto del montaggio o dello schermo, e una riga di **cosa non ha funzionato**. Due modi:
1. **Apri una segnalazione (Issue)** nel repository con il titolo "Misure - tuo nominativo - data" e allega i file.
2. **Proponi una modifica (fork e pull request):** metti il CSV e una pagina di note in `docs/misure/` con il nome `AAAA-MM-GG-nominativo-scheda.csv` (e `.md`). Prima esegui `make test` in `firmware/misura`.

**Privacy:** la posizione esatta di casa è un dato personale. Nelle prove sul campo basta il **locatore a 6 caratteri** (per esempio `JN53ab`) o la distanza fra le due stazioni; le coordinate precise le pubblichi solo se vuoi.

## 7. Se qualcosa non va
Apri una segnalazione con: scheda, firmware (`INFO`), comando dato, testo completo di ciò che compare sulla seriale e cosa ti aspettavi. Un errore chiaro vale più di mille ipotesi.

## 8. Licenza
Il progetto è software libero (GPL-3). Mandando il tuo lavoro accetti che sia distribuito con la stessa licenza.
