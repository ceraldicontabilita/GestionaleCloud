"""
IVA Router - New API Endpoints
Provides monthly, annual, F24, and comparison endpoints for VAT management
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from pathlib import Path
import logging
import os

# Import services (relative to backend/)
from services.iva import IVACalculator, IVAReportService

logger = logging.getLogger(__name__)

# Create router
iva_router = APIRouter(prefix="/iva", tags=["IVA Extended"])

# PDF storage directory (climb 3 levels: routers -> api -> backend)
BASE_DIR = Path(__file__).resolve().parents[2]
PDF_DIR = BASE_DIR / "documents" / "iva_reports"


# Dependency to get database (will be injected from server_complete.py)
async def get_db_dependency():
    """Database dependency - to be overridden by server_complete.py"""
    raise HTTPException(status_code=500, detail="Database not configured")


# Dependency for current user
async def get_current_user_dependency():
    """User dependency - to be overridden by server_complete.py"""
    return "admin"


@iva_router.get("/mese/{year}/{month}")
async def get_monthly_iva(
    year: int,
    month: int,
    db=Depends(get_db_dependency),
    username: str = Depends(get_current_user_dependency)
):
    """
    Get IVA liquidation for specific month with optional PDF generation
    
    Args:
        year: Year (e.g., 2025)
        month: Month (1-12)
        
    Returns:
        Monthly IVA calculation with breakdown
    """
    try:
        if not (1 <= month <= 12):
            raise HTTPException(status_code=400, detail="Month must be between 1 and 12")
        
        # Initialize service
        report_service = IVAReportService(db)
        
        # Generate report with PDF
        result = await report_service.generate_monthly_report_with_pdf(
            year=year,
            month=month,
            user_id=username
        )
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Error generating report"))
        
        return {
            "success": True,
            "period": f"{year}-{month:02d}",
            "data": result["data"],
            "pdf_available": True,
            "pdf_filename": result["pdf_filename"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in monthly IVA endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@iva_router.get("/anno/{year}")
async def get_annual_iva(
    year: int,
    db=Depends(get_db_dependency),
    username: str = Depends(get_current_user_dependency)
):
    """
    Get complete annual IVA report with monthly breakdown and PDF
    
    Args:
        year: Year (e.g., 2025)
        
    Returns:
        Annual IVA summary with monthly breakdown and PDF
    """
    try:
        # Initialize service
        report_service = IVAReportService(db)
        
        # Generate annual report with PDF
        result = await report_service.generate_annual_report_with_pdf(
            year=year,
            user_id=username
        )
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Error generating report"))
        
        return {
            "success": True,
            "year": year,
            "summary": {
                "total_iva_acquisti": result["data"]["total_iva_acquisti"],
                "total_iva_vendite": result["data"]["total_iva_vendite"],
                "total_iva_dovuta": result["data"]["total_iva_dovuta"],
                "total_imponibile_acquisti": result["data"]["total_imponibile_acquisti"],
                "total_imponibile_vendite": result["data"]["total_imponibile_vendite"]
            },
            "monthly_breakdown": result["data"]["monthly_breakdown"],
            "pdf_available": True,
            "pdf_filename": result["pdf_filename"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in annual IVA endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@iva_router.get("/f24/{year}")
async def get_f24_for_year(
    year: int,
    db=Depends(get_db_dependency),
    username: str = Depends(get_current_user_dependency)
):
    """
    Get all F24 forms for a specific year
    
    Args:
        year: Year (e.g., 2025)
        
    Returns:
        List of F24 documents (Erario + Contributi) for the year
    """
    try:
        # Initialize calculator
        calculator = IVACalculator(db)
        
        # Get F24 data
        f24_list = await calculator.get_f24_for_year(year, username)
        
        # Aggregate totals by type
        total_erario = sum(
            float(f24.get("importo_totale", 0))
            for f24 in f24_list
            if f24.get("type") == "erario"
        )
        
        total_contributi = sum(
            float(f24.get("importo_totale", 0))
            for f24 in f24_list
            if f24.get("type") == "contributi"
        )
        
        return {
            "success": True,
            "year": year,
            "f24_count": len(f24_list),
            "totals": {
                "erario": round(total_erario, 2),
                "contributi": round(total_contributi, 2),
                "total": round(total_erario + total_contributi, 2)
            },
            "f24_list": f24_list
        }
        
    except Exception as e:
        logger.error(f"Error getting F24 for year: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@iva_router.get("/confronto/{year}")
async def get_year_comparison(
    year: int,
    db=Depends(get_db_dependency),
    username: str = Depends(get_current_user_dependency)
):
    """
    Get year-over-year IVA comparison
    
    Args:
        year: Current year for comparison (will compare with year-1)
        
    Returns:
        Comparison data between current and previous year with delta and percentages
    """
    try:
        # Initialize calculator
        calculator = IVACalculator(db)
        
        # Get comparison data
        comparison = await calculator.calculate_comparison(year, username)
        
        return {
            "success": True,
            "comparison": comparison
        }
        
    except Exception as e:
        logger.error(f"Error calculating year comparison: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@iva_router.get("/download/{filename}")
async def download_pdf(filename: str):
    """
    Download generated IVA PDF report
    
    Args:
        filename: PDF filename (e.g., liquidazione_iva_2025_11.pdf)
        
    Returns:
        PDF file
    """
    try:
        # Sanitize filename to prevent directory traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        
        file_path = PDF_DIR / filename
        
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"PDF file not found: {filename}")
        
        return FileResponse(
            path=file_path,
            media_type="application/pdf",
            filename=filename
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading PDF: {e}")
        raise HTTPException(status_code=500, detail=str(e))
