import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from code_review.agents.registry import invalidate_agent_config_cache
from code_review.db.database import get_db
from code_review.db.models import AgentConfigRecord
from code_review.web.schemas import AgentConfigResponse, AgentUpdateRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("", response_model=list[AgentConfigResponse])
def list_agents(db: Session = Depends(get_db)) -> list[AgentConfigResponse]:
    configs = db.query(AgentConfigRecord).order_by(AgentConfigRecord.id.asc()).all()
    return [AgentConfigResponse.model_validate(c) for c in configs]


@router.put("/{agent_id}", response_model=AgentConfigResponse)
def update_agent(
    agent_id: str,
    payload: AgentUpdateRequest,
    db: Session = Depends(get_db),
) -> AgentConfigResponse:
    config = db.query(AgentConfigRecord).filter(AgentConfigRecord.agent_id == agent_id).first()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found.",
        )

    if payload.is_enabled is not None:
        config.is_enabled = payload.is_enabled
    if payload.provider is not None:
        config.provider = payload.provider
    if payload.model_name is not None:
        config.model_name = payload.model_name
    if payload.options is not None:
        config.options = payload.options

    db.commit()
    db.refresh(config)
    invalidate_agent_config_cache()
    logger.info("Updated configuration for agent '%s': enabled=%s", agent_id, config.is_enabled)
    return AgentConfigResponse.model_validate(config)
