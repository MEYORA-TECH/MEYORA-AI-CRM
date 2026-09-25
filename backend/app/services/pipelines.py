import uuid

from sqlalchemy import func, select

from app.auth.deps import TenantContext
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.models import Deal, Pipeline, PipelineStage
from app.models.enums import StageKind
from app.schemas.pipelines import PipelineCreate, PipelineUpdate, StageInput
from app.services.audit import audit

DEFAULT_STAGES: list[tuple[str, int, StageKind, str]] = [
    ("Lead", 10, StageKind.OPEN, "slate"),
    ("Qualified", 20, StageKind.OPEN, "sky"),
    ("Discovery", 35, StageKind.OPEN, "violet"),
    ("Proposal", 55, StageKind.OPEN, "amber"),
    ("Negotiation", 75, StageKind.OPEN, "orange"),
    ("Won", 100, StageKind.WON, "emerald"),
    ("Lost", 0, StageKind.LOST, "rose"),
]


def build_default_pipeline(organization_id: uuid.UUID) -> Pipeline:
    return Pipeline(
        organization_id=organization_id,
        name="Sales Pipeline",
        is_default=True,
        stages=[
            PipelineStage(
                organization_id=organization_id,
                name=name,
                position=i,
                probability=prob,
                kind=kind,
                color=color,
            )
            for i, (name, prob, kind, color) in enumerate(DEFAULT_STAGES)
        ],
    )


async def list_pipelines(ctx: TenantContext) -> list[Pipeline]:
    rows = await ctx.session.scalars(
        select(Pipeline)
        .where(Pipeline.organization_id == ctx.organization_id)
        .order_by(Pipeline.is_default.desc(), Pipeline.created_at)
    )
    return list(rows)


async def get_pipeline(ctx: TenantContext, pipeline_id: uuid.UUID) -> Pipeline:
    pipeline = await ctx.session.scalar(
        select(Pipeline).where(
            Pipeline.id == pipeline_id, Pipeline.organization_id == ctx.organization_id
        )
    )
    if pipeline is None:
        raise NotFound("Pipeline")
    return pipeline


async def get_default_pipeline(ctx: TenantContext) -> Pipeline:
    pipelines = await list_pipelines(ctx)
    if not pipelines:
        raise NotFound("Pipeline")
    return pipelines[0]


async def get_stage(ctx: TenantContext, stage_id: uuid.UUID) -> PipelineStage:
    stage = await ctx.session.scalar(
        select(PipelineStage).where(
            PipelineStage.id == stage_id, PipelineStage.organization_id == ctx.organization_id
        )
    )
    if stage is None:
        raise NotFound("Stage")
    return stage


def _validate_stages(stages: list[StageInput]) -> None:
    kinds = [s.kind for s in stages]
    if StageKind.OPEN not in kinds:
        raise ValidationFailed("A pipeline needs at least one open stage")
    if kinds.count(StageKind.WON) != 1 or kinds.count(StageKind.LOST) != 1:
        raise ValidationFailed("A pipeline needs exactly one won and one lost stage")


async def _clear_default(ctx: TenantContext, keep: uuid.UUID | None) -> None:
    for p in await list_pipelines(ctx):
        if p.id != keep and p.is_default:
            p.is_default = False


async def create_pipeline(ctx: TenantContext, data: PipelineCreate) -> Pipeline:
    _validate_stages(data.stages)
    pipeline = Pipeline(organization_id=ctx.organization_id, name=data.name, is_default=data.is_default)
    pipeline.stages = [
        PipelineStage(
            organization_id=ctx.organization_id,
            name=s.name,
            position=i,
            probability=s.probability,
            kind=s.kind,
            color=s.color,
        )
        for i, s in enumerate(data.stages)
    ]
    if data.is_default:
        await _clear_default(ctx, keep=None)
    ctx.session.add(pipeline)
    await ctx.session.flush()
    audit(ctx, "pipeline.create", entity_type="pipeline", entity_id=pipeline.id,
          changes={"name": {"old": None, "new": data.name}})
    return pipeline


async def update_pipeline(ctx: TenantContext, pipeline_id: uuid.UUID, data: PipelineUpdate) -> Pipeline:
    pipeline = await get_pipeline(ctx, pipeline_id)
    changes: dict = {}
    if data.name is not None and data.name != pipeline.name:
        changes["name"] = {"old": pipeline.name, "new": data.name}
        pipeline.name = data.name
    if data.is_default:
        await _clear_default(ctx, keep=pipeline.id)
        pipeline.is_default = True

    if data.stages is not None:
        _validate_stages(data.stages)
        existing = {s.id: s for s in pipeline.stages}
        incoming_ids = {s.id for s in data.stages if s.id}
        unknown = incoming_ids - existing.keys()
        if unknown:
            raise ValidationFailed("Unknown stage in update", details=[str(i) for i in unknown])

        removed = [s for sid, s in existing.items() if sid not in incoming_ids]
        if removed:
            in_use = await ctx.session.scalar(
                # Soft-deleted deals still reference the stage, so they count too.
                select(func.count(Deal.id)).where(Deal.stage_id.in_([s.id for s in removed]))
            )
            if in_use:
                raise Conflict("Move deals out of a stage before deleting it")

        new_stages: list[PipelineStage] = []
        for i, s in enumerate(data.stages):
            stage = existing.get(s.id) if s.id else None
            if stage is None:
                stage = PipelineStage(organization_id=ctx.organization_id, pipeline_id=pipeline.id)
            stage.name, stage.position = s.name, i
            stage.probability, stage.kind, stage.color = s.probability, s.kind, s.color
            new_stages.append(stage)
        pipeline.stages = new_stages
        changes["stages"] = {"old": None, "new": [s.name for s in new_stages]}

    await ctx.session.flush()
    if changes:
        audit(ctx, "pipeline.update", entity_type="pipeline", entity_id=pipeline.id, changes=changes)
    return pipeline


async def delete_pipeline(ctx: TenantContext, pipeline_id: uuid.UUID) -> None:
    pipeline = await get_pipeline(ctx, pipeline_id)
    if pipeline.is_default:
        raise Conflict("The default pipeline cannot be deleted")
    deals = await ctx.session.scalar(
        select(func.count(Deal.id)).where(Deal.pipeline_id == pipeline.id)
    )
    if deals:
        raise Conflict("Move or delete this pipeline's deals first")
    await ctx.session.delete(pipeline)
    audit(ctx, "pipeline.delete", entity_type="pipeline", entity_id=pipeline.id)
