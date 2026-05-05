"""Inferisce metodo_pagamento_predefinito di ogni fornitore usando i PAGAMENTI REALI
registrati sulle sue fatture (prima_nota_cassa_id / prima_nota_banca_id).

Regola:
  Per ogni fornitore (P.IVA), conta le fatture pagate con cassa_id o banca_id.
  Se solo cassa_id   -> "contanti"
  Se solo banca_id   -> "bonifico"
  Se entrambi:
    - >= 80% cassa -> "contanti"
    - >= 80% banca -> "bonifico"
    - altrimenti   -> "misto"
  Se nessun pagamento registrato:
    - guarda il metodo XML dichiarato dal cedente (fallback debole)
    - normalizza
    - se non disponibile: lascia vuoto (utente sceglierà manualmente)
"""
import re, os
from datetime import datetime, timezone
from collections import Counter

for line in open('/app/backend/.env'):
    m = re.match(r'^([A-Z_]+)\s*=\s*"?([^"\n]+?)"?\s*$', line.strip())
    if m: os.environ[m.group(1)] = m.group(2)

from pymongo import MongoClient
c = MongoClient(os.environ['MONGO_URL'])
db = c['Gestionale']

def normalize_xml(m):
    if not m: return ""
    s = m.strip().lower()
    if s in ("bonifico","banca","bank_transfer","bonifico bancario","sepa"): return "bonifico"
    if s in ("rid","sdd","addebito"): return "rid"
    if s in ("contanti","cassa","cash"): return "contanti"
    if s in ("assegno","assegno bancario"): return "assegno"
    if s in ("carta","carta di credito","pos"): return "carta"
    if s in ("paypal",): return "PayPal"
    return ""  # ignora misto e altri valori sospetti

fornitori = list(db.fornitori.find({}, {"_id":0,"id":1,"partita_iva":1,"denominazione":1}))
print(f"Totale fornitori: {len(fornitori)}\n")

now_iso = datetime.now(timezone.utc).isoformat()
agg = 0
log = []

for fr in fornitori:
    piva = (fr.get("partita_iva") or "").strip()
    if not piva: continue

    # 1. PAGAMENTI REALI: conta fatture con cassa_id e con banca_id
    n_cassa = db.invoices.count_documents({"supplier_vat": piva, "prima_nota_cassa_id": {"$exists": True, "$nin": [None, ""]}})
    n_banca = db.invoices.count_documents({"supplier_vat": piva, "prima_nota_banca_id": {"$exists": True, "$nin": [None, ""]}})
    tot_pagate = n_cassa + n_banca
    
    if tot_pagate >= 1:
        # Almeno un pagamento reale -> usa quello
        if n_banca == 0:
            new_metodo = "contanti"
        elif n_cassa == 0:
            new_metodo = "bonifico"
        else:
            pct_cassa = n_cassa / tot_pagate
            pct_banca = n_banca / tot_pagate
            if pct_cassa >= 0.80:
                new_metodo = "contanti"
            elif pct_banca >= 0.80:
                new_metodo = "bonifico"
            else:
                new_metodo = "misto"
        source = f"prima_nota (cassa:{n_cassa}, banca:{n_banca})"
    else:
        # Nessun pagamento reale -> fallback XML
        xml_metodi = Counter()
        for inv in db.invoices.find({"supplier_vat": piva}, {"_id":0,"metodo_pagamento":1,"payment_method":1}):
            v = normalize_xml(inv.get("metodo_pagamento") or inv.get("payment_method") or "")
            if v: xml_metodi[v] += 1
        if xml_metodi:
            top, top_n = xml_metodi.most_common(1)[0]
            tot = sum(xml_metodi.values())
            if top_n / tot >= 0.70:
                new_metodo = top
                source = f"xml_dominante ({top_n}/{tot}, {100*top_n//tot}%)"
            else:
                new_metodo = "misto"
                source = f"xml_misto"
        else:
            new_metodo = ""
            source = "no_data"

    db.fornitori.update_one(
        {"id": fr["id"]},
        {"$set": {
            "metodo_pagamento": new_metodo,
            "metodo_pagamento_predefinito": new_metodo,
            "metodo_pagamento_inferred": True,
            "metodo_pagamento_inferred_source": source,
            "updated_at": now_iso,
        }}
    )
    if new_metodo:
        agg += 1
    log.append((piva, fr.get("denominazione",""), new_metodo, n_cassa, n_banca, source))

print(f"Aggiornati: {agg}/{len(fornitori)}\n")

# Esempi specifici
print("=== Esempi specifici (fornitori importanti) ===")
target_pivas = ["07593261212","05157530634","04172800155","06714021000","15844561009",
                "01992440618","04518411212","04104640612","01238591216"]
for piva, denom, nm, nc, nb, src in log:
    if piva in target_pivas:
        print(f"  {piva:14s} {denom[:40]:40s} → {nm or '(vuoto)':<10s}  [{src}]")

print("\n=== STATO FINALE ===")
mc = Counter()
for f in db.fornitori.find({}, {"_id":0,"metodo_pagamento":1,"metodo_pagamento_predefinito":1}):
    m = f.get("metodo_pagamento_predefinito") or f.get("metodo_pagamento") or "(vuoto)"
    mc[m] += 1
for m, n in mc.most_common():
    print(f"  {m}: {n}")
