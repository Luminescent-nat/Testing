"""测试知识库 API。"""
import pytest

pytestmark = pytest.mark.asyncio


async def test_list_knowledge_entries_empty(client, admin_token):
    """未创建条目时返回空列表。"""
    response = await client.get(
        "/api/v1/knowledge",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["items"] == []
    assert data["total"] == 0


async def test_create_and_get_knowledge_entry(client, admin_token):
    """管理员可以创建并查看知识条目。"""
    payload = {
        "title": "EMMC 性能测试规范",
        "entry_type": "document",
        "category": "存储测试",
        "tags": ["emmc", "性能"],
        "content": "测试步骤：使用 fio 进行顺序读写测试。",
        "status": "approved",
    }
    create_resp = await client.post(
        "/api/v1/knowledge",
        json=payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_resp.status_code == 200, create_resp.text
    entry_id = create_resp.json()["data"]["id"]

    detail_resp = await client.get(
        f"/api/v1/knowledge/{entry_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert detail_resp.status_code == 200
    data = detail_resp.json()["data"]
    assert data["title"] == payload["title"]
    assert data["entry_type"] == "document"
    assert data["category"] == "存储测试"
    assert data["status"] == "approved"
    assert "emmc" in data["tags"]
    assert data["hit_count"] == 1


async def test_update_knowledge_entry(client, admin_token):
    """管理员可以更新知识条目。"""
    create_resp = await client.post(
        "/api/v1/knowledge",
        json={"title": "旧标题", "entry_type": "document", "status": "draft"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    entry_id = create_resp.json()["data"]["id"]

    update_resp = await client.put(
        f"/api/v1/knowledge/{entry_id}",
        json={"title": "新标题", "status": "approved"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["data"]["title"] == "新标题"
    assert update_resp.json()["data"]["status"] == "approved"


async def test_delete_knowledge_entry_by_admin(client, admin_token):
    """管理员可以删除知识条目。"""
    create_resp = await client.post(
        "/api/v1/knowledge",
        json={"title": "待删除", "entry_type": "document", "status": "draft"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    entry_id = create_resp.json()["data"]["id"]

    delete_resp = await client.delete(
        f"/api/v1/knowledge/{entry_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete_resp.status_code == 200

    get_resp = await client.get(
        f"/api/v1/knowledge/{entry_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert get_resp.status_code == 404


async def test_normal_user_cannot_delete(client, normal_token, admin_token):
    """普通用户不能删除知识条目。"""
    create_resp = await client.post(
        "/api/v1/knowledge",
        json={"title": "普通用户测试", "entry_type": "document", "status": "draft"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    entry_id = create_resp.json()["data"]["id"]

    delete_resp = await client.delete(
        f"/api/v1/knowledge/{entry_id}",
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    assert delete_resp.status_code == 403


async def test_search_knowledge_entry(client, admin_token):
    """可以通过关键词搜索知识条目。"""
    await client.post(
        "/api/v1/knowledge",
        json={
            "title": "WIFI 连接稳定性测试",
            "entry_type": "test_case",
            "category": "网络测试",
            "content": "测试 WIFI 在弱信号环境下的重连能力。",
            "status": "approved",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    response = await client.get(
        "/api/v1/knowledge?keyword=WIFI",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] >= 1
    assert any("WIFI" in item["title"] for item in data["items"])


async def test_semantic_search_knowledge(client, admin_token):
    """语义搜索返回匹配结果（默认 embedding 关闭时按关键词匹配）。"""
    await client.post(
        "/api/v1/knowledge",
        json={
            "title": "DDR 内存压力测试用例",
            "entry_type": "test_case",
            "category": "内存测试",
            "tags": ["ddr", "stress"],
            "content": "使用 memtester 对 DDR 进行压力测试，验证稳定性。",
            "status": "approved",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    response = await client.post(
        "/api/v1/knowledge/search",
        json={"query": "内存压力测试", "top_k": 5},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] >= 1
    assert any("DDR" in item["title"] for item in data["items"])


async def test_recommend_knowledge(client, admin_token):
    """智能推荐仅返回已审核条目。"""
    await client.post(
        "/api/v1/knowledge",
        json={
            "title": "蓝牙兼容性判定规则",
            "entry_type": "rule",
            "category": "蓝牙测试",
            "tags": ["bluetooth", "compat"],
            "content": "蓝牙模块兼容性判定规则。",
            "status": "approved",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    response = await client.post(
        "/api/v1/knowledge/recommend",
        json={"query": "蓝牙模块兼容性怎么判断", "top_k": 5},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] >= 1


async def test_embed_knowledge_entry(client, admin_token):
    """嵌入接口可正常调用（embedding 未启用时返回未启用提示）。"""
    create_resp = await client.post(
        "/api/v1/knowledge",
        json={"title": "待嵌入", "entry_type": "document", "status": "draft"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    entry_id = create_resp.json()["data"]["id"]

    response = await client.post(
        f"/api/v1/knowledge/{entry_id}/embed",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200


async def test_extract_knowledge_entry(client, admin_token, mock_llm):
    """AI 提取接口调用 LLM 并返回结构化信息。"""
    create_resp = await client.post(
        "/api/v1/knowledge",
        json={
            "title": "原始资料",
            "entry_type": "document",
            "status": "draft",
            "content": "这是一份关于 EMMC 随机读写性能测试的资料。",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    entry_id = create_resp.json()["data"]["id"]

    response = await client.post(
        f"/api/v1/knowledge/{entry_id}/extract",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "title" in data


async def test_knowledge_feedback_from_task(
    client, admin_token, sample_device, sample_module, mock_adb
):
    """测试执行后，相关知识条目应更新命中/通过次数。"""
    from unittest.mock import AsyncMock
    from app.models import TestItem
    from app.services.task_executor import TaskExecutor

    # mock adb 返回满足通过条件的输出
    mock_adb.execute_shell = AsyncMock(return_value=("bw=240MB/s", "", 0))

    # 创建一个带标签的测试项
    item_resp = await client.post(
        f"/api/v1/modules/{sample_module.id}/items",
        json={
            "module_id": sample_module.id,
            "name": "EMMC 顺序读写测试",
            "description": "验证 EMMC 顺序读写带宽",
            "exec_type": "adb_shell",
            "exec_command": "echo 'bw=240MB/s'",
            "parameters": {},
            "compatibility": {},
            "judgement_type": "assertion",
            "result_parse": {"pass_pattern": "bw="},
            "timeout": 30,
            "tags": ["emmc", "performance"]
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert item_resp.status_code == 200, item_resp.text
    item_id = item_resp.json()["data"]["id"]

    # 创建知识条目，标签与测试项匹配
    create_resp = await client.post(
        "/api/v1/knowledge",
        json={
            "title": "EMMC 性能测试规范",
            "entry_type": "test_case",
            "category": "存储测试",
            "tags": ["emmc", "performance"],
            "content": "EMMC 性能测试规范内容。",
            "status": "approved",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    entry_id = create_resp.json()["data"]["id"]

    # 创建并执行任务
    task_resp = await client.post(
        "/api/v1/tasks",
        json={
            "device_serial": sample_device.serial_number,
            "name": "反馈测试任务",
            "item_ids": [item_id],
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    task_id = task_resp.json()["data"]["id"]

    running = TaskExecutor._running_tasks.get(task_id)
    if running:
        await running

    # 验证知识条目统计更新
    detail_resp = await client.get(
        f"/api/v1/knowledge/{entry_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert detail_resp.status_code == 200
    data = detail_resp.json()["data"]
    assert data["hit_count"] >= 1
    assert data["pass_count"] >= 1


async def test_list_knowledge_categories_and_tags(client, admin_token):
    """分类和标签聚合接口正常返回。"""
    await client.post(
        "/api/v1/knowledge",
        json={
            "title": "聚合测试",
            "entry_type": "document",
            "category": "存储测试",
            "tags": ["emmc", "性能"],
            "status": "approved"
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    cat_resp = await client.get(
        "/api/v1/knowledge/categories",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert cat_resp.status_code == 200
    assert "存储测试" in cat_resp.json()["data"]

    tag_resp = await client.get(
        "/api/v1/knowledge/tags",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert tag_resp.status_code == 200
    tags = tag_resp.json()["data"]
    assert "emmc" in tags
    assert "性能" in tags


async def test_convert_knowledge_to_test_item(client, admin_token, monkeypatch):
    """管理员可将知识条目转换为测试项。"""
    create_resp = await client.post(
        "/api/v1/knowledge",
        json={
            "title": "EMMC 转换测试",
            "entry_type": "document",
            "content": "fio 顺序读测试",
            "status": "approved"
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    entry_id = create_resp.json()["data"]["id"]

    # Mock LLM 预览
    preview_data = {
        "module_name": "EMMC",
        "name": "顺序读测试",
        "exec_type": "adb_shell",
        "exec_command": "fio --name=seqread",
        "judgement_type": "assertion"
    }

    async def mock_preview(self, entry, target_type, extra_hint=None):
        return preview_data

    monkeypatch.setattr(
        "app.services.knowledge_converter.KnowledgeConverter.preview",
        mock_preview
    )

    preview_resp = await client.post(
        f"/api/v1/knowledge/{entry_id}/convert/preview",
        json={"target_type": "test_item"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert preview_resp.status_code == 200
    assert preview_resp.json()["data"]["preview_data"]["module_name"] == "EMMC"

    convert_resp = await client.post(
        f"/api/v1/knowledge/{entry_id}/convert",
        json={"target_type": "test_item", "preview_data": preview_data},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert convert_resp.status_code == 200
    data = convert_resp.json()["data"]
    assert data["asset_type"] == "test_item"
    assert data["detail"]["item_name"] == "顺序读测试"


async def test_convert_knowledge_forbidden_for_normal_user(client, normal_token, admin_token):
    """普通用户不能执行转换。"""
    create_resp = await client.post(
        "/api/v1/knowledge",
        json={"title": "权限测试", "entry_type": "document", "status": "approved"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    entry_id = create_resp.json()["data"]["id"]

    convert_resp = await client.post(
        f"/api/v1/knowledge/{entry_id}/convert",
        json={"target_type": "test_item", "preview_data": {"module_name": "A", "name": "B", "exec_type": "adb_shell", "exec_command": "echo", "judgement_type": "assertion"}},
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    assert convert_resp.status_code == 403
