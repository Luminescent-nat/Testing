"""V1-09a（T-15）：知识规则写入/转换边界回归。

覆盖契约 knowledge-rules-v1.0 §1 唯一 conditional_rules 对象 schema：
- list/标量/空 conditions/未知操作符/非法正则/缺失 source/target/approx_ratio 零目标 → 400
  VALIDATION_ERROR 且零资产写入、details.field 精确；
- 合法 conditions 转换后由判定引擎得到确定 pass/fail；
- 重复规则转换幂等；
- 预览非法规则同样 400（不写资产），合法预览返回规范化对象。
"""
import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import KnowledgeEntry, TestItem, TestModule
from app.services.judgement_engine import JudgementEngine
from app.services.knowledge_converter import KnowledgeConverter


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _valid_rules() -> dict:
    return {
        "returncode_zero": True,
        "conditions": [
            {
                "source": "regex:value=([0-9.]+)",
                "operator": ">=",
                "target": "100",
                "tolerance": "0%",
                "on_fail": "低于下限",
            }
        ],
    }


@pytest_asyncio.fixture
async def knowledge_entry(test_db, admin_user):
    entry = KnowledgeEntry(
        title="网络延迟规则资料",
        entry_type="document",
        content="latency value=150\n阈值 100",
        status="approved",
        created_by=admin_user.id,
    )
    test_db.add(entry)
    await test_db.commit()
    await test_db.refresh(entry)
    return entry


async def _item_count(test_db) -> int:
    return await test_db.scalar(select(func.count()).select_from(TestItem))


async def _module_count(test_db) -> int:
    return await test_db.scalar(select(func.count()).select_from(TestModule))


async def _convert(client, token, entry, preview_data):
    return await client.post(
        f"/api/v1/knowledge/{entry.id}/convert",
        headers=_auth(token),
        json={"target_type": "rule", "preview_data": preview_data},
    )


# ---------------------------------------------------------------- 非法结构 → 400 且零写入
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_rules, expected_field",
    [
        ([{"source": "regex:x=([0-9]+)", "operator": "eq", "target": "1"}], "preview_data.conditional_rules"),
        ("not-an-object", "preview_data.conditional_rules"),
        (123, "preview_data.conditional_rules"),
        (None, "preview_data.conditional_rules"),
        ({"returncode_zero": True, "conditions": []}, "preview_data.conditional_rules.conditions"),
        ({"returncode_zero": True, "conditions": "x"}, "preview_data.conditional_rules.conditions"),
        (
            {"conditions": [{"source": "regex:x=([0-9]+)", "operator": "unknown_op", "target": "1"}]},
            "preview_data.conditional_rules.conditions.0.operator",
        ),
        (
            {"conditions": [{"source": "regex:([0-9", "operator": "eq", "target": "1"}]},
            "preview_data.conditional_rules.conditions.0.source",
        ),
        (
            {"conditions": [{"operator": "eq", "target": "1"}]},
            "preview_data.conditional_rules.conditions.0.source",
        ),
        (
            {"conditions": [{"source": "regex:x=([0-9]+)", "operator": "eq"}]},
            "preview_data.conditional_rules.conditions.0.target",
        ),
        (
            {"conditions": [{"source": "regex:x=([0-9.]+)", "operator": "approx_ratio", "target": "0"}]},
            "preview_data.conditional_rules.conditions.0.target",
        ),
    ],
)
async def test_invalid_rule_structure_returns_400_zero_write(
    client, admin_token, knowledge_entry, sample_item, test_db, bad_rules, expected_field
):
    """各类非法 conditional_rules 在写前 400，详情字段精确，且零资产/零修改写入。"""
    item_before = await _item_count(test_db)
    module_before = await _module_count(test_db)
    original_rules = sample_item.conditional_rules

    response = await _convert(
        client, admin_token, knowledge_entry,
        {"target_item_id": sample_item.id, "conditional_rules": bad_rules},
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]["field"] == expected_field, body
    assert body["details"].get("reason")
    # 零资产写入、目标测试项规则未被修改
    assert await _item_count(test_db) == item_before
    assert await _module_count(test_db) == module_before
    await test_db.refresh(sample_item)
    assert sample_item.conditional_rules == original_rules


@pytest.mark.asyncio
async def test_object_is_not_wrapped_into_list(
    client, admin_token, knowledge_entry, sample_item, test_db
):
    """合法对象规则写入后仍为对象（不得包成 list），判定引擎得到确定 pass。"""
    response = await _convert(
        client, admin_token, knowledge_entry,
        {"target_item_id": sample_item.id, "conditional_rules": _valid_rules()},
    )
    assert response.status_code == 200, response.text
    detail = response.json()["data"]["detail"]
    assert detail["asset_type"] == "rule"
    assert detail["rules_count"] == 1
    assert detail["target_item_id"] == sample_item.id

    await test_db.refresh(sample_item)
    assert isinstance(sample_item.conditional_rules, dict)
    assert isinstance(sample_item.conditional_rules["conditions"], list)
    assert sample_item.conditional_rules["conditions"][0]["operator"] == "gte"


@pytest.mark.asyncio
async def test_legal_conditions_produce_deterministic_pass_fail(
    client, admin_token, knowledge_entry, sample_item, test_db
):
    """合法 conditions 转换后：满足→pass，不满足→fail（不得默认 pass）。"""
    response = await _convert(
        client, admin_token, knowledge_entry,
        {"target_item_id": sample_item.id, "conditional_rules": _valid_rules()},
    )
    assert response.status_code == 200, response.text
    await test_db.refresh(sample_item)

    engine = JudgementEngine()
    passed = await engine.judge(
        output="value=150", returncode=0, item_name="x", item_description="",
        judgement_type="assertion", rules=sample_item.conditional_rules,
        rubric_criteria={}, device_context={},
    )
    assert passed.status == "pass", passed.to_dict()

    failed = await engine.judge(
        output="value=50", returncode=0, item_name="x", item_description="",
        judgement_type="assertion", rules=sample_item.conditional_rules,
        rubric_criteria={}, device_context={},
    )
    assert failed.status == "fail", failed.to_dict()


@pytest.mark.asyncio
async def test_repeated_rule_conversion_is_idempotent(
    client, admin_token, knowledge_entry, sample_item, test_db
):
    """相同规则对象重复转换不重复附加（规则幂等）。"""
    payload = {"target_item_id": sample_item.id, "conditional_rules": _valid_rules()}
    first = await _convert(client, admin_token, knowledge_entry, payload)
    assert first.status_code == 200, first.text
    second = await _convert(client, admin_token, knowledge_entry, payload)
    assert second.status_code == 200, second.text

    await test_db.refresh(sample_item)
    assert len(sample_item.conditional_rules["conditions"]) == 1
    assert second.json()["data"]["detail"]["rules_count"] == 1


@pytest.mark.asyncio
async def test_preview_rejects_invalid_rules_without_write(
    client, admin_token, knowledge_entry, sample_item, test_db, monkeypatch
):
    """预览返回的非法规则 → 400 且不写资产。"""
    item_before = await _item_count(test_db)

    async def fake_preview(self, entry, target_type, extra_hint=None):
        return {"target_item_name": sample_item.name, "conditional_rules": {"conditions": []}}

    monkeypatch.setattr(KnowledgeConverter, "preview", fake_preview)
    response = await client.post(
        f"/api/v1/knowledge/{knowledge_entry.id}/convert/preview",
        headers=_auth(admin_token),
        json={"target_type": "rule"},
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]["field"] == "preview_data.conditional_rules.conditions"
    assert await _item_count(test_db) == item_before


@pytest.mark.asyncio
async def test_preview_valid_rules_returns_normalized_object(
    client, admin_token, knowledge_entry, sample_item, monkeypatch
):
    """合法预览返回规范化对象（conditions 数组），不写资产。"""

    async def fake_preview(self, entry, target_type, extra_hint=None):
        return {"target_item_name": sample_item.name, "conditional_rules": _valid_rules()}

    monkeypatch.setattr(KnowledgeConverter, "preview", fake_preview)
    response = await client.post(
        f"/api/v1/knowledge/{knowledge_entry.id}/convert/preview",
        headers=_auth(admin_token),
        json={"target_type": "rule"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["target_type"] == "rule"
    assert isinstance(data["preview_data"]["conditional_rules"], dict)
    assert data["preview_data"]["conditional_rules"]["conditions"][0]["operator"] == "gte"


@pytest.mark.asyncio
async def test_operator_symbol_normalized_and_unknown_field_rejected(
    client, admin_token, knowledge_entry, sample_item
):
    """符号操作符写前规范化为内部名；未知条件字段 400。"""
    ok_rules = {"conditions": [{"source": "regex:v=([0-9]+)", "operator": ">=", "target": "10"}]}
    resp = await _convert(client, admin_token, knowledge_entry,
                          {"target_item_id": sample_item.id, "conditional_rules": ok_rules})
    assert resp.status_code == 200, resp.text

    unknown_field = {"conditions": [{"source": "regex:v=([0-9]+)", "operator": "eq",
                                     "target": "1", "unexpected": "x"}]}
    bad = await _convert(client, admin_token, knowledge_entry,
                         {"target_item_id": sample_item.id, "conditional_rules": unknown_field})
    assert bad.status_code == 400, bad.text
    assert bad.json()["details"]["field"] == "preview_data.conditional_rules.conditions.0"
