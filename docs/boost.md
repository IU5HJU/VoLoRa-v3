# Modalità BOOST (+20 dBm), estrema (26/11/2026)

**Richiesta dell'autore:** prevedere nel firmware una modalità BOOST a **+20 dBm**, applicabile **a ogni profilo**, come modalità **estrema**, con la segnalazione che c'è il rischio.

**Stato:** scritta nel firmware di misura, nella configurazione del nodo e nella pagina di installazione. **Provata sul PC** (logica del firmware, configurazione, pagina). **Non compilata per le schede e non provata su schede vere**: nessun dato di corrente, temperatura o spurie misurato.

## Cosa fa
- **Di base** i nodi trasmettono a **+17 dBm** (decisione del 26/11/2026: massimo in continuo dell'SX1278). Il BOOST è **sempre spento all'avvio** e non si salva.
- **BOOST = +20 dBm in ogni profilo** (LoRa e FSK a 430-440 MHz, modulo a 2,4 GHz). Dove un profilo non arriva a +20 dBm (radio SPI a 2,4 GHz senza amplificatore, circa +12,5 dBm) il BOOST dà il massimo del profilo.
- Si attiva **solo scrivendo la parola RISCHIO**: `BOOST ON RISCHIO`. `BOOST ON` da solo non attiva e ristampa l'avviso. `BOOST OFF` torna alla potenza normale; `BOOST STATUS` mostra stato, potenza e ciclo di lavoro.
- Nella **configurazione del nodo** (pagina `nodo.html`, `tools/config_nodo.py`) la casella BOOST richiede la conferma "ho letto il rischio e lo accetto"; senza conferma la configurazione non è valida. L'avviso resta visibile finché il BOOST è attivo.
- **Schermo e riga di stato** della scheda mostrano `+20dBm !B` e "BOOST (RISCHIO)".

## Il rischio che si segnala (solo tecnico)
Nessun limite legale: vale [regole-radioamatoriali.md](regole-radioamatoriali.md). I rischi sono quelli dell'ingegneria, dal datasheet ([confronto-datasheet.md](confronto-datasheet.md)):
1. **SX1278:** +20 dBm solo con **ciclo di lavoro massimo 1%** e **VSWR 3:1** al connettore (Table 35); in continuo il massimo è **+17 dBm**. Corrente circa 120 mA a +20 dBm.
2. **SX1262:** +20 dBm è sotto il suo massimo (+22 dBm) ma la corrente è alta (circa 118 mA).
3. **Calore, alimentazione, batteria** sotto sforzo; **ricevitori vicini saturati**; **armoniche e spurie più forti** (filtrare; la terza armonica del voto a 144,9 MHz cade a 434,7 MHz).
4. **Antenna adattata obbligatoria:** mai trasmettere senza antenna o con antenna guasta.
5. **Modulo Ebyte a 2,4 GHz:** a 20 dBm e più, il ricevitore dell'altro modulo si può danneggiare se è vicino (blocking massimo 10 dBm): distanza o attenuatore.

## Controllo del ciclo di lavoro (firmware di misura)
In BOOST ogni trasmissione conta in una **finestra scorrevole di 100 s**; sopra l'**1%** il firmware stampa `ATTENZIONE BOOST: ciclo di lavoro …` (al massimo ogni 5 s). **Il firmware non spegne il BOOST da solo**: è una modalità estrema voluta dall'operatore. Il comando **CW** (portante continua) in BOOST segnala che è ciclo 100%, molto oltre l'1%.
`POWER` oltre +17 dBm: sull'SX1278 è rifiutato (si passa da BOOST); sull'SX1262 è ammesso con avviso.

## Dove sta nel codice
| Cosa | Dove |
|---|---|
| Logica (parametri, comando, ciclo di lavoro) | `firmware/misura/src/misura_core.h` (`kBoostDbm`, `parseBoost`, `BoostGuard`, `effectivePowerDbm`) |
| Comando, avvisi, schermo | `firmware/misura/src/main.cpp`, `status_display.h` |
| Tabella dei profili e rischi | `tools/limiti_chip.py` (`PROFILE_POWER_DBM`, `boost_dbm`, `boost_risks`) |
| Configurazione del nodo | `tools/config_nodo.py` (`boost`, `boost_rischio_accettato`, `potenze`), `site/nodo.html` |
| Prove | `firmware/misura/tests/test_core.cpp`, `tests/sim/test_config_nodo.py`, `tests/page/run_nodo.js` |

## Da fare / da decidere
- Compilare e provare il firmware di misura con BOOST su T3 e T-Beam (corrente, temperatura, spurie con l'analizzatore), fase 1.
- Il firmware dei nodi V3 non esiste ancora: la regola è scritta (parametro `boost` della configurazione, `BOOST ON RISCHIO`), da realizzare con lo stesso codice di `misura_core.h`.
- **Decisione:** il nodo deve **spegnere il BOOST da solo** se supera l'1% (protezione del chip), oppure resta solo l'avviso come ora?
- L'app di misura non ha ancora il comando BOOST (si manda da terminale seriale).
