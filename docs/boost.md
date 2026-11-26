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

## Nel firmware V3 (scheda mobile e banco)
Il BOOST è nel driver radio V3 (`firmware/v3/src/radio_board.h`) con il nucleo `firmware/v3/src/boost.h` (stesso comando, stessi testi, stesso conteggio del ciclo di lavoro di `misura_core.h`). **Provato sul PC** (`tests/test_boost.cpp`, 26 controlli per il BOOST e 10 per l'IOF MODE: comando, potenza, finestra di 100 s, avvisi, nessuno spegnimento automatico); **compilato dalla CI, mai eseguito su una scheda**.
- Comandi sulla seriale di `main_mobile.cpp` e `main_bench.cpp`: `BOOST ON RISCHIO`, `BOOST OFF`, `BOOST STATUS`. Sempre **spento all'avvio**, non si salva.
- La potenza vale per **ogni gradino** (LoRa e FSK): ogni cambio di gradino riconfigura la radio e usa la potenza in vigore (+17 dBm, o +20 dBm in BOOST). Ad accensione e spegnimento si cambia subito la potenza con `setOutputPower`, e in BOOST si porta il limite di corrente a 140 mA (circa 120 mA di assorbimento a +20 dBm). RadioLib (letta nel sorgente 7.8.1; la CI usa la 7.5.0) accetta 20 dBm su SX1278 (PA_BOOST con PA_DAC alto) e SX1262.
- **SX1278:** ogni trasmissione conta in una finestra di 100 s; sopra l'1% esce `ATTENZIONE BOOST: ciclo di lavoro …` (al massimo ogni 5 s). Il ponte e il protocollo non cambiano e **il BOOST non si spegne da solo** (decisione: solo avviso). Un trasferimento d'immagine in BOOST supera facilmente l'1%: l'avviso comparirà.
- **SX1262:** +20 dBm è sotto il suo massimo (+22 dBm): il ciclo si misura (si vede in `BOOST STATUS`) ma non c'è avviso di ciclo; restano calore, corrente, antenna e saturazione dei ricevitori vicini.
- Non c'è ancora un comando BOOST dal telefono (Bluetooth): è una scelta voluta, perché attivarlo richiede di leggere l'avviso sulla seriale.

## IOF MODE (+22 dBm, solo SX1262)
Un livello **sopra il BOOST**, solo per le schede con l'**SX1262** (T-Beam): **+22 dBm, il massimo del chip**. Nel firmware V3 si attiva con `IOF ON RISCHIO` (poi `IOF OFF`, `IOF STATUS`) sulla seriale; come il BOOST è **sempre spento all'avvio**, non si salva e **non si spegne da solo**. I livelli sono uno solo alla volta: `BOOST ON RISCHIO` dopo `IOF` torna a +20 dBm, `BOOST OFF` o `IOF OFF` a +17 dBm. Sull'**SX1278** il comando è rifiutato (il suo massimo è +20 dBm con il BOOST e solo all'1% di ciclo).
- **Rischio (solo tecnico):** corrente al limite (circa 120-140 mA; il limite di corrente della radio è portato a 140 mA, il massimo dell'SX1262), calore, batteria sotto sforzo, ricevitori vicini saturati, armoniche e spurie più forti, **antenna adattata obbligatoria**. Nessun limite legale: vale [regole-radioamatoriali.md](regole-radioamatoriali.md).
- Il ciclo di lavoro si misura (si vede con `IOF STATUS`) ma l'SX1262 non ha il limite dell'1% dell'SX1278: non c'è avviso di ciclo.
- Nel codice: `firmware/v3/src/boost.h` (`Level::Iof`, `kIofDbm`, `kIofWarning`, `parseIof`), `radio_board.h` (`boostCommand`), prove in `tests/test_boost.cpp` (36 controlli, sul PC). **Mai eseguito su una scheda.**

> **Dedica.** L'IOF MODE è dedicato a **IZ5IOF Andrea**, grande radioamatore e vero amico, che ama spremere tutto il possibile dalle sue apparecchiature per realizzare il collegamento impossibile: ogni volta ci riesce, e puntualmente qualche apparecchiatura ci rimette. Questo livello di potenza è per lui (l'avviso che esce sulla seriale all'attivazione porta il suo nome e dice chiaramente che chi spreme tutto spesso guasta qualcosa).

## Da fare / da decidere
- Compilare e provare il firmware di misura con BOOST su T3 e T-Beam (corrente, temperatura, spurie con l'analizzatore), fase 1.
- ~~Il firmware dei nodi V3~~ La scheda mobile e il banco V3 hanno il BOOST (sezione sopra); il ruolo "nodo" non esiste ancora e prenderà il parametro `boost` della configurazione.
- Da misurare sulla scheda: corrente, temperatura e spurie a +20 dBm; se il limite di corrente a 140 mA basta davvero.
- ~~**Decisione**~~ **Deciso il 26/11/2026: solo avviso.** Il nodo non spegne il BOOST da solo se supera l'1%: segnala il rischio e continua.
- L'app di misura non ha ancora il comando BOOST (si manda da terminale seriale).
