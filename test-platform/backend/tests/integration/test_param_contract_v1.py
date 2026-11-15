"""T-09 参数契约（R13/R14）集成测试：custom_parameters 嵌套分组精确校验。

契约依据：docs/contracts/task-execution-v1.0.md §2 custom_parameters 精确规则。
- 外层键为已选 item_id 的十进制字符串，内层为扁平参数对象；
- 值只允许 string、有限 number、boolean；禁止 object、array、null；
- 0、false、"" 必须原样保存和渲染；
- 参数名匹配 ^[A-Za-z_][A-Za-z0-9_]{0,63}$，字符串最长 1000，禁止 NUL/CR/LF；
- 非 URL 字符串拒绝 shell 控制符；合法 http/https URL 允许路径/查询字符，不得含凭据。
"""
import pytest
from httpx import AsyncClient

from app.models import Device, TestItem


@pytest.fixture()
async def schema_item(test_db, sample_module, admin_user) -> TestItem:
    """带 parameters_schema 的测试项（properties 含 target/count/verbose）。"""
    item = TestItem(
        module_id=sample_module.id,
        name="Param Contract Item",
        description="T-09 参数契约测试项",
        exec_type="adb_shell",
        exec_command="ping -c {count} {target}",
        parameters={},
        parameters_schema={
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "count": {"type": "number"},
                "verbose": {"type": "boolean"},
            },
        },
        compatibility={},
        judgement_type="assertion",
        result_parse={"pass_pattern": "ok"},
        timeout=30,
        created_by=admin_user.id,
    )
    test_db.add(item)
    await test_db.commit()
    await test_db.refresh(item)
    return item


def _payload(device: Device, item: TestItem, params: dict) -> dict:
    return {
        "device_serial": device.serial_number,
        "item_ids": [item.id],
        "custom_parameters": params,
    }


@pytest.mark.asyncio
async def test_legal_grouped_params_accepted(
    client: AsyncClient, admin_token: str, sample_device: Device, schema_item: TestItem
):
    """契约示例 {"12":{"target":"8.8.8.8"}} 必须 201（回归历史误拒缺陷）。"""
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=_payload(sample_device, schema_item, {str(schema_item.id): {"target": "8.8.8.8"}}),
    )
    assert response.status_code == 201, response.text
    assert response.json()["code"] == 201


@pytest.mark.asyncio
async def test_url_param_with_query_chars_accepted(
    client: AsyncClient, admin_token: str, sample_device: Device, schema_item: TestItem
):
    """合法 http/https URL 允许路径、查询中的 ?、&、=、/。"""
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=_payload(
            sample_device, schema_item,
            {str(schema_item.id): {"target": "https://example.com/dl?a=1&b=2"}},
        ),
    )
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_zero_false_empty_preserved(
    client: AsyncClient, admin_token: str, sample_device: Device, schema_item: TestItem
):
    """0、false、"" 必须原样保存（不得被 falsy 擦除）。"""
    key = str(schema_item.id)
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=_payload(
            sample_device, schema_item,
            {key: {"count": 0, "verbose": False, "target": ""}},
        ),
    )
    assert response.status_code == 201, response.text
    detail = await client.get(
        f"/api/v1/tasks/{response.json()['data']['id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    saved = detail.json()["data"]["custom_parameters"][key]
    assert saved["count"] == 0
    assert saved["verbose"] is False
    assert saved["target"] == ""


@pytest.mark.asyncio
async def test_outer_key_must_be_selected_item(
    client: AsyncClient, admin_token: str, sample_device: Device, schema_item: TestItem
):
    """外层键必须是已选 item_id 的十进制字符串。"""
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=_payload(sample_device, schema_item, {"999": {"target": "8.8.8.8"}}),
    )
    assert response.status_code == 400
    err = response.json()
    assert err["code"] == "VALIDATION_ERROR"
    assert err["details"]["field"] == "custom_parameters.999"


@pytest.mark.asyncio
async def test_nested_object_value_rejected(
    client: AsyncClient, admin_token: str, sample_device: Device, schema_item: TestItem
):
    """内层值禁止 object，field 精确到 custom_parameters.<item>.<key>。"""
    key = str(schema_item.id)
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=_payload(sample_device, schema_item, {key: {"target": {"host": "x"}}}),
    )
    assert response.status_code == 400
    err = response.json()
    assert err["code"] == "VALIDATION_ERROR"
    assert err["details"]["field"] == f"custom_parameters.{key}.target"
    assert "不允许嵌套对象" in err["details"]["reason"]


@pytest.mark.asyncio
async def test_array_value_rejected(
    client: AsyncClient, admin_token: str, sample_device: Device, schema_item: TestItem
):
    key = str(schema_item.id)
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=_payload(sample_device, schema_item, {key: {"target": ["a", "b"]}}),
    )
    assert response.status_code == 400
    assert response.json()["details"]["field"] == f"custom_parameters.{key}.target"


@pytest.mark.asyncio
async def test_null_value_rejected(
    client: AsyncClient, admin_token: str, sample_device: Device, schema_item: TestItem
):
    key = str(schema_item.id)
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=_payload(sample_device, schema_item, {key: {"target": None}}),
    )
    assert response.status_code == 400
    assert response.json()["details"]["field"] == f"custom_parameters.{key}.target"


@pytest.mark.asyncio
async def test_item_without_schema_rejects_params(
    client: AsyncClient, admin_token: str, sample_device: Device, sample_item: TestItem
):
    """缺 parameters_schema 的测试项不接受任何自定义参数。"""
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=_payload(sample_device, sample_item, {str(sample_item.id): {"target": "8.8.8.8"}}),
    )
    assert response.status_code == 400
    err = response.json()
    assert err["details"]["field"] == f"custom_parameters.{sample_item.id}"
    assert "schema" in err["details"]["reason"]


@pytest.mark.asyncio
async def test_unknown_param_name_rejected(
    client: AsyncClient, admin_token: str, sample_device: Device, schema_item: TestItem
):
    """内层参数名必须存在于该项 parameters_schema.properties。"""
    key = str(schema_item.id)
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=_payload(sample_device, schema_item, {key: {"unknown_key": "x"}}),
    )
    assert response.status_code == 400
    err = response.json()
    assert err["details"]["field"] == f"custom_parameters.{key}.unknown_key"
    assert "不存在" in err["details"]["reason"]


@pytest.mark.asyncio
async def test_invalid_param_name_format_rejected(
    client: AsyncClient, admin_token: str, sample_device: Device, schema_item: TestItem
):
    """参数名不匹配 ^[A-Za-z_][A-Za-z0-9_]{0,63}$（如数字开头）。"""
    key = str(schema_item.id)
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=_payload(sample_device, schema_item, {key: {"1abc": "x"}}),
    )
    assert response.status_code == 400
    assert response.json()["details"]["field"] == f"custom_parameters.{key}.1abc"


@pytest.mark.asyncio
async def test_string_too_long_rejected(
    client: AsyncClient, admin_token: str, sample_device: Device, schema_item: TestItem
):
    key = str(schema_item.id)
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=_payload(sample_device, schema_item, {key: {"target": "a" * 1001}}),
    )
    assert response.status_code == 400
    assert "1000" in response.json()["details"]["reason"]


@pytest.mark.asyncio
async def test_control_chars_rejected(
    client: AsyncClient, admin_token: str, sample_device: Device, schema_item: TestItem
):
    """字符串禁止 NUL、CR、LF。"""
    key = str(schema_item.id)
    for bad in ("\x00", "\r", "\n"):
        response = await client.post(
            "/api/v1/tasks",
            headers={"Authorization": f"Bearer {admin_token}"},
            json=_payload(sample_device, schema_item, {key: {"target": f"a{bad}b"}}),
        )
        assert response.status_code == 400
        assert response.json()["details"]["field"] == f"custom_parameters.{key}.target"


@pytest.mark.asyncio
async def test_shell_metachar_rejected(
    client: AsyncClient, admin_token: str, sample_device: Device, schema_item: TestItem
):
    """非 URL 字符串拒绝 ;、|、>、<、$、反引号等 shell 控制符。"""
    key = str(schema_item.id)
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=_payload(sample_device, schema_item, {key: {"target": "8.8.8.8; rm -rf /"}}),
    )
    assert response.status_code == 400
    err = response.json()
    assert err["code"] == "VALIDATION_ERROR"
    assert "非法字符" in err["details"]["reason"]


@pytest.mark.asyncio
async def test_url_with_credentials_rejected(
    client: AsyncClient, admin_token: str, sample_device: Device, schema_item: TestItem
):
    """合法 URL 不得含凭据（user:pass@host 形式）。"""
    key = str(schema_item.id)
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=_payload(
            sample_device, schema_item,
            {key: {"target": "https://user:pass@example.com/a.zip"}},
        ),
    )
    assert response.status_code == 400
    assert "凭据" in response.json()["details"]["reason"]


@pytest.mark.asyncio
async def test_bool_and_number_accepted(
    client: AsyncClient, admin_token: str, sample_device: Device, schema_item: TestItem
):
    """boolean 与有限 number 合法（bool 是 number 子类，不得混判）。"""
    key = str(schema_item.id)
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=_payload(sample_device, schema_item, {key: {"verbose": True, "count": 42}}),
    )
    assert response.status_code == 201, response.text
