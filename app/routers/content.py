"""Sección 9 — Curación de contenido."""
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import func, select

from app import models_canonico as M
from app.audit import audit, tenant_de
from app.deps import Db, require
from app.enums import ContentStatus, ContentType
from app.errors import conflict, invalid, not_found
from app.schemas.common import Page
from app.schemas.operation import ContentCreateIn, ContentItemOut, ContentPatchIn
from app.security import now_utc
from app.staff import nombres_de_staff

router = APIRouter(prefix="/content", tags=["Curación de contenido"])
CI = M.ContentItem
# Demo: no hay cola TTS real, así que el audio se da por generado al guardar. En
# producción quedaría en 'pending' hasta que el worker lo marque 'ready'.
TTS_DEMO = "ready"


def _out(i: M.ContentItem, nombres: dict) -> ContentItemOut:
    return ContentItemOut(id=i.id, type=ContentType(i.type), title=i.title, body=i.body,
                          audio_available=i.tts_status == "ready", tags=i.tags or [],
                          status=ContentStatus(i.status), publish_at=i.publish_at,
                          published_at=i.published_at, created_by_name=nombres.get(i.created_by),
                          updated_at=i.updated_at)


async def _out_uno(db, i: M.ContentItem) -> ContentItemOut:
    await db.flush()
    await db.refresh(i)  # updated_at lo pone el trigger
    return _out(i, await nombres_de_staff(db, [i.created_by]))


async def _get(db, request: Request, item_id: UUID) -> M.ContentItem:
    item = await db.get(CI, item_id)
    if item is None or item.deleted_at is not None or item.tenant_id != tenant_de(request):
        raise not_found()
    return item


# ---------- 9.1 Listar ----------
@router.get("/items", response_model=Page[ContentItemOut], dependencies=[require("content")])
async def list_items(request: Request, db: Db,
                     type_f: ContentType | None = Query(default=None, alias="type"),
                     status_f: ContentStatus | None = Query(default=None, alias="status"),
                     q: str | None = Query(default=None, max_length=120),
                     page: int = Query(default=1, ge=1),
                     page_size: int = Query(default=25, ge=1, le=100)):
    stmt = select(CI).where(CI.tenant_id == tenant_de(request), CI.deleted_at.is_(None))
    if type_f:
        stmt = stmt.where(CI.type == type_f.value)
    if status_f:
        stmt = stmt.where(CI.status == status_f.value)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(CI.title.ilike(like) | CI.body.ilike(like))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(CI.updated_at.desc(), CI.id)
                             .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    nombres = await nombres_de_staff(db, [i.created_by for i in rows])
    return Page(items=[_out(i, nombres) for i in rows], page=page, page_size=page_size, total=total)


# ---------- 9.2 Crear ----------
@router.post("/items", response_model=ContentItemOut, status_code=201)
async def create_item(body: ContentCreateIn, request: Request, db: Db,
                      admin: M.AdminUser = require("content", write=True)):
    if body.publish_at is not None and body.publish_at <= now_utc():
        raise invalid("PUBLISH_AT_PAST", "La fecha de publicación programada debe ser futura.")
    item = CI(tenant_id=tenant_de(request), type=body.type.value, title=body.title, body=body.body,
              tags=body.tags or [], publish_at=body.publish_at, tts_status=TTS_DEMO,
              created_by=admin.id, updated_by=admin.id)
    db.add(item)
    await db.flush()
    await audit(db, request, "content.create", "content_item", item.id, after={"title": item.title})
    return await _out_uno(db, item)


# ---------- 9.3 Editar ----------
@router.patch("/items/{item_id}", response_model=ContentItemOut)
async def patch_item(item_id: UUID, body: ContentPatchIn, request: Request, db: Db,
                     admin: M.AdminUser = require("content", write=True)):
    item = await _get(db, request, item_id)
    before = {"title": item.title}
    if body.publish_at is not None and body.publish_at <= now_utc():
        raise invalid("PUBLISH_AT_PAST", "La fecha de publicación programada debe ser futura.")
    if body.body is not None and body.body != item.body:
        item.body = body.body
        item.tts_status = TTS_DEMO  # en producción se re-encolaría la generación del audio
    if body.title is not None:
        item.title = body.title
    if body.tags is not None:
        item.tags = body.tags
    if body.publish_at is not None:
        item.publish_at = body.publish_at
    item.updated_by = admin.id
    await audit(db, request, "content.update", "content_item", item.id, before=before,
                after={"title": item.title})
    return await _out_uno(db, item)


# ---------- 9.4 Publicar ----------
@router.post("/items/{item_id}/publish", response_model=ContentItemOut)
async def publish_item(item_id: UUID, request: Request, db: Db,
                       admin: M.AdminUser = require("content", write=True)):
    item = await _get(db, request, item_id)
    if item.status == ContentStatus.published.value:
        raise conflict("ALREADY_PUBLISHED", "El contenido ya está publicado.")
    if item.tts_status != "ready":
        raise conflict("TTS_PENDING", "El audio del contenido aún se está generando. Intenta en unos segundos.")
    item.status = ContentStatus.published.value
    item.published_at = now_utc()
    item.publish_at = None
    item.archived_at = None
    item.updated_by = admin.id
    await audit(db, request, "content.publish", "content_item", item.id)
    return await _out_uno(db, item)


# ---------- 9.5 Retirar ----------
@router.post("/items/{item_id}/unpublish", response_model=ContentItemOut)
async def unpublish_item(item_id: UUID, request: Request, db: Db,
                         admin: M.AdminUser = require("content", write=True)):
    item = await _get(db, request, item_id)
    if item.status != ContentStatus.published.value:
        raise conflict("NOT_PUBLISHED", "Solo puede retirarse contenido publicado.")
    item.status = ContentStatus.archived.value
    item.archived_at = now_utc()
    item.updated_by = admin.id
    await audit(db, request, "content.unpublish", "content_item", item.id)
    return await _out_uno(db, item)


# ---------- 9.6 Eliminar ----------
@router.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: UUID, request: Request, db: Db,
                      admin: M.AdminUser = require("content", write=True)):
    item = await _get(db, request, item_id)
    if item.status == ContentStatus.published.value:
        raise conflict("ITEM_PUBLISHED", "Retira el contenido del feed antes de eliminarlo.")
    item.deleted_at = now_utc()  # borrado lógico
    item.updated_by = admin.id
    await audit(db, request, "content.delete", "content_item", item.id)
    return Response(status_code=204)
