"""Nodo a scheda singola (una sola radio, nessun canale di voto): la situazione di partenza per le prove (26/11/2026).
Regole decise dall'autore:
  - con Internet il nodo manda la voce in rete e usa l'infrastruttura della v2 (reflector), senza ritrasmettere in RF;
  - senza Internet fa il "pappagallo": memorizza il messaggio vocale e lo ripete a fine trasmissione;
  - prima di ripetere in RF aspetta 300 ms e poi un ritardo per qualita' su 400 ms, ascoltando se un altro nodo parte;
  - se negli ultimi 30 minuti non ha sentito altri nodi (ne' il frame NODO ne' pacchetti RELAYED) non aspetta.
Internet e' solo un aiuto: nulla di essenziale dipende da lui (docs/regole... e architettura). Provato sul PC: tests/sim/test_nodo_semplice.py."""

ATTESA_FISSA_S = 0.300          # dopo la finestra del voto (200 ms) piu' 100 ms
AMPIEZZA_QUALITA_S = 0.400      # il migliore segnale parte per primo
ISOLAMENTO_S = 30 * 60          # senza altri nodi sentiti per tanto tempo il nodo e' "solitario"
SPAN_DB = 20.0                  # dB che coprono l'ampiezza del ritardo
MAX_VOCE_S = 60.0               # la v2 spegne la TX di un ripetitore dopo 60 s continui di voce: anche il pappagallo si ferma li'
NOTA_MEMORIA = "il pappagallo memorizza su RAM o microSD: 1 minuto di Codec2 1200 sono circa 9 kB, a 3200 circa 24 kB"


def vicini_noti(ultimo_sentito_s, adesso_s):
    """True se un altro nodo e' stato sentito (frame NODO o pacchetto RELAYED) negli ultimi 30 minuti."""
    return ultimo_sentito_s is not None and adesso_s - ultimo_sentito_s <= ISOLAMENTO_S


def qualita(margine_db):
    return min(1.0, max(0.0, margine_db / SPAN_DB))


def azione_voce(internet, ultimo_sentito_s, adesso_s, margine_db):
    """Cosa fa il nodo quando riceve voce. Ritorna (azione, ritardo_s):
    'rete'      : manda la voce in rete (infrastruttura v2), nessuna ritrasmissione in RF;
    'pappagallo': memorizza e, a fine trasmissione, ripete in RF dopo `ritardo_s` (0 se e' solitario), ascoltando se un altro nodo parte prima."""
    if internet:
        return "rete", 0.0
    if not vicini_noti(ultimo_sentito_s, adesso_s):
        return "pappagallo", 0.0
    return "pappagallo", ATTESA_FISSA_S + AMPIEZZA_QUALITA_S * (1.0 - qualita(margine_db))


def deve_ripetere(heard_relayed_during_wait):
    """Dopo l'attesa il pappagallo ripete solo se non ha sentito partire un altro nodo."""
    return not heard_relayed_during_wait
