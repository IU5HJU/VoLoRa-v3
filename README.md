# VoLoRa V3 (studio)

Studio del **protocollo VoLoRa V3**: firmware **specializzati per ruolo** (ogni dispositivo fa una cosa sola) e **trasferimento di immagini** con le massime prestazioni delle radio LoRa/FSK, con **negoziazione del modo** fra le stazioni, da quello più veloce a quelli più lenti ma più robusti, fino ai casi estremi, **ridimensionando l'immagine** quando serve.

> **Stato: studio, nessun codice di produzione.** Questo repository è **distinto** da [VoLoRa](https://github.com/IU5HJU/VoLoRa) (protocollo v2): non ne modifica il lavoro, i tag né le pubblicazioni.

## Rapporto con VoLoRa v2

- Voce e testo restano in **protocollo VoLoRa v2** e devono funzionare fra una stazione V3 e una v2.
- Il codice della v2 si riusa senza copiarlo: sta nel submodule `third_party/VoLoRa-v2`, **fissato al tag `v0.1.0-rc.1`** di VoLoRa (commit `0efa2a3`). Per aggiornarlo si sposta su un altro tag, mai su un ramo.
- Dopo aver clonato: `git submodule update --init`.

## Documenti

- [docs/roadmap.md](docs/roadmap.md): fasi del lavoro.
- [docs/architettura.md](docs/architettura.md): ruoli, firmware, vincoli.
- [docs/applicazione.md](docs/applicazione.md): applicazione con interfaccia grafica per le prove (monitor seriali, tasti rapidi, risultati, invio su GitHub, immagini di prova).
- [docs/protocollo-immagini.md](docs/protocollo-immagini.md): bozza del protocollo immagini V3 (gradini, frame, negoziazione, ridimensionamento).
- [docs/scala-modi.md](docs/scala-modi.md): bozza della scala dei modi LoRa/FSK (calcolata, non misurata).
- [docs/firmware-misura.md](docs/firmware-misura.md): firmware di misura (non è il V3) e pilota dal PC.
- [docs/materiale.md](docs/materiale.md), [docs/guida-colleghi.md](docs/guida-colleghi.md) e [docs/prove-sul-campo.md](docs/prove-sul-campo.md): materiale da procurare, guida per chi collabora e protocollo delle prove a distanza.
- [Pagina di installazione](https://iu5hju.github.io/VoLoRa-v3/) del firmware di misura dal browser (**non ancora pubblicata**: serve il primo giro del workflow e Settings → Pages → Source: GitHub Actions). Il codice è in `site/`, l'assemblaggio in `tools/make_site.sh`.
- [docs/piano-misure.md](docs/piano-misure.md): piano di misura della fase 1 (attrezzatura, metodo, misure).
- [docs/scheda-sd.md](docs/scheda-sd.md): la microSD della T3 e dove conviene usarla.
- [docs/punti-aperti.md](docs/punti-aperti.md): decisioni ancora da prendere.

## Licenza

GNU General Public License v3 (vedi [LICENSE](LICENSE)), come VoLoRa e come la libreria Codec2 usata.
Possono trasmettere solo radioamatori con il proprio nominativo, sulle frequenze e con le potenze consentite.
