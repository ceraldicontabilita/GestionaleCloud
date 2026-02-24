"""Cash Register Extended router - Additional endpoints."""
from fastapi import APIRouter, Depends, Query
from typing import Dict, Any
import logging

from app.database import Database, Collections
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/controllo-mensile",
    summary="Get monthly control"
)
async def get_controllo_mensile(
    year: int = Query(None),
    month: int = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get monthly cash register control."""
    from datetime import datetime, timezone
    import calendar
    
    year = year or datetime.now(timezone.utc).year
    month = month or datetime.now(timezone.utc).month
    
    db = Database.get_db()
    
    # 1. Date Range
    _, last_day = calendar.monthrange(year, month)
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{last_day}"
    
    # 2. Fetch Movements
    movements = await db[Collections.CASH_MOVEMENTS].find({
        "user_id": current_user["user_id"],
        "date": {"$gte": start_date, "$lte": end_date}
    }).to_list(10000)
    
    # 3. Process Data
    daily_stats = {}
    
    # Init stats for every day
    for day in range(1, last_day + 1):
        day_str = f"{year}-{month:02d}-{day:02d}"
        daily_stats[day_str] = {
            "date": day_str,
            "corrispettivi_manuale": 0.0,
            "corrispettivi_xml": 0.0,
            "pos_xml": 0.0,
            "pos_banca": 0.0,
            "annulli": 0.0
        }
        
    totals = {
        "corrispettivi_manuale": 0.0,
        "corrispettivi_xml": 0.0,
        "pos_xml": 0.0,
        "pos_banca": 0.0,
        "differenza_pos": 0.0,
        "annulli": 0.0
    }
    
    for m in movements:
        d = m.get("date")
        if d not in daily_stats:
            continue
            
        amount = m.get("amount", 0)
        cat = m.get("category", "")
        desc = m.get("description", "").lower()
        source = m.get("source", "manual") # manual, xml, bank
        
        # Logic to classify
        if cat == "Corrispettivo":
            if source == "xml" or "xml" in desc:
                daily_stats[d]["corrispettivi_xml"] += amount
                totals["corrispettivi_xml"] += amount
            else:
                daily_stats[d]["corrispettivi_manuale"] += amount
                totals["corrispettivi_manuale"] += amount
                
        elif cat == "POS":
            if source == "xml" or "xml" in desc:
                daily_stats[d]["pos_xml"] += amount
                totals["pos_xml"] += amount
            elif source == "bank" or "banca" in desc:
                daily_stats[d]["pos_banca"] += amount
                totals["pos_banca"] += amount
            else:
                # Assume manual POS is what user checks against XML?
                # Actually usually POS Manual (scontrino) vs POS Banca (accredito)
                # Let's map Manual POS to "pos_xml" (scontrino) equivalent for comparison against Bank?
                # Or "pos_xml" means "Electronic Invoice Data".
                # For now, let's map 'POS' manual to 'pos_xml' (scontrino)
                daily_stats[d]["pos_xml"] += amount
                totals["pos_xml"] += amount
                
        elif cat == "Annulli" or "annull" in desc:
            daily_stats[d]["annulli"] += amount
            totals["annulli"] += amount

    # Arrays for frontend
    corrispettivi_list = []
    pos_list = []
    annulli_list = []
    
    sorted_days = sorted(daily_stats.keys())
    
    for d in sorted_days:
        s = daily_stats[d]
        
        # Corrispettivi Row
        if s["corrispettivi_manuale"] > 0 or s["corrispettivi_xml"] > 0:
            corrispettivi_list.append({
                "date": d,
                "manuale": s["corrispettivi_manuale"],
                "xml": s["corrispettivi_xml"]
            })
            
        # POS Row
        if s["pos_xml"] > 0 or s["pos_banca"] > 0:
            pos_list.append({
                "date": d,
                "xml": s["pos_xml"],
                "banca": s["pos_banca"]
            })
            
        # Annulli Row
        if s["annulli"] > 0:
            annulli_list.append({
                "date": d,
                "xml": s["annulli"] # using xml field for amount
            })
            
    totals["differenza_pos"] = totals["pos_xml"] - totals["pos_banca"]
    
    return {
        "year": year,
        "month": month,
        "totals": totals,
        "corrispettivi": corrispettivi_list,
        "pos": pos_list,
        "annulli": annulli_list
    }
