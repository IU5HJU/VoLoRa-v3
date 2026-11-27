# VoLoRa V3 (studio)

Studio del **protocollo VoLoRa V3**: firmware **specializzati per ruolo** (ogni dispositivo fa una cosa sola) e **trasferimento di immagini** con le massime prestazioni delle radio LoRa/FSK, con **negoziazione del modo** fra le stazioni, da quello più veloce a quelli più lenti ma più robusti, fino ai casi estremi, **ridimensionando l'immagine** quando serve.

> **Stato: studio, nessun codice di produzione.** Questo repository è **distinto** da [VoLoRa](https://github.com/IU5HJU/VoLoRa) (protocollo v2): non ne modifica il lavoro, i tag né le pubblicazioni.

## Rapporto con VoLoRa v2

- Voce, messaggio vocale e testo restano in **protocollo VoLoRa v2** e devono funzionare fra una stazione V3 e una v2. **L'infrastruttura v2 esistente non si modifica**: il V3 è retrocompatibile solo per questo traffico ([docs/compatibilita-v2.md](docs/compatibilita-v2.md)).
- Il codice della v2 si riusa senza copiarlo: sta nel submodule `third_party/VoLoRa-v2`, **fissato al tag `v0.1.0-rc.1`** di VoLoRa (commit `0efa2a3`). Per aggiornarlo si sposta su un altro tag, mai su un ramo.
- Dopo aver clonato: `git submodule update --init`.

## Documenti

- [docs/roadmap.md](docs/roadmap.md): fasi del lavoro.
- [docs/architettura.md](docs/architettura.md): ruoli, firmware, vincoli.
- [docs/gps-tempo.md](docs/gps-tempo.md): il tempo del GPS spiegato con numeri veri (settimane, rollover, secondi intercalari) e script di calcolo.
- [docs/gps-bluetooth.md](docs/gps-bluetooth.md): GPS Bluetooth su Linux (provato con il Nokia LD-3W): accoppiamento, rfcomm, fix e rollover della data.
- [docs/applicazione.md](docs/applicazione.md): applicazione con interfaccia grafica per le prove (monitor seriali, tasti rapidi, risultati, invio su GitHub, immagini di prova).
- [docs/simulatore-immagini.md](docs/simulatore-immagini.md): simulatore del protocollo immagini (frame veri, canale con perdite, scenari) e cosa ha trovato.
- [docs/protocollo-immagini.md](docs/protocollo-immagini.md): bozza del protocollo immagini V3 (gradini, frame, negoziazione, ridimensionamento).
- [docs/scala-modi.md](docs/scala-modi.md): bozza della scala dei modi LoRa/FSK (calcolata, non misurata).
- [docs/firmware-misura.md](docs/firmware-misura.md): firmware di misura (non è il V3) e pilota dal PC.
- [docs/simulatore-mesh.md](docs/simulatore-mesh.md): simulatore mesh (collisioni dei beacon, scelta del gruppo di ripetitori, taratura della regola, terminali nascosti) con i risultati.
- [docs/terminali-nascosti.md](docs/terminali-nascosti.md): cosa sono i terminali nascosti e perché il protocollo usa turni dall'orologio, voto e veto del destinatario.
- [docs/voting-isofrequenza.md](docs/voting-isofrequenza.md): più nodi sulla stessa frequenza nella voce: elezione per qualità e voto via radio (Internet non è affidabile).
- [docs/compatibilita-v2.md](docs/compatibilita-v2.md): la regola di compatibilità con la v2 (infrastruttura invariata).
- [docs/band-plan.md](docs/band-plan.md): il band plan ARI (70 cm, 13 cm, 23 cm) dalle schermate del sito, e dove cadono i nostri canali.
- [docs/reflector-v3.md](docs/reflector-v3.md): il reflector V3, sostituto compatibile del reflector v2 (stesso collegamento, voce e testo identici) con il trasporto del V3.
- [docs/configurazione-nodo.md](docs/configurazione-nodo.md): la configurazione di un nodo scelta dal sysop: gateway o pappagallo per v2 e V3, topologia singola, doppia o tripla.
- [docs/modulo-2g4-uart.md](docs/modulo-2g4-uart.md): i moduli Ebyte a 2,4 GHz con seriale, usati come tubo opaco (profilo 2 del cambio di banda), con la scheda di prova dell'applicazione e la configurazione dal programma.
- [docs/prova-gradini-lenti.md](docs/prova-gradini-lenti.md): prova in laboratorio dei gradini R10-R14 fra le due T3, con la serie F10 dell'app.
- [docs/mesh-v3.md](docs/mesh-v3.md): bozza della logica mesh V3 (beacon, polling, ripetizione, ricezione da più stazioni) con numeri calcolati e decisioni.
- [docs/regole-radioamatoriali.md](docs/regole-radioamatoriali.md): regola di progetto: nominativo, rapporto di segnale e posizione (locatore o GPS) sempre; nessuna privacy.
- [docs/metodo-di-prova.pdf](docs/metodo-di-prova.pdf): il metodo di prova spiegato in tre pagine, da condividere con i colleghi che vogliono partecipare.
- [docs/materiale.md](docs/materiale.md), [docs/guida-colleghi.md](docs/guida-colleghi.md) e [docs/prove-sul-campo.md](docs/prove-sul-campo.md): materiale da procurare, guida per chi collabora e protocollo delle prove a distanza.
- [Pagina di installazione](https://iu5hju.github.io/VoLoRa-v3/) del firmware di misura dal browser (**non ancora pubblicata**: serve il primo giro del workflow e Settings → Pages → Source: GitHub Actions). Il codice è in `site/`, l'assemblaggio in `tools/make_site.sh`. Il firmware V3 si installa da `firmware-v3.html` sullo stesso sito (studio, mai provato su schede).
- [docs/piano-misure.md](docs/piano-misure.md): piano di misura della fase 1 (attrezzatura, metodo, misure).
- [docs/scheda-sd.md](docs/scheda-sd.md): la microSD della T3 e dove conviene usarla.
- [docs/punti-aperti.md](docs/punti-aperti.md): decisioni ancora da prendere.

## Licenza

GNU General Public License v3 (vedi [LICENSE](LICENSE)), come VoLoRa e come la libreria Codec2 usata.
Possono trasmettere solo radioamatori con il proprio nominativo, sulle frequenze e con le potenze consentite.
