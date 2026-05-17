"""
ASTRA OS — Legacy Chat Endpoint (DEPRECATED)
==============================================
This endpoint is deprecated as of Phase 0 stabilization.
All chat functionality is now served through /api/v1/agent/run,
which provides:
  - Query classification
  - Iteration caps
  - Output sanitization
  - Circuit breakers
  - Modern memory system

This file returns HTTP 410 Gone for any request.
"""

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.post("/chat")
async def chat_endpoint_deprecated():
    """
    DEPRECATED: Use /api/v1/agent/run instead.
    This endpoint bypassed all Phase 0 safety protections and has been retired.
    """
    raise HTTPException(
        status_code=410,
        detail="Deprecated. Use /api/v1/agent/run — this endpoint has been retired for safety.",
    )
