import os
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_, func

from app.database import get_db
from app.api.auth import get_current_user, get_current_admin
from app.errors import build_error_body
from app.models import User, KnowledgeEntry
from app.schemas import (
    ResponseModel,
    KnowledgeEntryCreate,
    KnowledgeEntryUpdate,
    KnowledgeEntryResponse,
    KnowledgeEntryType,
    KnowledgeEntryStatus,
    KnowledgeConvertTargetType,
    KnowledgeConvertPreviewRequest,
    KnowledgeConvertRequest,
)
from app.services.knowledge_parser import parse_document, chunk_text
from app.services.knowledge_embedder import get_embedder
from app.services.knowledge_search import KnowledgeSearchService
from app.services.knowledge_extractor import get_extractor
from app.services.knowledge_converter import (
    KnowledgeConverter,
    RuleValidationError,
    validate_conditional_rules,
)

router = APIRouter(prefix="/knowledge", tags=["测试知识库"])


def _rule_validation_response(exc: RuleValidationError, message: str) -> JSONResponse:
    """按契约错误外层返回 400 VALIDATION_ERROR，details.field 精确到条件字段路径。"""
    return JSONResponse(
        status_code=400,
        content=build_error_body(
            "VALIDATION_ERROR", message, {"field": exc.field, "reason": exc.reason}
        ),
    )

KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage", "knowledge")
os.makedirs(KNOWLEDGE_DIR, exist_ok=True)

embedder = get_embedder()

ALLOWED_TYPES = {
    "text/plain", "text/markdown", "application/markdown",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/png", "image/jpeg", "image/jpg", "image/webp"
}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


def _build_entry_text(entry: KnowledgeEntry) -> str:
    """构建用于生成嵌入的文本。"""
    parts = [
        f"标题: {entry.title or ''}",
        f"类型: {entry.entry_type or ''}",
        f"分类: {entry.category or ''}",
        f"标签: {', '.join(entry.tags or [])}",
        f"内容: {entry.content or ''}"
    ]
    return "\n".join(parts)


async def _generate_embedding(entry: KnowledgeEntry) -> None:
    """为条目生成并设置嵌入向量。失败时不抛异常。"""
    try:
        text = _build_entry_text(entry)
        vec = await embedder.embed(text)
        if vec:
            entry.embedding = vec
    except Exception as exc:
        # 嵌入失败不影响主流程
        import logging
        logging.getLogger(__name__).warning("生成知识库条目嵌入失败 id=%s: %s", entry.id, exc)


@router.get("", response_model=ResponseModel)
async def list_knowledge_entries(
    entry_type: Optional[KnowledgeEntryType] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    status: Optional[KnowledgeEntryStatus] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """查询知识库条目。"""
    query = select(KnowledgeEntry)

    if entry_type:
        query = query.where(KnowledgeEntry.entry_type == entry_type.value)
    if category:
        query = query.where(KnowledgeEntry.category == category)
    if status:
        query = query.where(KnowledgeEntry.status == status.value)
    if tag:
        query = query.where(KnowledgeEntry.tags.contains([tag]))
    if keyword:
        like = f"%{keyword}%"
        query = query.where(
            or_(
                KnowledgeEntry.title.ilike(like),
                KnowledgeEntry.content.ilike(like),
                KnowledgeEntry.category.ilike(like)
            )
        )

    # 统计总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    query = query.order_by(desc(KnowledgeEntry.updated_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return ResponseModel(
        code=200,
        data={
            "items": [KnowledgeEntryResponse.model_validate(item).model_dump() for item in items],
            "total": total,
            "page": page,
            "page_size": page_size
        }
    )


@router.get("/categories", response_model=ResponseModel)
async def list_knowledge_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """聚合所有已有知识条目的分类，用于下拉建议。"""
    result = await db.execute(
        select(KnowledgeEntry.category)
        .where(KnowledgeEntry.category.isnot(None))
        .where(KnowledgeEntry.category != "")
        .distinct()
        .order_by(KnowledgeEntry.category)
    )
    categories = [r for r in result.scalars().all()]
    return ResponseModel(code=200, data=categories)


@router.get("/tags", response_model=ResponseModel)
async def list_knowledge_tags(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """聚合所有已有知识条目的标签，用于下拉建议。"""
    result = await db.execute(select(KnowledgeEntry.tags))
    tag_set = set()
    for row in result.scalars().all():
        if row:
            tag_set.update(row)
    return ResponseModel(code=200, data=sorted(tag_set))


@router.get("/{entry_id}", response_model=ResponseModel)
async def get_knowledge_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取知识库条目详情。"""
    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="知识条目不存在")

    entry.hit_count = (entry.hit_count or 0) + 1
    await db.commit()

    return ResponseModel(
        code=200,
        data=KnowledgeEntryResponse.model_validate(entry).model_dump()
    )


@router.post("", response_model=ResponseModel)
async def create_knowledge_entry(
    data: KnowledgeEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """手动创建知识库条目。"""
    entry = KnowledgeEntry(
        title=data.title,
        entry_type=data.entry_type.value,
        category=data.category,
        tags=data.tags,
        content=data.content,
        chunks=chunk_text(data.content) if data.content else None,
        source_type=data.source_type,
        source_file=data.source_file,
        status=data.status.value,
        meta=data.meta,
        created_by=current_user.id
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    await _generate_embedding(entry)
    await db.commit()
    await db.refresh(entry)

    return ResponseModel(
        code=200,
        message="创建成功",
        data=KnowledgeEntryResponse.model_validate(entry).model_dump()
    )


@router.put("/{entry_id}", response_model=ResponseModel)
async def update_knowledge_entry(
    entry_id: int,
    data: KnowledgeEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新知识库条目。管理员可更新任意条目，普通用户仅能更新自己创建的草稿。"""
    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="知识条目不存在")

    if current_user.role != "admin" and entry.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="无权限更新该条目")

    if current_user.role != "admin" and entry.status != "draft":
        raise HTTPException(status_code=403, detail="仅管理员可更新非草稿条目")

    update_map = {
        "title": data.title,
        "entry_type": data.entry_type.value if data.entry_type else None,
        "category": data.category,
        "tags": data.tags,
        "content": data.content,
        "source_type": data.source_type,
        "source_file": data.source_file,
        "status": data.status.value if data.status else None,
        "meta": data.meta,
    }

    for field, value in update_map.items():
        if value is not None:
            setattr(entry, field, value)

    # 如果内容变了，重新分片
    if data.content is not None:
        entry.chunks = chunk_text(data.content) if data.content else None

    await _generate_embedding(entry)
    await db.commit()
    await db.refresh(entry)
    return ResponseModel(
        code=200,
        message="更新成功",
        data=KnowledgeEntryResponse.model_validate(entry).model_dump()
    )


@router.delete("/{entry_id}", response_model=ResponseModel)
async def delete_knowledge_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """删除知识库条目（管理员）。"""
    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="知识条目不存在")

    # 删除关联文件
    if entry.source_file and os.path.exists(entry.source_file):
        try:
            os.remove(entry.source_file)
        except Exception:
            pass

    await db.delete(entry)
    await db.commit()
    return ResponseModel(code=200, message="删除成功")


@router.post("/upload", response_model=ResponseModel)
async def upload_knowledge_document(
    title: str = Form(..., max_length=200),
    category: Optional[str] = Form(None, max_length=100),
    tags: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """上传测试资料文档，自动解析为知识库条目。"""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型：{file.content_type}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件大小超过 20MB 限制")

    # 保存原始文件
    ext = os.path.splitext(file.filename or "")[1] or ".bin"
    saved_name = f"{uuid.uuid4().hex}{ext}"
    saved_path = os.path.join(KNOWLEDGE_DIR, saved_name)
    with open(saved_path, "wb") as f:
        f.write(content)

    is_xlsx = file.content_type in {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    } or (file.filename or "").lower().endswith((".xlsx", ".xls"))

    try:
        text = parse_document(content, file.filename or saved_name, file.content_type)
    except Exception as exc:
        # 解析失败也保留文件，但标记为草稿
        text = ""
        status = "draft"
        metadata_note = {"parse_error": str(exc)}
        extracted_test_cases = None
    else:
        status = "draft"
        metadata_note = {}
        extracted_test_cases = None

        # 对 XLSX 测试用例表格接入 AI 解析
        if is_xlsx and text:
            try:
                extractor = get_extractor()
                if extractor.client:
                    extracted = await extractor.extract_test_cases(text, file.filename)
                    if extracted and extracted.get("test_cases"):
                        extracted_test_cases = extracted
            except Exception as exc:
                logger.warning("XLSX AI 测试用例提取失败: %s", exc)

    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]

    # 如果成功提取到测试用例，条目类型标记为 test_case，便于后续检索和转换
    entry_type = "test_case" if extracted_test_cases else "document"

    meta = {
        "original_filename": file.filename,
        "content_type": file.content_type,
        **metadata_note
    }
    if extracted_test_cases:
        meta["ai_extracted_test_cases"] = extracted_test_cases

    entry = KnowledgeEntry(
        title=title,
        entry_type=entry_type,
        category=category,
        tags=tag_list,
        content=text,
        chunks=chunk_text(text) if text else None,
        source_type="upload",
        source_file=saved_path,
        status=status,
        meta=meta,
        created_by=current_user.id
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    await _generate_embedding(entry)
    await db.commit()
    await db.refresh(entry)

    return ResponseModel(
        code=200,
        message="上传并解析成功" if text else "上传成功，但解析失败",
        data=KnowledgeEntryResponse.model_validate(entry).model_dump()
    )


@router.post("/search", response_model=ResponseModel)
async def search_knowledge(
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """语义/混合搜索知识库。"""
    query = data.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="搜索词不能为空")

    service = KnowledgeSearchService(db)
    results = await service.search(
        query=query,
        entry_type=data.get("entry_type"),
        category=data.get("category"),
        status=data.get("status"),
        tag=data.get("tag"),
        top_k=data.get("top_k", 10)
    )
    return ResponseModel(code=200, data={"items": results, "total": len(results)})


@router.post("/{entry_id}/embed", response_model=ResponseModel)
async def embed_knowledge_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """为指定知识条目重新生成嵌入向量。"""
    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="知识条目不存在")

    await _generate_embedding(entry)
    await db.commit()
    await db.refresh(entry)
    return ResponseModel(
        code=200,
        message="嵌入生成成功" if entry.embedding else "嵌入生成失败或未启用",
        data={"has_embedding": entry.embedding is not None}
    )


@router.post("/{entry_id}/extract", response_model=ResponseModel)
async def extract_knowledge_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """使用 AI 提取/优化知识条目信息（管理员或创建者）。"""
    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="知识条目不存在")

    if current_user.role != "admin" and entry.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="无权限操作该条目")

    extractor = get_extractor()
    if not extractor.client:
        raise HTTPException(status_code=400, detail="未配置 LLM，无法执行 AI 提取")

    extracted = await extractor.extract(entry.content or entry.title, entry.meta.get("original_filename"))
    if not extracted:
        raise HTTPException(status_code=500, detail="AI 提取失败")

    entry.meta = {
        **(entry.meta or {}),
        "ai_extracted": extracted,
        "extracted_at": str(datetime.now(timezone.utc))
    }

    await db.commit()
    await db.refresh(entry)
    return ResponseModel(code=200, data=extracted)


@router.post("/recommend", response_model=ResponseModel)
async def recommend_knowledge(
    data: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """根据查询意图推荐相关知识条目（用于 AI 测试规划辅助）。"""
    query = data.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="查询意图不能为空")

    service = KnowledgeSearchService(db)
    results = await service.search(
        query=query,
        entry_type=data.get("entry_type"),
        status="approved",
        top_k=data.get("top_k", 5)
    )
    return ResponseModel(code=200, data={"items": results, "total": len(results)})


@router.post("/{entry_id}/convert/preview", response_model=ResponseModel)
async def preview_convert_knowledge(
    entry_id: int,
    data: KnowledgeConvertPreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """预览将知识条目转换为测试资产的结果（不写入数据库）。"""
    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="知识条目不存在")

    converter = KnowledgeConverter.get_default_converter()
    preview = await converter.preview(
        entry=entry,
        target_type=data.target_type.value,
        extra_hint=data.extra_hint
    )

    if preview is None:
        if not converter.client:
            raise HTTPException(status_code=400, detail="未配置 LLM，无法生成预览")
        raise HTTPException(status_code=500, detail="AI 预览生成失败")

    # 写前校验：rule 预览的 conditional_rules 必须符合契约 §1 唯一对象结构；
    # 非法立即 400，且本接口不写任何测试资产。
    if data.target_type.value == "rule":
        try:
            preview["conditional_rules"] = validate_conditional_rules(
                preview.get("conditional_rules"), "preview_data.conditional_rules"
            )
        except RuleValidationError as exc:
            return _rule_validation_response(exc, "转换预览参数不合法")

    return ResponseModel(
        code=200,
        data={
            "target_type": data.target_type.value,
            "preview_data": preview,
            "has_llm": converter.client is not None
        }
    )


@router.post("/{entry_id}/convert", response_model=ResponseModel)
async def convert_knowledge(
    entry_id: int,
    data: KnowledgeConvertRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """将知识条目转换为实际测试资产（管理员权限）。"""
    result = await db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="知识条目不存在")

    converter = KnowledgeConverter.get_default_converter()
    try:
        detail = await converter.convert(
            db=db,
            entry=entry,
            target_type=data.target_type.value,
            preview_data=data.preview_data,
            current_user_id=current_user.id
        )
    except RuleValidationError as exc:
        # 规则写前校验失败：400 契约错误外层，事务未写入任何资产
        return _rule_validation_response(exc, "转换数据不合法")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger = logging.getLogger(__name__)
        logger.warning("知识条目转换失败 id=%s: %s", entry_id, exc)
        raise HTTPException(status_code=500, detail=f"转换失败：{exc}")

    await db.commit()
    return ResponseModel(
        code=200,
        message="转换成功",
        data={"asset_type": data.target_type.value, "detail": detail}
    )
