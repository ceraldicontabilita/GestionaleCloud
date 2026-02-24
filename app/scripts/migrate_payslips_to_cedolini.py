"""
Script di Migrazione: Unificazione Collection cedolini/payslips
================================================================

Questo script:
1. Legge tutti i record da 'payslips'
2. Li converte nel formato 'cedolini'
3. Li inserisce in 'cedolini' evitando duplicati
4. Mantiene 'payslips' per retrocompatibilità (non elimina)

Eseguire con: python -m app.scripts.migrate_payslips_to_cedolini
"""
import asyncio
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_payslips_to_cedolini():
    """Migra i record da payslips a cedolini."""
    from app.database import Database
    
    # Inizializza connessione DB
    await Database.connect_db()
    db = Database.get_db()
    
    print("=" * 60)
    print("MIGRAZIONE payslips → cedolini")
    print("=" * 60)
    
    # 1. Conta record
    payslips_count = await db["payslips"].count_documents({})
    cedolini_count = await db["cedolini"].count_documents({})
    
    print("\n📊 Stato attuale:")
    print(f"   - payslips: {payslips_count} record")
    print(f"   - cedolini: {cedolini_count} record")
    
    if payslips_count == 0:
        print("\n✅ Nessun record in payslips da migrare")
        return {"migrated": 0, "skipped": 0, "errors": 0}
    
    # 2. Leggi tutti i payslips
    payslips = await db["payslips"].find({}, {"_id": 0}).to_list(10000)
    
    migrated = 0
    skipped = 0
    errors = 0
    
    print("\n🔄 Migrazione in corso...")
    
    for ps in payslips:
        try:
            # Estrai dati
            cf = ps.get("codice_fiscale", "")
            mese = ps.get("mese")
            anno = ps.get("anno")
            
            # Se manca mese/anno, prova a estrarlo dal periodo
            if not mese or not anno:
                periodo = ps.get("periodo", "")
                if "/" in periodo:
                    parts = periodo.split("/")
                    if len(parts) == 2:
                        try:
                            mese = int(parts[0])
                            anno = int(parts[1])
                        except:
                            pass
            
            if not cf or not mese or not anno:
                logger.warning(f"Record payslip senza dati chiave: CF={cf}, mese={mese}, anno={anno}")
                errors += 1
                continue
            
            # Controlla se esiste già in cedolini
            existing = await db["cedolini"].find_one({
                "codice_fiscale": cf,
                "mese": mese,
                "anno": anno
            })
            
            if existing:
                skipped += 1
                continue
            
            # Converti nel formato cedolini
            cedolino = {
                "id": ps.get("id", ps.get("payslip_id", str(datetime.now().timestamp()))),
                "dipendente_id": ps.get("dipendente_id", ps.get("employee_id")),
                "codice_fiscale": cf,
                "nome_dipendente": ps.get("nome_completo", f"{ps.get('cognome', '')} {ps.get('nome', '')}".strip()),
                "mese": mese,
                "anno": anno,
                "periodo": f"{mese:02d}/{anno}" if isinstance(mese, int) and isinstance(anno, int) else ps.get("periodo", ""),
                # Retribuzione
                "lordo": ps.get("retribuzione_lorda", ps.get("lordo", 0)),
                "netto_mese": ps.get("retribuzione_netta", ps.get("netto", 0)),
                "totale_trattenute": ps.get("totale_trattenute", 0),
                # Dettagli
                "ore_lavorate": ps.get("ore_ordinarie", ps.get("ore_lavorate", 0)),
                "qualifica": ps.get("qualifica", ""),
                "livello": ps.get("livello", ""),
                "iban": ps.get("iban"),
                # TFR
                "tfr_quota": ps.get("tfr_quota", ps.get("tfr", 0)),
                # Metadati
                "source": "migrated_from_payslips",
                "original_payslip_id": ps.get("id", ps.get("payslip_id")),
                "filename": ps.get("filename"),
                "created_at": ps.get("created_at", datetime.now(timezone.utc).isoformat()),
                "migrated_at": datetime.now(timezone.utc).isoformat()
            }
            
            # Rimuovi campi None
            cedolino = {k: v for k, v in cedolino.items() if v is not None}
            
            await db["cedolini"].insert_one(cedolino.copy())
            migrated += 1
            
        except Exception as e:
            logger.error(f"Errore migrazione record: {e}")
            errors += 1
    
    print("\n✅ Migrazione completata:")
    print(f"   - Migrati: {migrated}")
    print(f"   - Saltati (duplicati): {skipped}")
    print(f"   - Errori: {errors}")
    
    # Conteggio finale
    cedolini_count_after = await db["cedolini"].count_documents({})
    print(f"\n📊 Stato finale cedolini: {cedolini_count_after} record")
    
    return {"migrated": migrated, "skipped": skipped, "errors": errors}


if __name__ == "__main__":
    asyncio.run(migrate_payslips_to_cedolini())
