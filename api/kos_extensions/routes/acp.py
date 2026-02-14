"""ACP API routes for the cloud offering.

Exposes strategies, proposals, and outcome events via REST endpoints.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/acp", tags=["acp"])


def _get_registry():
    """Import at call time to avoid circular imports."""
    from kos.cloud.app import _get_registry
    return _get_registry()


@router.get("/strategies")
async def list_strategies():
    """List all active memory strategies."""
    reg = _get_registry()
    strategies = await reg.strategy_store.list_strategies()
    return [s.model_dump(mode="json") for s in strategies]


@router.get("/strategies/{kos_id}")
async def get_strategy(kos_id: str):
    """Get a single strategy by ID."""
    from fastapi import HTTPException
    from kos.core.models.ids import KosId

    reg = _get_registry()
    strategy = await reg.strategy_store.get_strategy(KosId(kos_id))
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy.model_dump(mode="json")


@router.get("/proposals")
async def list_proposals(status: str | None = None):
    """List strategy change proposals, optionally filtered by status."""
    from kos.core.models.strategy_change_proposal import ProposalStatus

    reg = _get_registry()
    proposal_status = ProposalStatus(status) if status else None
    proposals = await reg.proposal_store.list_proposals(status=proposal_status)
    return [p.model_dump(mode="json") for p in proposals]


@router.get("/proposals/{kos_id}")
async def get_proposal(kos_id: str):
    """Get a single proposal by ID."""
    from fastapi import HTTPException
    from kos.core.models.ids import KosId

    reg = _get_registry()
    proposal = await reg.proposal_store.get_proposal(KosId(kos_id))
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal.model_dump(mode="json")


@router.post("/proposals/{kos_id}/approve")
async def approve_proposal(kos_id: str):
    """Approve a pending proposal."""
    from fastapi import HTTPException
    from kos.core.models.ids import KosId
    from kos.core.models.strategy_change_proposal import ProposalStatus

    reg = _get_registry()
    success = await reg.proposal_store.update_status(
        KosId(kos_id), ProposalStatus.APPROVED
    )
    if not success:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return {"status": "approved", "kos_id": kos_id}


@router.post("/proposals/{kos_id}/reject")
async def reject_proposal(kos_id: str):
    """Reject a pending proposal."""
    from fastapi import HTTPException
    from kos.core.models.ids import KosId
    from kos.core.models.strategy_change_proposal import ProposalStatus

    reg = _get_registry()
    success = await reg.proposal_store.update_status(
        KosId(kos_id), ProposalStatus.REJECTED
    )
    if not success:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return {"status": "rejected", "kos_id": kos_id}


@router.get("/outcomes")
async def list_outcomes(
    strategy_id: str | None = None,
    limit: int = 100,
):
    """List recent outcome events."""
    from kos.core.models.ids import KosId

    reg = _get_registry()
    sid = KosId(strategy_id) if strategy_id else None
    outcomes = await reg.outcome_store.query_outcomes(
        strategy_id=sid, limit=limit
    )
    return [o.model_dump(mode="json") for o in outcomes]
