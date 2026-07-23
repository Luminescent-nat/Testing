import re
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from app.services.llm_client import LLMClient, JUDGEMENT_SCHEMA
from app.services.knowledge_judge_context import JudgeKnowledgeContext, format_context_for_llm

logger = logging.getLogger(__name__)


@dataclass
class JudgementResult:
    """判定结果"""
    status: str  # pass/fail/skip/unknown
    confidence: float
    score: Optional[int] = None
    metrics: Dict[str, Any] = None
    evidence: List[str] = None
    fail_reason: str = ""
    suggestions: str = ""
    judgement_type: str = ""  # assertion / rubric / ai_fallback

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "confidence": self.confidence,
            "score": self.score,
            "metrics": self.metrics or {},
            "evidence": self.evidence or [],
            "fail_reason": self.fail_reason,
            "suggestions": self.suggestions,
            "judgement_type": self.judgement_type
        }


class RuleBasedJudger:
    """基于规则的判定器"""

    def judge_assertion(
        self,
        output: str,
        returncode: int,
        rules: Dict[str, Any],
        spec: Dict[str, Any] = None
    ) -> Optional[JudgementResult]:
        """执行条件式断言判定。"""
        spec = spec or {}
        evidence = []
        metrics = {}

        conditions = rules.get("conditions", [])

        # 先尝试按 returncode_zero 判定
        if rules.get("returncode_zero", True) and returncode != 0:
            return JudgementResult(
                status="fail",
                confidence=1.0,
                evidence=[f"命令返回码非零: {returncode}"],
                fail_reason=f"命令返回码非零: {returncode}",
                judgement_type="assertion"
            )

        if not conditions:
            return None

        for condition in conditions:
            source = condition.get("source", "")
            operator = condition.get("operator", "")
            target = condition.get("target", "")
            tolerance = condition.get("tolerance", "0%")
            on_fail = condition.get("on_fail", "条件不满足")

            # 解析 source
            actual_value = self._resolve_source(source, output)
            if actual_value is None:
                # 无法从输出中提取，规则无法判定
                return None

            # 解析 target
            expected_value = self._resolve_target(target, spec)
            if expected_value is None:
                return None

            # 记录指标
            metrics[source.split(":")[-1]] = actual_value

            # 比较
            ok, reason = self._compare(actual_value, operator, expected_value, tolerance)
            if not ok:
                return JudgementResult(
                    status="fail",
                    confidence=1.0,
                    metrics=metrics,
                    evidence=[reason],
                    fail_reason=on_fail or reason,
                    judgement_type="assertion"
                )
            evidence.append(reason)

        return JudgementResult(
            status="pass",
            confidence=1.0,
            metrics=metrics,
            evidence=evidence,
            judgement_type="assertion"
        )

    def judge_rubric(
        self,
        output: str,
        criteria: Dict[str, Any],
        device_model: Optional[str] = None,
        item_id: Optional[int] = None,
        baselines: Optional[Dict[str, Any]] = None
    ) -> Optional[JudgementResult]:
        """执行 Rubrics 评分判定，支持固定阈值与基线阈值。"""
        if not criteria:
            return None

        total_score = 0
        total_max = 0
        evidence = []
        metrics = {}

        for criterion_name, criterion_config in criteria.items():
            extract_pattern = criterion_config.get("extract_pattern")
            levels = criterion_config.get("levels", [])

            if not extract_pattern:
                return None

            matches = re.findall(extract_pattern, output)
            if not matches:
                return None

            try:
                value = float(matches[0])
            except (ValueError, TypeError):
                return None

            metrics[criterion_name] = value

            # 判断评分逻辑：基线模式 或 固定阈值模式
            source = criterion_config.get("source", "fixed")
            score = 1

            if source == "baseline":
                baseline_key = criterion_config.get("metric", criterion_name)
                baseline = (baselines or {}).get(baseline_key)
                fallback_levels = criterion_config.get("fallback_levels") or levels

                if baseline:
                    baseline_value = self._resolve_baseline_value(
                        baseline, criterion_config.get("baseline_field", "avg_value")
                    )
                    operator = self._normalize_operator(criterion_config.get("operator", ">="))
                    tolerance = criterion_config.get("tolerance", "0%")
                    ok, reason = self._compare(value, operator, baseline_value, tolerance)
                    # 基线模式下：满足则 4 分，不满足则 1 分
                    score = 4 if ok else 1
                    evidence.append(
                        f"{criterion_name}: {value} {operator} 基线 {baseline_value} ({reason}) -> 得分 {score}"
                    )
                elif fallback_levels:
                    # 无基线时回落到固定阈值
                    score = self._score_by_levels(value, fallback_levels)
                    evidence.append(
                        f"{criterion_name}: {value} -> 得分 {score} (无基线，使用固定阈值)"
                    )
                else:
                    return None
            else:
                if not levels:
                    return None
                score = self._score_by_levels(value, levels)
                evidence.append(f"{criterion_name}: {value} -> 得分 {score}")

            total_score += score
            total_max += 4  # 统一按 4 分制计算

        if total_max == 0:
            return None

        final_score = round(total_score / total_max * 4)
        status = "pass" if final_score >= 2 else "fail"

        return JudgementResult(
            status=status,
            confidence=1.0,
            score=final_score,
            metrics=metrics,
            evidence=evidence,
            judgement_type="rubric",
            fail_reason="" if status == "pass" else "Rubrics 评分低于及格线"
        )

    @staticmethod
    def _score_by_levels(value: float, levels: List[Dict[str, Any]]) -> int:
        """按固定阈值等级评分。"""
        for level in sorted(levels, key=lambda x: x.get("score", 1), reverse=True):
            threshold = level.get("threshold")
            if threshold is not None and value >= threshold:
                return level.get("score", 1)
        return 1

    @staticmethod
    def _normalize_operator(operator: str) -> str:
        """把常见比较符号统一为内部操作符。"""
        mapping = {
            ">=": "gte",
            "<=": "lte",
            ">": "gt",
            "<": "lt",
            "=": "eq",
            "==": "eq",
        }
        return mapping.get(operator, operator)

    @staticmethod
    def _resolve_baseline_value(baseline: Any, field: str) -> Optional[float]:
        """从基线对象或字典中解析数值。"""
        if isinstance(baseline, dict):
            raw = baseline.get(field)
        else:
            raw = getattr(baseline, field, None)
        if raw is None:
            return None
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None

    def _resolve_source(self, source: str, output: str) -> Optional[float]:
        """从命令输出中解析实际值。"""
        if source.startswith("regex:"):
            pattern = source[6:]
            matches = re.findall(pattern, output, re.IGNORECASE)
            if not matches:
                return None
            try:
                return float(matches[0])
            except (ValueError, TypeError):
                return matches[0]
        elif source.startswith("node:"):
            # 节点路径，在执行引擎中应已读取，这里暂不支持
            return None
        return None

    def _resolve_target(self, target: str, spec: Dict[str, Any]) -> Optional[Any]:
        """解析期望值。"""
        if target.startswith("spec:"):
            key = target[5:]
            return spec.get(key)
        try:
            return float(target)
        except ValueError:
            return target

    def _compare(
        self,
        actual: Any,
        operator: str,
        expected: Any,
        tolerance: str = "0%"
    ) -> tuple:
        """比较实际值与期望值。"""
        if operator == "eq":
            ok = actual == expected
            return ok, f"{actual} {'==' if ok else '!='} {expected}"

        if operator in ("gt", "gte", "lt", "lte"):
            try:
                a = float(actual)
                e = float(expected)
            except (ValueError, TypeError):
                return False, f"无法比较非数值: {actual} {operator} {expected}"

            ops = {
                "gt": lambda x, y: x > y,
                "gte": lambda x, y: x >= y,
                "lt": lambda x, y: x < y,
                "lte": lambda x, y: x <= y
            }
            ok = ops[operator](a, e)
            return ok, f"{a} {operator} {e} -> {'满足' if ok else '不满足'}"

        if operator == "approx_ratio":
            try:
                a = float(actual)
                e = float(expected)
            except (ValueError, TypeError):
                return False, f"无法计算比例: {actual} vs {expected}"

            tol = float(tolerance.replace("%", "")) / 100.0
            ratio = abs(a - e) / e if e != 0 else 0
            ok = ratio <= tol
            return ok, f"{a} 与 {e} 偏差 {ratio*100:.1f}% {'在' if ok else '超出'} 阈值 {tolerance}"

        if operator == "contains":
            ok = str(expected) in str(actual)
            return ok, f"{actual} {'包含' if ok else '不包含'} {expected}"

        return False, f"未知操作符: {operator}"


class AIJudger:
    """基于 LLM 的兜底判定器，支持注入知识库上下文。"""

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client or LLMClient.get_default_client()

    async def judge(
        self,
        output: str,
        item_name: str,
        item_description: str,
        device_context: Dict[str, Any],
        ai_context: str = "",
        knowledge_context: str = ""
    ) -> JudgementResult:
        """调用 LLM 进行判定。"""
        system_prompt = (
            "你是一位硬件测试专家。请根据测试命令输出、设备信息、用例上下文和知识库参考资料，"
            "判断该测试项是否通过。必须返回结构化 JSON。"
        )

        user_prompt = f"""测试项: {item_name}
描述: {item_description}
设备信息: {device_context}
判定上下文: {ai_context or '无额外说明'}

知识库参考:
{knowledge_context or '无'}

命令输出:
```
{output[:4000]}
```

请判断该测试是否通过，并给出置信度、关键指标、判定依据、失败原因（如有）和优化建议。
"""

        try:
            result = await self.client.chat_completion_structured(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                schema=JUDGEMENT_SCHEMA
            )

            return JudgementResult(
                status=result.get("status", "unknown"),
                confidence=result.get("confidence", 0.5),
                score=result.get("score"),
                metrics=result.get("metrics", {}),
                evidence=result.get("evidence", []),
                fail_reason=result.get("fail_reason", ""),
                suggestions=result.get("suggestions", ""),
                judgement_type="ai_fallback"
            )
        except Exception as exc:
            logger.exception("AI 判定失败: %s", exc)
            return JudgementResult(
                status="unknown",
                confidence=0.0,
                fail_reason=f"AI 判定服务异常: {exc}",
                suggestions="请检查 LLM 配置或稍后重试",
                judgement_type="ai_fallback"
            )


class JudgementEngine:
    """组合判定引擎：规则优先，AI 兜底。"""

    def __init__(self, ai_client: Optional[LLMClient] = None):
        self.rule_judger = RuleBasedJudger()
        self.ai_judger = AIJudger(ai_client)

    async def judge(
        self,
        output: str,
        returncode: int,
        item_name: str,
        item_description: str,
        judgement_type: str,
        rules: Dict[str, Any],
        rubric_criteria: Dict[str, Any],
        device_context: Dict[str, Any],
        ai_context: str = "",
        spec: Dict[str, Any] = None,
        baselines: Optional[Dict[str, Any]] = None,
        knowledge_context: str = ""
    ) -> JudgementResult:
        """执行判定。"""
        # 1. 规则断言
        if judgement_type == "assertion":
            result = self.rule_judger.judge_assertion(output, returncode, rules or {}, spec)
            if result:
                return result

        # 2. Rubrics 评分
        if judgement_type == "rubric":
            result = self.rule_judger.judge_rubric(
                output,
                rubric_criteria or {},
                device_model=device_context.get("model"),
                baselines=baselines
            )
            if result:
                return result

        # 3. AI 兜底（仅当配置为 ai_fallback 时）
        if judgement_type == "ai_fallback":
            return await self.ai_judger.judge(
                output, item_name, item_description, device_context, ai_context, knowledge_context
            )

        # 4. 默认：根据返回码
        if returncode == 0:
            return JudgementResult(
                status="pass",
                confidence=1.0,
                evidence=["命令返回码为 0"],
                judgement_type="assertion"
            )
        else:
            return JudgementResult(
                status="fail",
                confidence=1.0,
                evidence=[f"命令返回码非零: {returncode}"],
                fail_reason=f"命令返回码非零: {returncode}",
                judgement_type="assertion"
            )
