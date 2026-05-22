import logging
import os
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.etl.pipeline import (
    run_pipeline,
    run_domain_pipeline,
    process_file
)

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="ForestED Backend API",
    description="API for pedagogical data management",
    version="0.1.0"
)

# ==========================================
# HEALTH CHECK
# ==========================================

@app.get("/health", tags=["health"])
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "forested-backend"}

# ==========================================
# PIPELINE ENDPOINTS
# ==========================================

@app.post("/pipeline/run", tags=["pipeline"])
async def run_full_pipeline() -> Dict[str, Any]:
    """Run the complete ETL pipeline for all domains."""
    try:
        logger.info("Starting full ETL pipeline")
        run_pipeline()
        return {
            "status": "success",
            "message": "Pipeline completed successfully"
        }
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline failed: {str(e)}"
        )

@app.post("/pipeline/domain/{domain}", tags=["pipeline"])
async def run_domain_etl(domain: str) -> Dict[str, Any]:
    """Run ETL pipeline for a specific domain.
    
    Args:
        domain: Domain name (competence, curriculum, etc.)
    """
    if domain not in ["competence", "curriculum"]:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown domain: {domain}"
        )
    
    try:
        logger.info(f"Starting ETL pipeline for domain: {domain}")
        run_domain_pipeline(domain)
        return {
            "status": "success",
            "message": f"Pipeline for domain '{domain}' completed successfully"
        }
    except Exception as e:
        logger.error(f"Pipeline for {domain} failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline failed: {str(e)}"
        )

# ==========================================
# DATA ENDPOINTS
# ==========================================

@app.get("/competences", tags=["competence"])
async def get_competences() -> Dict[str, Any]:
    """Get processed competence data."""
    try:
        processed_file = Path("app/data/processed/competence")
        if not processed_file.exists():
            return {
                "status": "no_data",
                "message": "No processed competence data available. Run pipeline first."
            }
        
        import json
        files = list(processed_file.glob("*.json"))
        
        if not files:
            return {"status": "empty", "data": []}
        
        data = {}
        for file in files:
            with open(file, "r", encoding="utf-8") as f:
                data[file.stem] = json.load(f)
        
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error(f"Error retrieving competences: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving data: {str(e)}"
        )

@app.get("/curricula", tags=["curriculum"])
async def get_curricula() -> Dict[str, Any]:
    """Get processed curriculum data."""
    try:
        processed_file = Path("app/data/processed/curriculum")
        if not processed_file.exists():
            return {
                "status": "no_data",
                "message": "No processed curriculum data available. Run pipeline first."
            }
        
        import json
        files = list(processed_file.glob("*.json"))
        
        if not files:
            return {"status": "empty", "data": []}
        
        data = {}
        for file in files:
            with open(file, "r", encoding="utf-8") as f:
                data[file.stem] = json.load(f)
        
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error(f"Error retrieving curricula: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving data: {str(e)}"
        )

@app.get("/analytics/{domain}", tags=["analytics"])
async def get_analytics(domain: str) -> Dict[str, Any]:
    """Get flattened analytics data for a domain."""
    if domain not in ["competence", "curriculum"]:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown domain: {domain}"
        )
    
    try:
        analytics_file = Path("app/data/analytics") / domain
        if not analytics_file.exists():
            return {
                "status": "no_data",
                "message": f"No analytics data available for domain '{domain}'. Run pipeline first."
            }
        
        import json
        files = list(analytics_file.glob("*.json"))
        
        if not files:
            return {"status": "empty", "data": []}
        
        data = {}
        for file in files:
            with open(file, "r", encoding="utf-8") as f:
                data[file.stem] = json.load(f)
        
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error(f"Error retrieving analytics for {domain}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving data: {str(e)}"
        )

# ==========================================
# ERROR HANDLERS
# ==========================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

# ==========================================
# STARTUP/SHUTDOWN
# ==========================================

@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    logger.info("ForestED Backend started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("ForestED Backend stopped")

if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    
    logger.info(f"Starting server on {host}:{port}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )
