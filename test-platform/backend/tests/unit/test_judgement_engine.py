"""判定引擎单元测试。"""
import pytest

from app.services.judgement_engine import RuleBasedJudger, JudgementEngine
from app.services.llm_client import LLMClient


@pytest.mark.asyncio
async def test_rule_assertion_eq_pass():
    judger = RuleBasedJudger()
    rules = {
        "conditions": [
            {"source": "regex:value=(\\d+)", "operator": "eq", "target": "100"}
        ]
    }
    result = judger.judge_assertion("value=100", 0, rules)
    assert result.status == "pass"


@pytest.mark.asyncio
async def test_rule_assertion_gt_fail():
    judger = RuleBasedJudger()
    rules = {
        "conditions": [
            {"source": "regex:value=(\\d+)", "operator": "gt", "target": "200"}
        ]
    }
    result = judger.judge_assertion("value=100", 0, rules)
    assert result.status == "fail"


@pytest.mark.asyncio
async def test_rule_assertion_gte():
    judger = RuleBasedJudger()
    rules = {
        "conditions": [
            {"source": "regex:value=(\\d+)", "operator": "gte", "target": "100"}
        ]
    }
    assert judger.judge_assertion("value=100", 0, rules).status == "pass"


@pytest.mark.asyncio
async def test_rule_assertion_approx_ratio():
    judger = RuleBasedJudger()
    rules = {
        "conditions": [
            {
                "source": "regex:value=(\\d+)",
                "operator": "approx_ratio",
                "target": "100",
                "tolerance": "5%",
            }
        ]
    }
    assert judger.judge_assertion("value=103", 0, rules).status == "pass"
    assert judger.judge_assertion("value=110", 0, rules).status == "fail"


@pytest.mark.asyncio
async def test_rule_assertion_contains():
    judger = RuleBasedJudger()
    rules = {
        "conditions": [
            {"source": "regex:status=(\\w+)", "operator": "contains", "target": "ok"}
        ]
    }
    assert judger.judge_assertion("status=okok", 0, rules).status == "pass"


@pytest.mark.asyncio
async def test_rule_assertion_returncode_nonzero():
    judger = RuleBasedJudger()
    rules = {"returncode_zero": True, "conditions": []}
    result = judger.judge_assertion("", 1, rules)
    assert result.status == "fail"
    assert "返回码非零" in result.fail_reason


@pytest.mark.asyncio
async def test_rule_assertion_with_spec_target():
    judger = RuleBasedJudger()
    rules = {
        "conditions": [
            {"source": "regex:value=(\\d+)", "operator": "gte", "target": "spec:total_mb"}
        ]
    }
    result = judger.judge_assertion("value=2048", 0, rules, spec={"total_mb": 1024})
    assert result.status == "pass"


@pytest.mark.asyncio
async def test_rubric_scoring_pass():
    judger = RuleBasedJudger()
    criteria = {
        "bw_mbps": {
            "extract_pattern": r"bw_mbps\s*:\s*([\d.]+)",
            "levels": [
                {"score": 4, "threshold": 200},
                {"score": 3, "threshold": 150},
                {"score": 2, "threshold": 100},
                {"score": 1},
            ],
        }
    }
    result = judger.judge_rubric("bw_mbps: 250", criteria)
    assert result.status == "pass"
    assert result.score == 4


@pytest.mark.asyncio
async def test_rubric_scoring_fail():
    judger = RuleBasedJudger()
    criteria = {
        "bw_mbps": {
            "extract_pattern": r"bw_mbps\s*:\s*([\d.]+)",
            "levels": [
                {"score": 4, "threshold": 200},
                {"score": 3, "threshold": 150},
                {"score": 2, "threshold": 100},
                {"score": 1},
            ],
        }
    }
    result = judger.judge_rubric("bw_mbps: 50", criteria)
    assert result.status == "fail"


@pytest.mark.asyncio
async def test_judgement_engine_default_returncode():
    engine = JudgementEngine()
    result = await engine.judge(
        output="",
        returncode=0,
        item_name="test",
        item_description="",
        judgement_type="assertion",
        rules={},
        rubric_criteria={},
        device_context={},
    )
    assert result.status == "pass"


@pytest.mark.asyncio
async def test_judgement_engine_default_returncode_fail():
    engine = JudgementEngine()
    result = await engine.judge(
        output="",
        returncode=1,
        item_name="test",
        item_description="",
        judgement_type="assertion",
        rules={},
        rubric_criteria={},
        device_context={},
    )
    assert result.status == "fail"


@pytest.mark.asyncio
async def test_ai_fallback_without_llm():
    """TC-JUDGE-012: 未配置 LLM API Key 时，AI fallback 应降级返回 unknown。"""
    engine = JudgementEngine(ai_client=LLMClient(api_key=""))
    result = await engine.judge(
        output="some output",
        returncode=0,
        item_name="ai_test",
        item_description="AI fallback test",
        judgement_type="ai_fallback",
        rules={},
        rubric_criteria={},
        device_context={"model": "rk3568"},
    )
    assert result.status == "unknown"
    assert result.judgement_type == "ai_fallback"
    assert "LLM API Key 未配置" in result.fail_reason
