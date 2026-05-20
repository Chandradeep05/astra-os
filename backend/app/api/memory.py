from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any
from app.agent.memory import agent_memory

router = APIRouter()

@router.get("/")
async def list_episodes(
    project_id: str = "default",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """Retrieve a paginated list of episodic memories for the specified project."""
    try:
        result = agent_memory.episodic.get_all_episodes(
            project_id=project_id,
            limit=limit,
            offset=offset,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch memories: {e}")

@router.delete("/{episode_id}")
async def delete_episode(episode_id: str) -> Dict[str, Any]:
    """Delete a specific episodic memory by its ID."""
    try:
        success = agent_memory.episodic.delete_episode(episode_id)
        if not success:
            raise HTTPException(status_code=404, detail="Episodic memory not found")
        return {"status": "success", "message": f"Episode {episode_id} deleted."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete memory: {e}")
