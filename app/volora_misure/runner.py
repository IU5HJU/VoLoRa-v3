"""Sequenza di una misura fra due schede (usa solo l'interfaccia delle schede: vale per quelle vere e per quelle finte)."""
import time

from . import core


class RunError(Exception):
    pass


def command(board, line, prefix="MODE", timeout=6):
    """Manda un comando e aspetta la risposta; ERR diventa un errore."""
    w = board.expect(prefix, timeout)
    board.send(line)
    r = w.wait()
    if r is None:
        raise RunError(f"{board.name}: nessuna risposta a '{line}'")
    if r.startswith("ERR"):
        raise RunError(f"{board.name}: {r}")
    return r


def configure(boards, code, power, freq, payload, call):
    for b in boards:
        command(b, f"CALL {call}", "OK")
        command(b, core.mode_command(code, b.chip))
        command(b, f"POWER {power}")
        command(b, f"FREQ {freq}")
        command(b, f"PAYLOAD {payload}")


def run_series(tx, rx, codes, count, power, att, freq, payload, call, stop=None, progress=None, on_row=None):
    """Serie di modi fra due schede, per esempio i gradini lenti R11-R14: per ogni modo configura le due schede e manda `count` pacchetti con un intervallo
    adatto al tempo in aria. Ritorna le righe di risultato. `stop` e' un threading.Event; `progress(i, n, codice)` e' chiamata prima di ogni modo, `on_row(riga)` dopo."""
    rows = []
    for i, code in enumerate(codes):
        if stop is not None and stop.is_set():
            break
        if progress:
            progress(i, len(codes), code)
        configure([tx, rx], code, power, freq, payload, call)
        row = run_point(tx, rx, code, count, core.interval_ms(code, payload), power, att, freq)
        rows.append(row)
        if on_row:
            on_row(row)
    return rows


def run_point(tx, rx, code, count, interval_ms, power, att, freq, stop=None):
    """Una misura: la scheda rx ascolta, la tx manda `count` pacchetti. Ritorna la riga di risultato (dizionario di core.FIELDS)."""
    window = int(count * interval_ms / 1000.0) + 15
    rx_wait = rx.expect("RXSUM", window + 15)
    tx_wait = tx.expect("TXSUM", window + 15)
    rx.send(f"RX {window}")
    time.sleep(0.3)
    tx.send(f"TX {count} {interval_ms}")
    txline = tx_wait.wait()
    if txline is None or txline.startswith("ERR"):
        rx.send("STOP")
        rx_wait.cancel()
        raise RunError(f"{tx.name}: {txline or 'TXSUM non arrivato'}")
    rxline = rx_wait.wait()
    if rxline is None or rxline.startswith("ERR"):
        raise RunError(f"{rx.name}: {rxline or 'RXSUM non arrivato'}")
    _, t = core.parse_line(txline)
    _, r = core.parse_line(rxline)
    return core.new_row(code, freq, power, att, t, r)
