import os
import hashlib
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List

from app.database import get_db
from app.api.auth import get_current_user, get_current_admin
from app.models import User, TestTool
from app.schemas import TestToolResponse, ResponseModel
from app.config import get_settings

router = APIRouter(prefix="/tools", tags=["测试工具"])

settings = get_settings()


def _ensure_tools_dir():
    tools_dir = settings.TOOLS_PATH
    os.makedirs(tools_dir, exist_ok=True)
    return tools_dir


def _compute_md5(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


@router.get("", response_model=ResponseModel)
async def list_tools(
    architecture: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取测试工具列表"""
    query = select(TestTool).order_by(TestTool.created_at.desc())
    if architecture:
        query = query.where(TestTool.architecture == architecture)
    result = await db.execute(query)
    tools = result.scalars().all()
    return ResponseModel(
        code=200,
        data={
            "items": [TestToolResponse.model_validate(tool) for tool in tools],
            "total": len(tools)
        }
    )


@router.get("/{tool_id}", response_model=ResponseModel)
async def get_tool(
    tool_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取测试工具详情"""
    result = await db.execute(select(TestTool).where(TestTool.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")
    return ResponseModel(code=200, data=TestToolResponse.model_validate(tool))


@router.post("", response_model=ResponseModel)
async def upload_tool(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    version: Optional[str] = Form(None),
    architecture: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """上传测试工具（管理员）"""
    tools_dir = _ensure_tools_dir()
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    safe_name = os.path.basename(file.filename or "unknown")
    file_path = os.path.join(tools_dir, safe_name)

    # 如果文件已存在则覆盖
    with open(file_path, "wb") as f:
        f.write(content)

    md5_hash = _compute_md5(content)
    file_size = len(content)

    new_tool = TestTool(
        name=name,
        description=description,
        version=version,
        architecture=architecture,
        filename=safe_name,
        file_size=file_size,
        file_path=file_path,
        mime_type=file.content_type,
        md5_hash=md5_hash,
        created_by=current_user.id
    )
    db.add(new_tool)
    await db.commit()
    await db.refresh(new_tool)

    return ResponseModel(
        code=200,
        message="上传成功",
        data=TestToolResponse.model_validate(new_tool)
    )


@router.delete("/{tool_id}", response_model=ResponseModel)
async def delete_tool(
    tool_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """删除测试工具（管理员）"""
    result = await db.execute(select(TestTool).where(TestTool.id == tool_id))
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail="工具不存在")

    # 尝试删除物理文件，失败不影响数据库删除
    try:
        if os.path.exists(tool.file_path):
            os.remove(tool.file_path)
    except OSError:
        pass

    await db.delete(tool)
    await db.commit()
    return ResponseModel(code=200, message="工具已删除")
