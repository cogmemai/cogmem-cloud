"""ACP API routes for the cloud offering.

Exposes strategies, proposals, and outcome events via REST endpoints.
All routes are tenant-scoped — each user sees only their own data.
"""

from fastapi import APIRouter, Depends, HTTPException

from kos_extensions.tenant_deps import get_tenant_registry, TenantRegistry

router = APIRouter(prefix="/acp", tags=["acp"])


@router.get("/strategies")
async def list_strategies(reg: TenantRegistry = Depends(get_tenant_registry)):
    """List all active memory strategies."""
    strategies = await reg.strategy_store.list_strategies()
    return [s.model_dump(mode="json") for s in strategies]


@router.get("/strategies/{kos_id}")
async def get_strategy(kos_id: str, reg: TenantRegistry = Depends(get_tenant_registry)):
    """Get a single strategy by ID."""
    from kos.core.models.ids import KosId

    strategy = await reg.strategy_store.get_strategy(KosId(kos_id))
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy.model_dump(mode="json")


@router.get("/proposals")
async def list_proposals(status: str | None = None, reg: TenantRegistry = Depends(get_tenant_registry)):
    """List strategy change proposals, optionally filtered by status."""
    from kos.core.models.strategy_change_proposal import ProposalStatus

    proposal_status = ProposalStatus(status) if status else None
    proposals = await reg.proposal_store.list_proposals(status=proposal_status)
    return [p.model_dump(mode="json") for p in proposals]


@router.get("/proposals/{kos_id}")
async def get_proposal(kos_id: str, reg: TenantRegistry = Depends(get_tenant_registry)):
    """Get a single proposal by ID."""
    from kos.core.models.ids import KosId

    proposal = await reg.proposal_store.get_proposal(KosId(kos_id))
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return proposal.model_dump(mode="json")


@router.post("/proposals/{kos_id}/approve")
async def approve_proposal(kos_id: str, reg: TenantRegistry = Depends(get_tenant_registry)):
    """Approve a pending proposal."""
    from kos.core.models.ids import KosId
    from kos.core.models.strategy_change_proposal import ProposalStatus

    success = await reg.proposal_store.update_status(
        KosId(kos_id), ProposalStatus.APPROVED
    )
    if not success:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return {"status": "approved", "kos_id": kos_id}


@router.post("/proposals/{kos_id}/reject")
async def reject_proposal(kos_id: str, reg: TenantRegistry = Depends(get_tenant_registry)):
    """Reject a pending proposal."""
    from kos.core.models.ids import KosId
    from kos.core.models.strategy_change_proposal import ProposalStatus

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
    reg: TenantRegistry = Depends(get_tenant_registry),
):
    """List recent outcome events."""
    from kos.core.models.ids import KosId

    sid = KosId(strategy_id) if strategy_id else None
    outcomes = await reg.outcome_store.query_outcomes(
        strategy_id=sid, limit=limit
    )
    return [o.model_dump(mode="json") for o in outcomes]
