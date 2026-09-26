import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.auth.deps import TenantContext
from app.core.errors import ValidationFailed
from app.models import Activity, Deal, Organization, PipelineStage
from app.models.enums import ActivityType, DealStatus, StageKind
from app.schemas.crm import BoardColumn, BoardOut, DealOut
from app.services import pipelines, records
from app.services.crud import check_refs

_STATUS_FOR_KIND = {StageKind.OPEN: DealStatus.OPEN, StageKind.WON: DealStatus.WON, StageKind.LOST: DealStatus.LOST}


def _apply_stage(deal_data: dict[str, Any], stage: PipelineStage, *, keep_probability: bool) -> None:
    deal_data["stage_id"] = stage.id
    deal_data["pipeline_id"] = stage.pipeline_id
    deal_data["status"] = _STATUS_FOR_KIND[stage.kind]
    if not keep_probability:
        deal_data["probability"] = stage.probability
    deal_data["closed_at"] = datetime.now(UTC) if stage.kind != StageKind.OPEN else None


async def _resolve_stage(
    ctx: TenantContext, pipeline_id: uuid.UUID | None, stage_id: uuid.UUID | None
) -> PipelineStage:
    if stage_id:
        stage = await pipelines.get_stage(ctx, stage_id)
        if pipeline_id and stage.pipeline_id != pipeline_id:
            raise ValidationFailed("Stage does not belong to that pipeline")
        return stage
    pipeline = (
        await pipelines.get_pipeline(ctx, pipeline_id) if pipeline_id else await pipelines.get_default_pipeline(ctx)
    )
    first_open = next((s for s in pipeline.stages if s.kind == StageKind.OPEN), None)
    if first_open is None:
        raise ValidationFailed("Pipeline has no open stage")
    return first_open


def _log_stage_change(ctx: TenantContext, deal: Deal, old: PipelineStage | None, new: PipelineStage) -> None:
    ctx.session.add(
        Activity(
            organization_id=ctx.organization_id,
            type=ActivityType.STAGE_CHANGE,
            subject=f"Stage changed to {new.name}" if old else f"Deal created in {new.name}",
            occurred_at=datetime.now(UTC),
            actor_id=ctx.user_id,
            deal_id=deal.id,
            company_id=deal.company_id,
            contact_id=deal.contact_id,
            metadata_={
                "from_stage_id": str(old.id) if old else None,
                "from_stage": old.name if old else None,
                "to_stage_id": str(new.id),
                "to_stage": new.name,
            },
        )
    )


async def create_deal(ctx: TenantContext, data: dict[str, Any]) -> Deal:
    await check_refs(ctx, data)
    stage = await _resolve_stage(ctx, data.pop("pipeline_id", None), data.pop("stage_id", None))
    _apply_stage(data, stage, keep_probability=data.get("probability") is not None)
    if not data.get("currency"):
        org = await ctx.session.get(Organization, ctx.organization_id)
        data["currency"] = org.default_currency if org else "INR"
    data.setdefault("owner_id", ctx.user_id)
    if data.get("amount") is None:
        data["amount"] = Decimal(0)
    deal = await records.deals(ctx).create(data)
    _log_stage_change(ctx, deal, None, stage)
    return deal


async def update_deal(ctx: TenantContext, deal: Deal, data: dict[str, Any]) -> Deal:
    await check_refs(ctx, data)
    pipeline_id = data.pop("pipeline_id", None)
    stage_id = data.pop("stage_id", None)
    old_stage = new_stage = None
    if (stage_id and stage_id != deal.stage_id) or (pipeline_id and pipeline_id != deal.pipeline_id):
        old_stage = await pipelines.get_stage(ctx, deal.stage_id)
        new_stage = await _resolve_stage(ctx, pipeline_id, stage_id)
        _apply_stage(data, new_stage, keep_probability="probability" in data)

    await records.deals(ctx).update(deal, data)
    if new_stage:
        _log_stage_change(ctx, deal, old_stage, new_stage)
    return deal


async def board(ctx: TenantContext, pipeline_id: uuid.UUID | None, per_stage: int = 50) -> BoardOut:
    pipeline = (
        await pipelines.get_pipeline(ctx, pipeline_id) if pipeline_id else await pipelines.get_default_pipeline(ctx)
    )
    repo = records.deals(ctx)
    rows = list(
        await ctx.session.scalars(repo.base().where(Deal.pipeline_id == pipeline.id).order_by(Deal.updated_at.desc()))
    )
    columns = []
    for stage in pipeline.stages:
        in_stage = [d for d in rows if d.stage_id == stage.id]
        columns.append(
            BoardColumn(
                stage_id=stage.id,
                name=stage.name,
                kind=stage.kind,
                color=stage.color,
                probability=stage.probability,
                count=len(in_stage),
                total_amount=sum((d.amount for d in in_stage), Decimal(0)),
                deals=[DealOut.model_validate(d) for d in in_stage[:per_stage]],
            )
        )
    return BoardOut(pipeline_id=pipeline.id, columns=columns)
