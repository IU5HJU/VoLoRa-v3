# Materiale per le misure

Lista da condividere tra i radioamatori che partecipano alle prove. Il progetto è uno studio e il firmware di misura **non è ancora provato su schede** ([firmware-misura.md](firmware-misura.md)): conviene che una persona lo provi per prima a banco, prima di distribuire il resto.

## 1. Banco di misura (via cavo)

| Materiale | Quantità | Note |
|---|---|---|
| Schede **LILYGO LoRa32 T3 V1.6.1** (SX1278) | 2 | T3 senza microfono e altoparlante collegati, microSD tolta |
| Schede **T-Beam V1.2 con modulo SX1262** | 2 | per SF5, confronto con SX1278 e FSK a banda più larga |
| Una T3 con **TCXO** (opzionale) | 1 | per il confronto della deriva; la deriva si misura comunque (`fei_hz`) |
| Attenuatori **SMA fissi**, DC-3 GHz, 2 W: 3, 6, 10, 20, 30 dB | 2-3 per valore | catena da comporre; vedi il limite di circa 100 dB sotto |
| Carichi da **50 Ω SMA** | almeno 4 | per chiudere le porte inutilizzate e per la prova di tenuta |
| **Cavi SMA** corti (20-50 cm) | almeno 6 | tutti dello stesso tipo, di buona qualità |
| **Adattatori SMA da pannello** (passanti) | 4 | uno per lato di ogni scatola |
| **Scatole metalliche** con coperchio a contatto continuo | 2 | una per scheda |
| **Ferriti** per cavi USB | 2-4 | cavo USB = via di fuga del segnale |
| Batterie o power bank | 2 | per tenere l'alimentazione fuori dal campo |
| Nastro di alluminio o guarnizione conduttiva | 1 | per chiudere le fessure delle scatole |

## 2. Strumenti

| Strumento | Uso | Chi lo ha (da compilare) |
|---|---|---|
| Misuratore di potenza 0-1,3 GHz, minimo 1 mW (0 dBm) | taratura dell'uscita a +2 dBm e oltre | disponibile |
| **NanoVNA V3** | perdita (S21) di cavi e attenuatori a 430, 433,5 e 440 MHz; ROS delle antenne | disponibile |
| Oscilloscopio | tempi dai pin DIO, SPI, corrente | disponibile |
| Multimetro | corrente e alimentazione | disponibile |
| Chiavetta SDR (NESDR) | verifica di frequenza e struttura dei pacchetti | disponibile |
| Analizzatore di spettro | banda occupata, spurie, deviazione | **non disponibile**: una visita breve in laboratorio più avanti |

## 3. Per le prove sul campo
- Schede cariche con il firmware di misura già caricato, **antenna a 433 MHz** collegata, nominativo del proprietario.
- Un PC portatile con `pyserial` e lo script [`tools/misura.py`](../tools/misura.py), oppure un terminale seriale a 921600 baud.
- **GPS** (anche quello del telefono) per le posizioni, **metro** o telemetro per le altezze.
- Attenuatori fissi da 10, 20 e 30 dB da inserire in serie all'antenna (idea da verificare, vedi [prove-sul-campo.md](prove-sul-campo.md)).
- Una **antenna di riferimento** uguale per tutti, per quanto possibile, e una coppia di cavi corti.

## 4. Il limite dei 100 dB
Con un trasmettitore a +2 dBm e una catena di attenuatori fissi si arriva a circa -100 dBm di potenza ricevuta senza problemi. Per i modi più sensibili (da circa -114 a -149 dBm) servirebbero 100-140 dB: sopra circa 100 dB l'isolamento delle scatole è il limite, e **comprare altri attenuatori non basta**. Quei modi si misurano con le prove sul campo o in laboratorio, non a banco.

## 5. Chi porta cosa (da compilare)
| Voce | Chi | Prestato fino al |
|---|---|---|
| | | |
