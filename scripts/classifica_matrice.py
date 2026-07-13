"""
Classificatore matrice API — audit canonico Fase C.

Legge memoria/AUDIT_MATRICE_DATI.json (prodotto da estrai_matrice_api.py)
e genera memoria/AUDIT_MATRICE.md con:
- riepilogo numerico
- endpoint duplicati (stesso metodo+path normalizzato registrato piu' volte)
- classificazione di ogni endpoint:
    ATTIVO        chiamato dal frontend
    INTEGRAZIONE  superficie per app/servizi esterni (erp_bridge, public_api,
                  webhook, websocket, openapi)
    MANUTENZIONE  admin/batch/rollback/auto-repair: uso manuale od occasionale
    SISTEMA       health/ping/lock/root
    DA_VERIFICARE tutto il resto: orfano senza categoria nota (candidato
                  legacy/eliminabile, decide l'utente)

Uso:  python scripts/estrai_matrice_api.py && python scripts/classifica_matrice.py
"""
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATI = ROOT / "memoria" / "AUDIT_MATRICE_DATI.json"
DEST = ROOT / "memoria" / "AUDIT_MATRICE.md"

INTEGRAZIONE_MODULI = (
    "erp_bridge", "public_api", "openapi", "websocket", "webhook", "pagopa",
)
MANUTENZIONE_MODULI = (
    "admin", "admin_rollback", "batch_reprocessing", "auto_repair",
    "sync_relazionale", "rapido",
)
SISTEMA_NOMI = ("health", "ping", "root", "lock_status", "read_root")


def norm(path: str) -> str:
    return re.sub(r"\{[^}]*\}", "{P}", path)


def classifica(r, usati):
    key = (tuple(r["methods"]), r["path"])
    if key in usati:
        return "ATTIVO"
    mod = r["module"].rsplit(".", 1)[-1]
    if any(m in mod for m in INTEGRAZIONE_MODULI):
        return "INTEGRAZIONE"
    if any(mod == m or mod.startswith(m) for m in MANUTENZIONE_MODULI):
        return "MANUTENZIONE"
    if r["name"] in SISTEMA_NOMI or mod == "main":
        return "SISTEMA"
    return "DA_VERIFICARE"


def main():
    d = json.loads(DATI.read_text())
    routes = d["endpoint_backend"]
    orfani_keys = {(tuple(r["methods"]), r["path"]) for r in d["endpoint_orfani"]}
    usati = {(tuple(r["methods"]), r["path"]) for r in routes} - orfani_keys

    # Duplicati: stesso (metodo, path normalizzato) da piu' handler
    per_chiave = defaultdict(list)
    for r in routes:
        for m in r["methods"]:
            per_chiave[(m, norm(r["path"]))].append(r)
    duplicati = {k: v for k, v in per_chiave.items() if len({(x["file"], x["line"]) for x in v}) > 1}

    # Classifica
    per_classe = defaultdict(list)
    per_modulo = defaultdict(lambda: defaultdict(int))
    for r in routes:
        c = classifica(r, usati)
        r["classe"] = c
        per_classe[c].append(r)
        per_modulo[r["module"].replace("app.routers.", "")][c] += 1

    righe = []
    righe.append("# Matrice API — Audit canonico Fase C\n")
    righe.append("Generato da `scripts/estrai_matrice_api.py` + `scripts/classifica_matrice.py`.")
    righe.append("Dati grezzi (ogni chiamata frontend con file:riga e ogni endpoint con file:riga):")
    righe.append("`memoria/AUDIT_MATRICE_DATI.json`.\n")

    righe.append("## Riepilogo\n")
    righe.append(f"- Endpoint backend registrati: **{len(routes)}**")
    righe.append(f"- Chiamate API nel frontend: **{d['totale_chiamate_frontend']}**")
    righe.append(f"- Chiamate frontend senza endpoint (ROTTE): **{len(d['chiamate_rotte'])}** (vedi sotto)")
    for c in ("ATTIVO", "INTEGRAZIONE", "MANUTENZIONE", "SISTEMA", "DA_VERIFICARE"):
        righe.append(f"- {c}: **{len(per_classe[c])}**")
    righe.append(f"- Coppie (metodo, path) duplicate: **{len(duplicati)}**\n")

    # Falsi positivi verificati a mano (13/07/2026)
    NOTE_ROTTE = {
        ("POST", "/api/invoices"): "helper `createInvoice` in api.js MAI importato da nessuna pagina: codice morto, non un bottone rotto",
        ("POST", "/api/prima-nota-banca/crea"): "chiamata dentro un blocco COMMENTATO in RiconciliazioneUnificata.jsx: non eseguita",
    }
    righe.append("## Chiamate frontend senza endpoint\n")
    if d["chiamate_rotte"]:
        for c in d["chiamate_rotte"]:
            nota = NOTE_ROTTE.get((c["method"], c["norm"]))
            suffisso = f" — FALSO POSITIVO: {nota}" if nota else ""
            righe.append(f"- `{c['method']} {c['norm']}` — {c['file']}:{c['line']}{suffisso}")
        if all((c["method"], c["norm"]) in NOTE_ROTTE for c in d["chiamate_rotte"]):
            righe.append("\n**Nessun bottone/pagina chiama davvero un endpoint inesistente.**")
    else:
        righe.append("Nessuna.")
    righe.append("")

    righe.append("## Endpoint duplicati (stesso metodo+path da handler diversi)\n")
    if duplicati:
        for (m, p), rs in sorted(duplicati.items()):
            righe.append(f"- `{m} {p}`")
            for r in rs:
                righe.append(f"    - {r['file']}:{r['line']} `{r['name']}` [{r['module']}]")
    else:
        righe.append("Nessuno.")
    righe.append("")

    righe.append("## Endpoint per modulo router\n")
    righe.append("| Modulo | Attivi | Integrazione | Manutenzione | Sistema | Da verificare | Tot |")
    righe.append("|---|---|---|---|---|---|---|")
    for mod in sorted(per_modulo, key=lambda m: -sum(per_modulo[m].values())):
        cc = per_modulo[mod]
        tot = sum(cc.values())
        righe.append(
            f"| {mod} | {cc.get('ATTIVO',0)} | {cc.get('INTEGRAZIONE',0)} | "
            f"{cc.get('MANUTENZIONE',0)} | {cc.get('SISTEMA',0)} | {cc.get('DA_VERIFICARE',0)} | {tot} |"
        )
    righe.append("")

    righe.append("## Endpoint DA VERIFICARE (orfani senza categoria nota)\n")
    righe.append("Nessuna pagina li chiama e non appartengono a integrazione/manutenzione/sistema.")
    righe.append("Candidati legacy: la rimozione va decisa caso per caso.\n")
    per_mod_dv = defaultdict(list)
    for r in per_classe["DA_VERIFICARE"]:
        per_mod_dv[r["module"].replace("app.routers.", "")].append(r)
    for mod in sorted(per_mod_dv, key=lambda m: -len(per_mod_dv[m])):
        righe.append(f"### {mod} ({len(per_mod_dv[mod])})")
        for r in sorted(per_mod_dv[mod], key=lambda x: x["path"]):
            metodi = ",".join(r["methods"])
            righe.append(f"- `{metodi} {r['path']}` — {r['file']}:{r['line']}")
        righe.append("")

    DEST.write_text("\n".join(righe))
    print(f"Scritto {DEST.relative_to(ROOT)} ({len(righe)} righe)")
    print({c: len(v) for c, v in per_classe.items()})
    print(f"duplicati: {len(duplicati)}")


if __name__ == "__main__":
    main()
