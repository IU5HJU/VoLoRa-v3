# Punti aperti

1. **Hardware:** solo le schede attuali (SX1278, SX1262) o anche altre radio, per esempio SX1280 a 2,4 GHz per le alte velocità?
2. ~~**Banda e norme**~~ **Deciso il 21/11/2026:** nessun limite di larghezza di banda e nessun vincolo di band plan dentro **430-440 MHz**. Le modalità si scelgono solo per prestazioni e robustezza. Restano da verificare le radio e le schede (punto 7).
3. **Immagini via ripetitore e reflector:** sì o no?
4. **Correzione d'errore o conferme selettive**, o entrambe: si decide dopo le misure della fase 1.
5. **Formato dell'immagine:** quale codifica a livelli gira sull'ESP32.
6. ~~**Tag del submodule**~~ **Fatto il 21/11/2026:** il submodule è fissato al tag `v0.1.0-rc.1` di VoLoRa (commit `0efa2a3`). Da spostare sul tag della stabile quando esisterà.
7. **Schede sui 430-440 MHz:** le schede 433 MHz hanno filtri e antenne tarati su 433: misurare quanto rendono sugli estremi della gamma (430 e 440 MHz) e con FSK a banda larga. Il campo di sintonia dei chip (SX1278 e SX1262) va confrontato con i datasheet.
8. **Convivenza:** senza vincoli di band plan, scegliere comunque come non disturbare chi è già sulla stessa frequenza (ascolto prima di trasmettere, identificazione).
9. **Datasheet Semtech:** [radio-limiti.md](radio-limiti.md) usa fonti secondarie (RadioLib e tabelle LilyGO). Da confermare sui datasheet originali prima di fissare l'architettura.
10. **MicroSD della T3:** usarla (opzionale) nel nodo immagini; verificare caricamento del firmware con la scheda inserita, corrente, disturbi alla ricezione e comportamento senza scheda. Vedi [scheda-sd.md](scheda-sd.md).
