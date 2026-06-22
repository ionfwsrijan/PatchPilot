from fastapi import APIRouter, HTTPException
from ..models import Finding
from .engine import analyze_root_cause

router = APIRouter()

@router.get("/jobs/{job_id}/root-cause-groups", response_model=dict)
async def get_root_cause_groups(job_id: str):
    """Return root cause grouping for a given job.

    The response matches the structure of ``RootCauseResponse`` defined in
    ``backend/app/ml/root_cause/models.py`` but is returned as a plain dict for
    simplicity in FastAPI serialization.
    """
    try:
        result = await analyze_root_cause(job_id)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
