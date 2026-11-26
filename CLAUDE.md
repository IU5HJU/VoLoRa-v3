# Istruzioni per chi lavora su questo repository (persone e assistenti automatici)

## Regola ferma: nessuna privacy
**Prima di scrivere o dire qualunque cosa su privacy, riservatezza, "dati personali", posizione o nominativo da nascondere, ridurre o rendere facoltativi, leggi `docs/regole-radioamatoriali.md`.**
In questo progetto radioamatoriale nominativo, rapporto di segnale e posizione (locatore o GPS assoluta) sono elementi essenziali e fissi, da trasmettere sempre.
**Non** proporre privacy, anonimizzazione, posizione spenta di base, avvertenze o campi per nascondere la posizione. Il responsabile del progetto (IU5HJU) ha chiarito la regola più volte: non va riaperta.

## Regola ferma: frequenze e potenza
**Prima di scrivere o dire qualunque cosa su frequenze o potenza di trasmissione (limiti, avvertenze, apparati ISM, moduli da 27 dBm, 2,4 GHz, 430-440 MHz), leggi `docs/regole-radioamatoriali.md`, sezione "Frequenze e potenza".**
In breve: l'autore, radioamatore, ha indicato che in Italia i radioamatori possono usare **fino a 500 W** sia a 430-440 MHz sia a 2,4 GHz. Non proporre limiti legali di potenza né avvertenze; restano solo i limiti tecnici (moduli, calore, alimentazione, saturazione del ricevitore, spurie).
**Frequenze dei canali nel firmware:** quelle di T3 e T-Beam sono **liberamente configurabili** (si controlla solo il campo del chip); quelle del modulo a 2,4 GHz sono configurabili a piacere **dentro la banda dei radioamatori** (2400-2450 MHz), sulla griglia del modulo. Le tabelle del progetto sono valori di partenza.

## Appunti di progetto da rileggere
- `docs/regole-radioamatoriali.md`: nominativo, rapporto e posizione sempre; nessuna privacy; frequenze e potenza (fino a 500 W a 430-440 MHz e a 2,4 GHz).
- `docs/mesh-v3.md`: la logica mesh voluta dall'autore e il registro delle decisioni (sezione 10).
- `docs/simulatore-mesh.md`: simulatore mesh e risultati sulla regola del gruppo di ripetitori.
- `docs/compatibilita-v2.md`: **l'infrastruttura v2 non si modifica**; il V3 è retrocompatibile solo per voce, messaggio vocale e testo.
- `docs/voting-isofrequenza.md`: isofrequenza e voting nella voce, elezione fra due nodi. Regola: **Internet non è affidabile**, annunci e voti vanno via radio.
- `docs/terminali-nascosti.md`: terminali nascosti e perché il protocollo usa turni dall'orologio e veto del destinatario.
- `docs/protocollo-immagini.md`, `docs/simulatore-immagini.md`, `docs/scala-modi.md`: protocollo e numeri dei gradini.

## Per il resto
- Lingua dei documenti e dei messaggi: italiano.
- Il progetto è uno **studio** (protocollo VoLoRa V3): dichiarare sempre cosa è provato su schede vere e cosa no.
- Prove sul PC: `make -C firmware/misura test`, `python3 tests/app/test_core.py`, `python3 tests/sim/test_sim_immagini.py`, `python3 tests/sim/test_sim_mesh.py`, `python3 tests/sim/test_fontana.py`, `python3 tests/sim/test_frame_mesh.py`, `python3 tests/sim/test_voting.py`, `python3 tests/sim/test_uart_frame.py`, `python3 tests/sim/test_ebyte_e28.py`, `python3 tests/sim/test_canali.py`, `python3 tests/sim/test_nodo_semplice.py`, `python3 tests/sim/test_config_nodo.py`, `python3 tests/sim/test_ascolto_nodo.py`, `python3 tests/sim/test_limiti_chip.py`, `python3 tests/sim/test_ble_bridge.py`, `python3 tests/sim/test_reflector_v3.py`, `python3 tests/interop/test_reflector_vs_vlnode.py` (compila `vlnode` dal submodule), `reflector/build.sh /tmp/refl` e poi `/tmp/refl/build/test_reflector_v3` (reflector C++: patch sulla v2), `python3 tests/interop/test_reflector_cpp.py`, `python3 tests/app/test_uartlink.py`, `python3 tests/app/test_timesync.py`, `python3 tests/app/test_field.py`, `python3 tests/app/test_bluetooth.py`; interfaccia con `xvfb-run -a python3 tests/app/test_gui.py`.
- Le decisioni già prese stanno in `docs/punti-aperti.md` e `docs/roadmap.md`; la precisione dell'orologio richiesta è in `docs/applicazione.md` (basta NTP o GPS, nessuna ricerca di precisione estrema).
