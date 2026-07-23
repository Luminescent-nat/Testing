from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from typing import Optional, List

from app.database import get_db
from app.api.auth import get_current_user, get_current_admin
from app.models import User, TestModule, TestItem, TestTool
from app.schemas import (
    TestModuleCreate, TestModuleUpdate, TestModuleResponse, TestModuleWithItems,
    TestItemCreate, TestItemUpdate, TestItemResponse,
    TestToolCreate, TestToolResponse,
    ResponseModel, PaginationParams
)

router = APIRouter(prefix="/modules", tags=["测试编排"])


# ========== 测试模块接口 ==========

@router.get("", response_model=ResponseModel)
async def list_modules(
    enabled_only: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取测试模块列表"""
    query = select(TestModule).options(selectinload(TestModule.items))

    if enabled_only:
        query = query.where(TestModule.enabled == True)

    query = query.order_by(TestModule.sort_order)
    result = await db.execute(query)
    modules = result.scalars().all()
    
    # 计算每个模块的测试项数量
    module_list = []
    for module in modules:
        module_data = TestModuleResponse.model_validate(module)
        module_data.item_count = len(module.items)
        module_list.append(module_data)
    
    return ResponseModel(
        code=200,
        data={
            "items": module_list,
            "total": len(module_list)
        }
    )


@router.get("/{module_id}", response_model=ResponseModel)
async def get_module(
    module_id: int,
    include_items: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取测试模块详情"""
    result = await db.execute(
        select(TestModule)
        .options(selectinload(TestModule.items))
        .where(TestModule.id == module_id)
    )
    module = result.scalar_one_or_none()
    
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    
    if include_items:
        return ResponseModel(
            code=200, 
            data=TestModuleWithItems.model_validate(module)
        )
    else:
        return ResponseModel(
            code=200,
            data=TestModuleResponse.model_validate(module)
        )


@router.post("", response_model=ResponseModel)
async def create_module(
    module_data: TestModuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """创建测试模块（管理员）"""
    new_module = TestModule(
        name=module_data.name,
        category=module_data.category,
        description=module_data.description,
        icon=module_data.icon,
        sort_order=module_data.sort_order,
        enabled=module_data.enabled,
        created_by=current_user.id
    )
    
    db.add(new_module)
    await db.commit()
    await db.refresh(new_module)
    
    return ResponseModel(
        code=200,
        message="创建成功",
        data=TestModuleResponse.model_validate(new_module)
    )


@router.put("/{module_id}", response_model=ResponseModel)
async def update_module(
    module_id: int,
    module_data: TestModuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """更新测试模块（管理员）"""
    result = await db.execute(
        select(TestModule).where(TestModule.id == module_id)
    )
    module = result.scalar_one_or_none()
    
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    
    # 更新字段
    if module_data.name is not None:
        module.name = module_data.name
    if module_data.category is not None:
        module.category = module_data.category
    if module_data.description is not None:
        module.description = module_data.description
    if module_data.icon is not None:
        module.icon = module_data.icon
    if module_data.sort_order is not None:
        module.sort_order = module_data.sort_order
    if module_data.enabled is not None:
        module.enabled = module_data.enabled
    
    await db.commit()
    await db.refresh(module)
    
    return ResponseModel(
        code=200,
        message="更新成功",
        data=TestModuleResponse.model_validate(module)
    )


@router.delete("/{module_id}", response_model=ResponseModel)
async def delete_module(
    module_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """删除测试模块（管理员）"""
    result = await db.execute(
        select(TestModule).where(TestModule.id == module_id)
    )
    module = result.scalar_one_or_none()
    
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    
    await db.delete(module)
    await db.commit()
    
    return ResponseModel(code=200, message="模块已删除")


# ========== 测试项接口 ==========

@router.get("/{module_id}/items", response_model=ResponseModel)
async def list_items(
    module_id: int,
    enabled_only: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取模块下的测试项列表"""
    # 检查模块是否存在
    result = await db.execute(
        select(TestModule).where(TestModule.id == module_id)
    )
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    
    query = (
        select(TestItem)
        .where(TestItem.module_id == module_id)
        .options(selectinload(TestItem.tool))
    )
    
    if enabled_only:
        query = query.where(TestItem.enabled == True)
    
    query = query.order_by(TestItem.sort_order)
    result = await db.execute(query)
    items = result.scalars().all()
    
    return ResponseModel(
        code=200,
        data={
            "items": [TestItemResponse.model_validate(item) for item in items],
            "total": len(items)
        }
    )


@router.post("/{module_id}/items", response_model=ResponseModel)
async def create_item(
    module_id: int,
    item_data: TestItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """创建测试项（管理员）"""
    # 检查模块是否存在
    result = await db.execute(
        select(TestModule).where(TestModule.id == module_id)
    )
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    
    new_item = TestItem(
        module_id=module_id,
        name=item_data.name,
        description=item_data.description,
        objective=item_data.objective,
        precondition=item_data.precondition,
        steps=item_data.steps,
        expected_result=item_data.expected_result,
        sort_order=item_data.sort_order,
        enabled=item_data.enabled,
        exec_type=item_data.exec_type.value,
        exec_command=item_data.exec_command,
        tool_id=item_data.tool_id,
        push_target=item_data.push_target,
        parameters=item_data.parameters,
        parameters_schema=item_data.parameters_schema,
        compatibility=item_data.compatibility,
        judgement_type=item_data.judgement_type.value,
        conditional_rules=item_data.conditional_rules,
        rubric_criteria=item_data.rubric_criteria,
        result_parse=item_data.result_parse,
        timeout=item_data.timeout,
        on_failure=item_data.on_failure,
        retry_count=item_data.retry_count,
        skills=item_data.skills,
        tags=item_data.tags,
        created_by=current_user.id
    )
    
    db.add(new_item)
    await db.commit()
    await db.refresh(new_item)
    
    return ResponseModel(
        code=200,
        message="创建成功",
        data=TestItemResponse.model_validate(new_item)
    )


@router.put("/{module_id}/items/{item_id}", response_model=ResponseModel)
async def update_item(
    module_id: int,
    item_id: int,
    item_data: TestItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """更新测试项（管理员）"""
    result = await db.execute(
        select(TestItem).where(
            and_(TestItem.id == item_id, TestItem.module_id == module_id)
        )
    )
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="测试项不存在")
    
    # 更新字段
    if item_data.name is not None:
        item.name = item_data.name
    if item_data.description is not None:
        item.description = item_data.description
    if item_data.objective is not None:
        item.objective = item_data.objective
    if item_data.precondition is not None:
        item.precondition = item_data.precondition
    if item_data.steps is not None:
        item.steps = item_data.steps
    if item_data.expected_result is not None:
        item.expected_result = item_data.expected_result
    if item_data.enabled is not None:
        item.enabled = item_data.enabled
    if item_data.exec_type is not None:
        item.exec_type = item_data.exec_type.value
    if item_data.exec_command is not None:
        item.exec_command = item_data.exec_command
    if item_data.tool_id is not None:
        item.tool_id = item_data.tool_id
    if item_data.push_target is not None:
        item.push_target = item_data.push_target
    if item_data.parameters is not None:
        item.parameters = item_data.parameters
    if item_data.compatibility is not None:
        item.compatibility = item_data.compatibility
    if item_data.judgement_type is not None:
        item.judgement_type = item_data.judgement_type.value
    if item_data.conditional_rules is not None:
        item.conditional_rules = item_data.conditional_rules
    if item_data.rubric_criteria is not None:
        item.rubric_criteria = item_data.rubric_criteria
    if item_data.timeout is not None:
        item.timeout = item_data.timeout
    if item_data.on_failure is not None:
        item.on_failure = item_data.on_failure
    if item_data.retry_count is not None:
        item.retry_count = item_data.retry_count
    if item_data.skills is not None:
        item.skills = item_data.skills
    if item_data.tags is not None:
        item.tags = item_data.tags

    await db.commit()
    await db.refresh(item)
    
    return ResponseModel(
        code=200,
        message="更新成功",
        data=TestItemResponse.model_validate(item)
    )


@router.delete("/{module_id}/items/{item_id}", response_model=ResponseModel)
async def delete_item(
    module_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """删除测试项（管理员）"""
    result = await db.execute(
        select(TestItem).where(
            and_(TestItem.id == item_id, TestItem.module_id == module_id)
        )
    )
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="测试项不存在")
    
    await db.delete(item)
    await db.commit()
    
    return ResponseModel(code=200, message="测试项已删除")
