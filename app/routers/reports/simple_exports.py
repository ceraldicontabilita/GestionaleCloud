"""
Simple Export Router - Export data without authentication
"""
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import date, datetime
import io
import logging

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/invoices",
    summary="Export fatture"
)
async def export_invoices(
    format: str = Query("xlsx", description="Formato: xlsx o json")
):
    """Export fatture in Excel o JSON."""
    db = Database.get_db()
    
    invoices = await db["invoices"].find({}, {"_id": 0}).sort("data_fattura", -1).to_list(10000)
    
    if format == "json":
        return {"invoices": invoices, "count": len(invoices)}
    
    # Excel export
    import pandas as pd
    df = pd.DataFrame(invoices)
    if df.empty:
        df = pd.DataFrame(columns=["numero_fattura", "data_fattura", "cedente_denominazione", "importo_totale"])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Fatture", index=False)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=fatture_{date.today()}.xlsx"}
    )


@router.get(
    "/suppliers",
    summary="Export fornitori"
)
async def export_suppliers(
    format: str = Query("xlsx")
):
    """Export fornitori in Excel o JSON."""
    db = Database.get_db()
    
    suppliers = await db["suppliers"].find({}, {"_id": 0}).sort("denominazione", 1).to_list(5000)
    
    if format == "json":
        return {"suppliers": suppliers, "count": len(suppliers)}
    
    import pandas as pd
    df = pd.DataFrame(suppliers)
    if df.empty:
        df = pd.DataFrame(columns=["denominazione", "partita_iva", "codice_fiscale"])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Fornitori", index=False)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=fornitori_{date.today()}.xlsx"}
    )


@router.get(
    "/products",
    summary="Export prodotti magazzino"
)
async def export_products(
    format: str = Query("xlsx")
):
    """Export prodotti magazzino."""
    db = Database.get_db()
    
    products = await db["warehouse_products"].find({}, {"_id": 0}).sort("nome", 1).to_list(10000)
    
    if format == "json":
        return {"products": products, "count": len(products)}
    
    import pandas as pd
    df = pd.DataFrame(products)
    if df.empty:
        df = pd.DataFrame(columns=["codice", "nome", "prezzo", "quantita"])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Prodotti", index=False)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=prodotti_{date.today()}.xlsx"}
    )


@router.get(
    "/employees",
    summary="Export dipendenti"
)
async def export_employees(
    format: str = Query("xlsx")
):
    """Export dipendenti."""
    db = Database.get_db()
    
    employees = await db["employees"].find({}, {"_id": 0}).sort("nome_completo", 1).to_list(1000)
    
    if format == "json":
        return {"employees": employees, "count": len(employees)}
    
    import pandas as pd
    df = pd.DataFrame(employees)
    if df.empty:
        df = pd.DataFrame(columns=["nome_completo", "codice_fiscale", "qualifica"])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Dipendenti", index=False)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=dipendenti_{date.today()}.xlsx"}
    )


@router.get(
    "/cash",
    summary="Export Prima Nota Cassa"
)
async def export_cash(
    format: str = Query("xlsx"),
    data_da: Optional[str] = None,
    data_a: Optional[str] = None
):
    """Export Prima Nota Cassa."""
    db = Database.get_db()
    
    query = {}
    if data_da:
        query["data"] = {"$gte": data_da}
    if data_a:
        query.setdefault("data", {})["$lte"] = data_a
    
    movements = await db["prima_nota_cassa"].find(query, {"_id": 0}).sort("data", -1).to_list(10000)
    
    if format == "json":
        return {"movements": movements, "count": len(movements)}
    
    import pandas as pd
    df = pd.DataFrame(movements)
    if df.empty:
        df = pd.DataFrame(columns=["data", "tipo", "importo", "descrizione", "categoria"])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Prima Nota Cassa", index=False)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=prima_nota_cassa_{date.today()}.xlsx"}
    )


@router.get(
    "/bank",
    summary="Export Prima Nota Banca"
)
async def export_bank(
    format: str = Query("xlsx"),
    data_da: Optional[str] = None,
    data_a: Optional[str] = None
):
    """Export Prima Nota Banca."""
    db = Database.get_db()
    
    query = {}
    if data_da:
        query["data"] = {"$gte": data_da}
    if data_a:
        query.setdefault("data", {})["$lte"] = data_a
    
    movements = await db["prima_nota_banca"].find(query, {"_id": 0}).sort("data", -1).to_list(10000)
    
    if format == "json":
        return {"movements": movements, "count": len(movements)}
    
    import pandas as pd
    df = pd.DataFrame(movements)
    if df.empty:
        df = pd.DataFrame(columns=["data", "tipo", "importo", "descrizione", "categoria"])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Prima Nota Banca", index=False)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=prima_nota_banca_{date.today()}.xlsx"}
    )


@router.get(
    "/salari",
    summary="Export Prima Nota Salari"
)
async def export_salari(
    format: str = Query("xlsx"),
    data_da: Optional[str] = None,
    data_a: Optional[str] = None
):
    """Export Prima Nota Salari."""
    db = Database.get_db()
    
    query = {}
    if data_da:
        query["data"] = {"$gte": data_da}
    if data_a:
        query.setdefault("data", {})["$lte"] = data_a
    
    movements = await db["prima_nota_salari"].find(query, {"_id": 0}).sort("data", -1).to_list(10000)
    
    if format == "json":
        return {"movements": movements, "count": len(movements)}
    
    import pandas as pd
    df = pd.DataFrame(movements)
    if df.empty:
        df = pd.DataFrame(columns=["data", "importo", "nome_dipendente", "periodo"])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Prima Nota Salari", index=False)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=prima_nota_salari_{date.today()}.xlsx"}
    )


@router.get(
    "/haccp",
    summary="Export HACCP Temperature"
)
async def export_haccp(
    format: str = Query("xlsx")
):
    """Export registrazioni HACCP."""
    db = Database.get_db()
    
    records = await db["haccp_temperatures"].find({}, {"_id": 0}).sort("timestamp", -1).to_list(10000)
    
    if format == "json":
        return {"records": records, "count": len(records)}
    
    import pandas as pd
    df = pd.DataFrame(records)
    if df.empty:
        df = pd.DataFrame(columns=["timestamp", "zona", "temperatura", "operatore"])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="HACCP", index=False)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=haccp_{date.today()}.xlsx"}
    )


@router.get(
    "/riconciliazione",
    summary="Export Riconciliazione Bancaria"
)
async def export_riconciliazione(
    format: str = Query("xlsx"),
    solo_non_riconciliati: bool = Query(False, description="Esporta solo movimenti non riconciliati")
):
    """Export stato riconciliazione Prima Nota Banca con estratto conto."""
    db = Database.get_db()
    
    query = {}
    if solo_non_riconciliati:
        query["riconciliato"] = {"$ne": True}
    
    movements = await db["prima_nota_banca"].find(query, {"_id": 0}).sort("data", -1).to_list(10000)
    
    # Enrich with reconciliation status
    for m in movements:
        m["stato_riconciliazione"] = "Riconciliato" if m.get("riconciliato") else "Non riconciliato"
        m["data_riconciliazione"] = m.get("data_riconciliazione", "")
        m["riferimento_estratto_conto"] = m.get("estratto_conto_ref", "")
    
    # Get summary stats
    total = len(movements)
    reconciled = sum(1 for m in movements if m.get("riconciliato"))
    
    if format == "json":
        return {
            "movements": movements, 
            "count": total,
            "reconciled": reconciled,
            "not_reconciled": total - reconciled
        }
    
    import pandas as pd
    
    # Main movements sheet
    df_movements = pd.DataFrame(movements)
    if df_movements.empty:
        df_movements = pd.DataFrame(columns=[
            "data", "tipo", "importo", "descrizione", "categoria",
            "stato_riconciliazione", "data_riconciliazione", "riferimento_estratto_conto"
        ])
    
    # Summary sheet
    summary_data = {
        "Metrica": [
            "Totale Movimenti Banca",
            "Movimenti Riconciliati",
            "Movimenti Non Riconciliati",
            "Percentuale Riconciliazione",
            "Data Export"
        ],
        "Valore": [
            total,
            reconciled,
            total - reconciled,
            f"{round((reconciled/total*100) if total > 0 else 0, 1)}%",
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ]
    }
    df_summary = pd.DataFrame(summary_data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_summary.to_excel(writer, sheet_name="Riepilogo", index=False)
        df_movements.to_excel(writer, sheet_name="Movimenti", index=False)
    output.seek(0)
    
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=riconciliazione_{date.today()}.xlsx"}
    )

