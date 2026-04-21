"""
Script retroattivo: popola verbali_noleggio da Gmail + fatture XML storiche,
quindi collega fatture e ricerca pagamenti.

Esecuzione:
    cd /app && python -m scripts.popola_verbali_retroattivo
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import Database
from app.services.verbali_gmail_scanner import scan_gmail_verbali
from app.services.verbali_fattura_trigger import processa_fattura_per_verbali
from app.services.verbali_fattura_linker import collega_verbali_a_fatture
from app.services.verbali_pagamento_finder import (
    trova_pagamento_verbale,
    applica_pagamento_a_verbale,
)


async def main():
    await Database.connect_db()
    db = Database.get_db()

    print("1/4 Scan Gmail ultimo anno...")
    r1 = await scan_gmail_verbali(db, days_back=365)
    print(f"   {r1}")

    print("2/4 Trigger fatture XML esistenti (ARVAL/LEASYS/ALD/ALPHABET)...")
    stats = {"processate": 0, "creati": 0, "aggiornati": 0}
    cursor = db["invoices"].find({
        "$or": [
            {"fornitore_denominazione": {"$regex": "ARVAL|LEASYS|ALD|ALPHABET", "$options": "i"}},
            {"supplier_name": {"$regex": "ARVAL|LEASYS|ALD|ALPHABET", "$options": "i"}},
        ]
    })
    async for f in cursor:
        r = await processa_fattura_per_verbali(db, f)
        if not r.get("skip"):
            stats["processate"] += 1
            stats["creati"] += r.get("verbali_creati", 0)
            stats["aggiornati"] += r.get("verbali_aggiornati", 0)
    print(f"   {stats}")

    print("3/4 Link fatture ↔ verbali...")
    r3 = await collega_verbali_a_fatture(db)
    print(f"   {r3}")

    print("4/4 Ricerca pagamenti...")
    r4 = {"processati": 0, "riconciliati": 0}
    cursor = db["verbali_noleggio"].find({"riconciliato_paypal": {"$ne": True}})
    async for v in cursor:
        r4["processati"] += 1
        m = await trova_pagamento_verbale(db, v)
        if m:
            vid = v.get("id") or v.get("numero_verbale")
            ok = await applica_pagamento_a_verbale(db, vid, m)
            if ok:
                r4["riconciliati"] += 1
    print(f"   {r4}")


if __name__ == "__main__":
    asyncio.run(main())
