from fastapi import APIRouter
from .downloads.router import router as downloads_router

router = APIRouter()

# Include the downloads router with the correct prefix
router.include_router(downloads_router, prefix="/downloads")

@router.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {"status": "ok"} 