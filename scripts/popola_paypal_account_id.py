"""
Script retroattivo: popola il campo anagrafica.paypal_account_id sui fornitori
partendo dalle transazioni PayPal esistenti.

Strategia:
1. Raggruppa paypal_transactions per paypal_account_id.
2. Per ciascun account_id, trova la fattura con invoice_id_fornitore matching.
3. Se trovato un fornitore coerente, aggiunge paypal_account_id in anagrafica.
"""
import asyncio
import sys
from pathlib import Path

# path fix per import relativi
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import Database


async def main():
    await Database.connect_db()
    db = Database.get_db()

    print("🔍 Scansione paypal_transactions in corso...")
    pipeline = [
        {"$match": {"paypal_account_id": {"$ne": None}, "invoice_id_fornitore": {"$ne": None}}},
        {"$group": {
            "_id": "$paypal_account_id",
            "invoice_id": {"$first": "$invoice_id_fornitore"},
            "n": {"$sum": 1},
        }},
    ]
    mappings = await db["paypal_transactions"].aggregate(pipeline).to_list(None)
    print(f"   {len(mappings)} account PayPal candidati")

    popolati = 0
    for m in mappings:
        account_id = m["_id"]
        invoice_id = m["invoice_id"]
        # trova la fattura (supplier lookup)
        fatt = await db["invoices"].find_one(
            {"$or": [{"invoice_number": invoice_id}, {"numero_documento": invoice_id},
                     {"id": invoice_id}]},
            {"supplier_vat": 1, "fornitore_partita_iva": 1, "supplier_name": 1,
             "fornitore_denominazione": 1, "fornitore_id": 1, "_id": 0},
        )
        if not fatt:
            continue
        piva = fatt.get("supplier_vat") or fatt.get("fornitore_partita_iva")
        if not piva:
            continue
        res = await db["fornitori"].update_one(
            {"$or": [{"anagrafica.piva": piva}, {"piva": piva},
                     {"partita_iva": piva}, {"anagrafica.partita_iva": piva}]},
            {"$set": {"paypal_account_id": account_id}}
        )
        if res.modified_count:
            popolati += 1
            print(f"  ✓ {piva}: account {account_id} (da {m['n']} tx)")

    print(f"\n✅ Popolati {popolati} fornitori")


if __name__ == "__main__":
    asyncio.run(main())
