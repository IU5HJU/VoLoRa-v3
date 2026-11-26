#!/usr/bin/env python3
"""Tracce del PROTOCOLLO immagini (tools/img_proto.py) per la prova di conformita' del firmware C++ (firmware/v3/tests/test_protocol.cpp).
Fa girare il simulatore su alcuni scenari e registra, per ogni stazione, tutto cio' che entra e tutto cio' che esce:
  <scenario>.link_S.txt, .link_R.txt   il collegamento di ciascuna stazione: chiamate (tick, setrung, tx, heard) e stato dopo ciascuna
  <scenario>.rx.txt                    il ricevitore: frame ricevuti con rssi, snr, ora, gradino -> frame di risposta; STATUS e PROBE-REPORT
  <scenario>.tx.txt                    il mittente: a ogni ripresa (ora, gradino, in ricerca, risposta) l'azione che chiede
Numeri decimali in repr (si rileggono esatti). Non si salvano nel repository (grandi): si generano al momento della prova.
  python3 tools/gen_tracce_protocollo.py <cartella>"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import img_proto as ip  # noqa: E402
import sim_immagini as si  # noqa: E402

SCENARI = {
    "vicino": dict(chips=("SX1278", "SX1278"), prx=-100.0, scen="costante", seed=1, size=4000),
    "medio": dict(chips=("SX1278", "SX1262"), prx=-122.0, scen="degrada", seed=2, size=6000),
    "gradino": dict(chips=("SX1262", "SX1262"), prx=-128.0, scen="gradino", seed=1, size=5000),
    "lontano": dict(chips=("SX1278", "SX1278"), prx=-136.0, scen="oscilla", seed=3, size=3000, tcxo=True),
    "perso": dict(chips=("SX1278", "SX1278"), prx=-142.0, scen="costante", seed=1, size=3000),
    "budget": dict(chips=("SX1278", "SX1262"), prx=-125.0, scen="oscilla", seed=5, size=30000, budget=120.0),
    "quattro_livelli": dict(chips=("SX1278", "SX1278"), prx=-95.0, scen="costante", seed=6, size=20000, layers=(0.1, 0.3, 0.6, 1.0)),
    "tcxo_ricerca": dict(chips=("SX1278", "SX1278"), prx=-136.0, scen="gradino", seed=4, size=2500, tcxo=True),
    "senza_hello": dict(chips=("SX1278", "SX1278"), prx=-150.0, scen="costante", seed=2, size=1000),
}


def fx(v):
    return repr(float(v))


def stato(n):
    return f"rung={n.rung} lost={'-' if n.lost_since is None else fx(n.lost_since)} hold={int(n.hold)} holdu={fx(n.hold_until)} lh={fx(n.last_heard)} had={int(n.had_link)}"


def ev_str(evs):
    return ";".join((f"F:{fx(e[1])}:{e[2]}" if e[0] == "fallback" else f"R:{e[1]}:{e[2]}") for e in evs) or "-"


def categoria(msg):
    for k, c in (("nessun incontro", "hello"), ("negoziazione", "negoziazione"), ("OFFER senza ACCEPT", "offer"), ("il primo livello non entra", "budget"), ("collegamento perso (nessun", "progresso"),
                 ("collegamento perso (la ricerca", "ricerca"), ("DONE non confermato", "done"), ("tempo massimo", "tempo")):
        if msg.startswith(k):
            return c
    return "altro"


def registra(nome, sc, out):
    ch = si.Channel(sc["prx"], sc["scen"], extra_db=11.0 if sc["scen"] != "oscilla" else 14.0, when_s=60.0, span_s=300.0, rng=random.Random(sc["seed"] + 1))
    sim = si.Simulator(sc["size"], sc.get("layers", (1 / 3, 2 / 3, 1.0)), ch, sc["chips"][0], sc["chips"][1], sc.get("budget", 600.0), sc["seed"], tcxo_a=sc.get("tcxo", False),
                       tcxo_b=sc.get("tcxo", False), max_time_s=6 * 3600.0, ricerca=sc.get("ricerca", "calendario"), incontro=sc.get("incontro", "hello"))
    L = {"S": [], "R": [], "rx": [], "tx": []}
    # ---- collegamento
    for node in (sim.S, sim.R):
        lg = L[node.name]
        o_tick, o_set, o_tx, o_heard = node.tick, node.set_rung, node.on_tx, node.on_heard

        def tick(t, order, ricerca, node=node, lg=lg, o=o_tick):
            ord_ = order()
            ev = o(t, order, ricerca)
            lg.append(f"tick {fx(t)} {ricerca} {','.join(str(x) for x in ord_)} | {ev_str(ev)} | {stato(node)}")
            return ev

        def set_rung(r, node=node, lg=lg, o=o_set):
            ev = o(r)
            lg.append(f"setrung {r} | {ev_str(ev)} | {stato(node)}")
            return ev

        def on_tx(t, node=node, lg=lg, o=o_tx):
            o(t)
            lg.append(f"tx {fx(t)} | {stato(node)}")

        def on_heard(t, tipo, reply, node=node, lg=lg, o=o_heard):
            o(t, tipo, reply)
            lg.append(f"heard {fx(t)} {'-' if tipo is None else tipo} {int(reply)} | {stato(node)}")
        node.tick, node.set_rung, node.on_tx, node.on_heard = tick, set_rung, on_tx, on_heard
    # modifiche al collegamento che arrivano da fuori (ricevitore e mittente): servono per rifare il collegamento da solo
    o_recv, o_perform = sim.recv, sim.perform

    def recv(f, o=o_recv):
        r = o(f)
        return r
    # (la tenuta del gradino del ricevitore e' decisa da Receiver.on_frame e applicata da recv: la si registra sul ricevitore, in on_frame)

    def perform(a, o=o_perform):
        if a[0] == "holdclear":
            L["S"].append("holdclear")
        return o(a)
    sim.perform = perform
    # ---- frame con i byte originali
    o_air = sim.air

    def air(tx, rx, frame, o=o_air):
        d = o(tx, rx, frame)
        if d is not None:
            d["_raw"] = bytes(frame)
        return d
    sim.air = air
    # ---- ricevitore
    rc = sim.receiver
    o_on, o_st, o_pr = rc.on_frame, rc.status, rc.probe_report

    def on_frame(f, rssi, snr, t, rung, lost):
        rep = o_on(f, rssi, snr, t, rung, lost)
        L["rx"].append(f"frame {f['_raw'].hex()} {fx(rssi)} {fx(snr)} {fx(t)} {rung} {int(lost)} | {rep.frame.hex() if rep.frame else '-'} {'-' if rep.hold_until is None else fx(rep.hold_until)} "
                       f"{'-' if rep.rung_after is None else rep.rung_after}")
        if rep.hold_until is not None:
            L["R"].append(f"holdu {fx(rep.hold_until)}")      # il mezzo la applica al collegamento del ricevitore subito dopo
        return rep

    def status(n, k):
        fr = o_st(n, k)
        L["rx"].append(f"status {n} {k} | {fr.hex()}")
        return fr

    def probe_report():
        fr = o_pr()
        L["rx"].append(f"probe | {fr.hex() if fr else '-'}")
        return fr
    rc.on_frame, rc.status, rc.probe_report = on_frame, status, probe_report
    # ---- mittente: ciclo di esecuzione registrato
    snd = sim.sender
    L["rx"].insert(0, f"init call={rc.call.encode().hex()} sx1262={int(rc.chip == 'SX1262')} tcxo={int(rc.tcxo)} window={rc.window} hello={int(rc.incontro == 'hello')}")
    L["tx"].insert(0, f"init sess={snd.sess} call={snd.call.encode().hex()} sx1262={int(snd.chip == 'SX1262')} tcxo={int(snd.tcxo)} budget={fx(snd.budget)} window={snd.window} probes={snd.probes_r10} "
                      f"layers={','.join(str(e) for e in snd.layer_ends)}")
    with open(os.path.join(out, f"{nome}.obj.txt"), "w") as fo:
        fo.write(snd.obj.hex() + "\n")
    proc = snd.proc()
    ans, tx = None, L["tx"]
    try:
        while True:
            snd.t, snd.rung, snd.lost = sim.t, sim.S.rung, sim.S.lost_since is not None
            res_line = f"resume {fx(snd.t)} {snd.rung} {int(snd.lost)} {ans_str(ans)}"
            try:
                act = proc.send(ans)
                while act[0] == "note":
                    sim.perform(act)
                    act = proc.send(None)
            except StopIteration as e:
                tx.append(res_line)
                tx.append(f"end {e.value[0]} {e.value[1]}")
                break
            except ip.Failure as e:
                tx.append(res_line)
                tx.append(f"fail {categoria(str(e))}")
                break
            tx.append(res_line)
            tx.append("act " + act_str(act))
            ans = sim.perform(act)
    except ip.Failure as e:           # il mezzo (tempo massimo)
        tx.append(f"fail {categoria(str(e))}")
    for nome_f, righe in (("link_S", L["S"]), ("link_R", L["R"]), ("rx", L["rx"]), ("tx", L["tx"])):
        with open(os.path.join(out, f"{nome}.{nome_f}.txt"), "w") as f:
            f.write("\n".join(righe) + "\n")
    return sum(len(v) for v in L.values())


def ans_str(a):
    if a is None:
        return "none"
    if isinstance(a, bool):
        return f"bool:{int(a)}"
    if isinstance(a, float):
        return f"rand:{fx(a)}"
    return "frame:" + a["_raw"].hex()


def act_str(a):
    k = a[0]
    if k == "exchange":
        return f"exchange {a[1].hex()} {a[2]} {a[3]}"
    if k == "probe":
        return "probe " + ",".join(x.hex() for x in a[1])
    if k == "modeset":
        return f"modeset {a[1].hex()} {a[2]}"
    if k == "burst":
        return "burst " + ",".join(x.hex() for x in a[1])
    if k == "status":
        return f"status {a[1]} {a[2]}"
    if k == "wait":
        return f"wait {fx(a[1])}"
    if k in ("rand", "holdclear", "legacy", "oracle"):
        return k
    if k == "setrung":
        return f"setrung {a[1]}"
    raise ValueError(a)


def tutti_gli_scenari():
    """I nove scenari scelti a mano piu' tutti quelli del riferimento del simulatore (tools/golden_sim_immagini.py), tranne la vecchia ricerca che torna a R10 (il firmware non ce l'ha)."""
    import golden_sim_immagini as g
    sc = dict(SCENARI)
    for i, d in enumerate(g.scenari()):
        if d["ricerca"] == "calendario":
            sc[f"g{i:03d}"] = d
    return sc


def genera(out, completo=True):
    os.makedirs(out, exist_ok=True)
    n = {}
    scen = tutti_gli_scenari() if completo else SCENARI
    for nome, sc in scen.items():
        n[nome] = registra(nome, sc, out)
    with open(os.path.join(out, "lista.txt"), "w") as f:
        f.write("\n".join(scen) + "\n")
    return n


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "/tmp/tracce"
    r = genera(out, completo="--breve" not in sys.argv)
    print(f"tracce: {len(r)} scenari, {sum(r.values())} righe")
