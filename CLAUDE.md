# Istruzioni per chi lavora su questo repository (persone e assistenti automatici)

## Regola ferma: nessuna privacy
**Prima di scrivere o dire qualunque cosa su privacy, riservatezza, "dati personali", posizione o nominativo da nascondere, ridurre o rendere facoltativi, leggi `docs/regole-radioamatoriali.md`.**
In questo progetto radioamatoriale nominativo, rapporto di segnale e posizione (locatore o GPS assoluta) sono elementi essenziali e fissi, da trasmettere sempre.
**Non** proporre privacy, anonimizzazione, posizione spenta di base, avvertenze o campi per nascondere la posizione. Il responsabile del progetto (IU5HJU) ha chiarito la regola più volte: non va riaperta.

## Appunti di progetto da rileggere
- `docs/regole-radioamatoriali.md`: nominativo, rapporto e posizione sempre; nessuna privacy.
- `docs/mesh-v3.md`: la logica mesh voluta dall'autore e il registro delle decisioni (sezione 10).
- `docs/simulatore-mesh.md`: simulatore mesh e risultati sulla regola del gruppo di ripetitori.
- `docs/voting-isofrequenza.md`: isofrequenza e voting nella voce, elezione fra due nodi. Regola: **Internet non è affidabile**, annunci e voti vanno via radio.
- `docs/terminali-nascosti.md`: terminali nascosti e perché il protocollo usa turni dall'orologio e veto del destinatario.
- `docs/protocollo-immagini.md`, `docs/simulatore-immagini.md`, `docs/scala-modi.md`: protocollo e numeri dei gradini.

## Per il resto
- Lingua dei documenti e dei messaggi: italiano.
- Il progetto è uno **studio** (protocollo VoLoRa V3): dichiarare sempre cosa è provato su schede vere e cosa no.
- Prove sul PC: `make -C firmware/misura test`, `python3 tests/app/test_core.py`, `python3 tests/sim/test_sim_immagini.py`, `python3 tests/sim/test_sim_mesh.py`, `python3 tests/sim/test_fontana.py`, `python3 tests/sim/test_frame_mesh.py`, `python3 tests/sim/test_voting.py`, `python3 tests/app/test_timesync.py`, `python3 tests/app/test_field.py`, `python3 tests/app/test_bluetooth.py`; interfaccia con `xvfb-run -a python3 tests/app/test_gui.py`.
- Le decisioni già prese stanno in `docs/punti-aperti.md` e `docs/roadmap.md`; la precisione dell'orologio richiesta è in `docs/applicazione.md` (basta NTP o GPS, nessuna ricerca di precisione estrema).
