"""
FastAPI route handlers for Bland AI integration
"""

from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from director.core.config import Config
from director.core.exceptions import IntegrationError
from director.integrations.bland_ai.handler import BlandAIIntegrationHandler

router = APIRouter(prefix="/api/v1/bland-ai", tags=["bland-ai"])

class RecordingData(BaseModel):
    """Request model for sales recording data"""
    audio_url: str
    transcript: Optional[str] = None
    metadata: Optional[Dict] = None

class PathwayUpdateRequest(BaseModel):
    """Request model for updating an existing pathway"""
    recording_data: RecordingData
    pathway_id: str

async def get_integration_handler(config: Config = Depends()) -> BlandAIIntegrationHandler:
    """Dependency to get BlandAIIntegrationHandler instance"""
    return BlandAIIntegrationHandler(config)

@router.post("/process-recording")
async def process_recording(
    recording_data: RecordingData,
    handler: BlandAIIntegrationHandler = Depends(get_integration_handler)
) -> Dict:
    """Process a sales recording and create a new Bland AI pathway"""
    try:
        result = await handler.process_sales_recording(
            recording_data=recording_data.dict()
        )
        return result
    except IntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.post("/update-pathway")
async def update_pathway(
    request: PathwayUpdateRequest,
    handler: BlandAIIntegrationHandler = Depends(get_integration_handler)
) -> Dict:
    """Update an existing Bland AI pathway with new sales recording data"""
    try:
        result = await handler.process_sales_recording(
            recording_data=request.recording_data.dict(),
            update_existing=True,
            pathway_id=request.pathway_id
        )
        return result
    except IntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/pathways")
async def list_pathways(
    handler: BlandAIIntegrationHandler = Depends(get_integration_handler)
) -> List[Dict]:
    """Get list of available Bland AI pathways"""
    try:
        pathways = await handler.list_available_pathways()
        return pathways
    except IntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/pathways/{pathway_id}/stats")
async def get_pathway_stats(
    pathway_id: str,
    handler: BlandAIIntegrationHandler = Depends(get_integration_handler)
) -> Dict:
    """Get statistics about a specific pathway"""
    try:
        stats = await handler.get_pathway_stats(pathway_id)
        return stats
    except IntegrationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}") 