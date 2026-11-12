"""判定引擎：测试项结果的唯一判定入口（T-06 失败关闭 / 原生 SKIP）。

优先级严格对齐 docs/design/execution-state-machine.md 第 2 节：
timeout（执行器先行） > 内部异常 error（执行器先行） > rc!=0 fail
> rc=0 独立整行原生 SKIP > fail_pattern/双命中 fail
> assertion / rubric / ai_fallback > 无配置/空规则/非法规则 = error。

本模块不再产出 ``unknown``：任何无法形成有效判定的分支一律 error，
也不再有「rc=0 默认 pass」。
"""
import re
import math
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass

from app.services.llm_client import LLMClient, JUDGEMENT_SCHEMA
from app.services.knowledge_judge_context import JudgeKnowledgeContext, format_context_for_llm

logger = logging.getLogger(__name__)

# 条件规则允许的操作符（符号写法在校验前归一化）。
VALID_OPERATORS = frozenset({"eq", "gt", "gte", "lt", "lte", "approx_ratio", "contains"})

# 原生 SKIP 行：仅整行 `RESULT: SKIP` 或 `RESULT: SKIP: <原因>`，
# 允许前后空白；标记本身区分大小写；`foo RESULT: SKIP`、`RESULT: SKIPPED`、
# 自然语言中包含该短语均不匹配（§2 行4 / SKIP-02）。
_NATIVE_SKIP_PREFIX = "RESULT: SKIP"
_NATIVE_SKIP_WITH_REASON = "RESULT: SKIP:"


def find_native_skip(output: str) -> Optional[str]:
    """返回原生 SKIP 行的原因；无原因返回 ""，未出现原生 SKIP 行返回 None。

    只认「独立整行」：逐行 strip 后必须恰为 `RESULT: SKIP`，或以
    `RESULT: SKIP:` 开头；大小写敏感。多行输出中其他自然语言不受影响。
    """
    if not isinstance(output, str):
        return None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped == _NATIVE_SKIP_PREFIX:
            return ""
        if stripped.startswith(_NATIVE_SKIP_WITH_REASON):
            return stripped[len(_NATIVE_SKIP_WITH_REASON):].strip()
    return None


def extract_fail_reason(output: str) -> str:
    """从输出中提取简短失败原因（不含堆栈）。"""
    lines = (output or "").split("\n")
    for line in lines:
        if any(keyword in line.lower() for keyword in ("error", "fail", "exception", "crash")):
            return line.strip()[:500]
    if lines:
        return lines[-1].strip()[:500]
    return "未知错误"


def _unavailable(reason: str, judgement_type: str = "", **kwargs) -> "JudgementResult":
    """构造「判定配置不可用」的 error 结果（§2 行11，绝不为 pass）。"""
    return JudgementResult(
        status="error",
        confidence=0.0,
        metrics=kwargs.get("metrics"),
        evidence=kwargs.get("evidence") or [reason],
        fail_reason=reason,
        judgement_type=judgement_type,
    )


def parse_patterns(output: str, config: Optional[Dict[str, Any]]) -> "JudgementResult":
    """按 §2 行5/6/7/11 解析 pass_pattern / fail_pattern / extract_pattern。

    - fail_pattern 命中（含 pass/fail 双命中）→ fail；
    - 已配置 pass_pattern 且命中 → pass，未命中 → fail；
    - 非法正则、结构非法、无可用通过判据（含「仅 fail_pattern 且未命中」）→ error。
    移除旧语义：pass_pattern 缺失时默认 pass、pass_pattern 未命中时返回 unknown。
    """
    if config is None:
        config = {}
    if not isinstance(config, dict):
        return _unavailable("判定配置不可用：result_parse 结构非法", "pattern")

    fail_pattern = config.get("fail_pattern")
    pass_pattern = config.get("pass_pattern")
    extract_pattern = config.get("extract_pattern")
    metrics: Dict[str, Any] = {}

    try:
        fail_hit = bool(fail_pattern and re.search(str(fail_pattern), output, re.IGNORECASE))
        pass_hit = bool(pass_pattern and re.search(str(pass_pattern), output, re.IGNORECASE))
        if extract_pattern:
            values = re.findall(str(extract_pattern), output)
            if values:
                metrics["values"] = values
    except re.error as exc:
        return _unavailable(f"判定配置不可用：非法正则 ({exc})", "pattern")

    if fail_hit:
        detail = extract_fail_reason(output)
        return JudgementResult(
            status="fail",
            confidence=1.0,
            metrics=metrics,
            evidence=[f"失败模式命中: {fail_pattern}"],
            fail_reason=f"失败模式命中: {fail_pattern}；{detail}",
            judgement_type="pattern",
        )
    if pass_pattern:
        if pass_hit:
            return JudgementResult(
                status="pass",
                confidence=1.0,
                metrics=metrics,
                evidence=[f"通过模式命中: {pass_pattern}"],
                judgement_type="pattern",
            )
        return JudgementResult(
            status="fail",
            confidence=1.0,
            metrics=metrics,
            evidence=[f"pass_pattern 未命中: {pass_pattern}"],
            fail_reason=f"pass_pattern 未命中: {pass_pattern}（未满足断言）",
            judgement_type="pattern",
        )
    if fail_pattern:
        return _unavailable(
            "判定配置不可用：仅配置 fail_pattern 且未命中，缺少可用的通过判据",
            "pattern",
            metrics=metrics,
        )
    return _unavailable(
        "判定配置不可用：未配置判定规则（pass_pattern/断言条件/评分规则/AI 兜底）",
        "pattern",
        metrics=metrics,
    )


@dataclass
class JudgementResult:
    """判定结果：status 只取 pass/fail/skip/error/timeout 语义中的前四类。

    不再产出 unknown；skip 的原生原因保存在 fail_reason，贯通
    record.fail_reason / 报告 / WS 数据链路。
    """
    status: str  # pass/fail/skip/error
    confidence: float
    score: Optional[int] = None
    metrics: Dict[str, Any] = None
    evidence: List[str] = None
    fail_reason: str = ""
    suggestions: str = ""
    judgement_type: str = ""  # assertion / rubric / ai_fallback / pattern / native_skip

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
    """基于规则的判定器（assertion / rubric）。"""

    def judge_assertion(
        self,
        output: str,
        returncode: int,
        rules: Dict[str, Any],
        spec: Dict[str, Any] = None
    ) -> JudgementResult:
        """执行条件式断言判定（§2 行3 兜底 / 行6 / 行7 / 行11）。

        所有条件完整执行且为 true → pass；任一有效条件为 false → fail（指出未满足
        断言）；无法提取、未知操作符、非法正则、规则结构非法 → error，
        绝不回退默认 pass。
        """
        spec = spec or {}
        if not isinstance(rules, dict):
            return _unavailable("判定配置不可用：断言规则结构非法（非对象）", "assertion")

        # 行3：直接调用本方法时同样遵守「非零退出码即 fail」。
        if rules.get("returncode_zero", True) and returncode not in (0, None):
            return JudgementResult(
                status="fail",
                confidence=1.0,
                evidence=[f"命令返回码非零: {returncode}"],
                fail_reason=f"命令返回码非零: {returncode}",
                judgement_type="assertion"
            )

        conditions = rules.get("conditions")
        if not conditions or not isinstance(conditions, list):
            return _unavailable("判定配置不可用：断言条件规则为空", "assertion")

        evidence: List[str] = []
        metrics: Dict[str, Any] = {}

        for condition in conditions:
            if not isinstance(condition, dict):
                return _unavailable("判定配置不可用：断言条件结构非法（非对象）", "assertion")
            source = condition.get("source")
            operator = condition.get("operator")
            target = condition.get("target")
            tolerance = condition.get("tolerance", "0%")
            on_fail = condition.get("on_fail") or "未满足断言"

            if not isinstance(source, str) or not source or not isinstance(operator, str) or not operator:
                return _unavailable("判定配置不可用：断言条件缺少 source/operator", "assertion")
            if target is None or target == "" or isinstance(target, (list, dict)):
                return _unavailable("判定配置不可用：断言条件缺少 target", "assertion")
            operator = self._normalize_operator(operator)
            if operator not in VALID_OPERATORS:
                return _unavailable(f"判定配置不可用：未知操作符 {operator}", "assertion")

            try:
                actual_value = self._resolve_source(source, output)
            except re.error as exc:
                return _unavailable(f"判定配置不可用：非法正则 ({exc})", "assertion")
            if actual_value is None:
                return _unavailable(f"判定配置不可用：无法从输出提取 source={source}", "assertion")

            expected_value = self._resolve_target(target, spec)
            if expected_value is None:
                return _unavailable(f"判定配置不可用：无法解析期望值 target={target}", "assertion")

            # 非数值 / NaN/Inf / approx_ratio 零目标 → 运行时 error 兜底（V1-02）
            if operator in ("gt", "gte", "lt", "lte", "approx_ratio"):
                try:
                    num_actual = float(actual_value)
                    num_expected = float(expected_value)
                except (ValueError, TypeError):
                    return _unavailable(
                        f"判定配置不可用：非数值比较 {actual_value!r} {operator} {expected_value!r}",
                        "assertion",
                    )
                if not (math.isfinite(num_actual) and math.isfinite(num_expected)):
                    return _unavailable("判定配置不可用：比较值非有限数值（NaN/Inf）", "assertion")
                if operator == "approx_ratio" and num_expected == 0:
                    return _unavailable("判定配置不可用：approx_ratio 目标为 0（禁止零目标）", "assertion")

            metrics[source.split(":")[-1]] = actual_value
            try:
                ok, reason = self._compare(actual_value, operator, expected_value, tolerance)
            except (ValueError, TypeError, ZeroDivisionError, KeyError) as exc:
                return _unavailable(f"判定配置不可用：断言规则执行异常 ({exc})", "assertion")
            if not ok:
                return JudgementResult(
                    status="fail",
                    confidence=1.0,
                    metrics=metrics,
                    evidence=[reason],
                    fail_reason=f"{on_fail}：{reason}" if on_fail else reason,
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
    ) -> JudgementResult:
        """执行 Rubrics 评分判定（§2 行8 / 行9 / 行11）。

        有效评分达到阈值 → pass，低于阈值 → fail；无有效评分（无规则、
        提取失败、非法正则、结构非法、评分异常）→ error。
        """
        if not isinstance(criteria, dict) or not criteria:
            return _unavailable("判定配置不可用：rubric 评分规则为空", "rubric")

        total_score = 0
        total_max = 0
        evidence: List[str] = []
        metrics: Dict[str, Any] = {}

        for criterion_name, criterion_config in criteria.items():
            if not isinstance(criterion_config, dict):
                return _unavailable(
                    f"判定配置不可用：rubric 规则结构非法 ({criterion_name})", "rubric"
                )
            extract_pattern = criterion_config.get("extract_pattern")
            levels = criterion_config.get("levels", [])
            if not isinstance(extract_pattern, str) or not extract_pattern:
                return _unavailable(
                    f"判定配置不可用：rubric 缺少 extract_pattern ({criterion_name})", "rubric"
                )
            try:
                matches = re.findall(extract_pattern, output)
            except re.error as exc:
                return _unavailable(f"判定配置不可用：rubric 非法正则 ({exc})", "rubric")
            if not matches:
                return _unavailable(
                    f"判定配置不可用：rubric 无法从输出提取评分依据 ({criterion_name})", "rubric"
                )
            try:
                value = float(matches[0])
            except (ValueError, TypeError):
                return _unavailable(
                    f"判定配置不可用：rubric 提取值非数值 ({criterion_name})", "rubric"
                )
            metrics[criterion_name] = value

            try:
                source = criterion_config.get("source", "fixed")
                if source == "baseline":
                    baseline_key = criterion_config.get("metric", criterion_name)
                    baseline = (baselines or {}).get(baseline_key)
                    fallback_levels = criterion_config.get("fallback_levels") or levels
                    if baseline:
                        baseline_value = self._resolve_baseline_value(
                            baseline, criterion_config.get("baseline_field", "avg_value")
                        )
                        if baseline_value is None or not math.isfinite(baseline_value):
                            return _unavailable(
                                f"判定配置不可用：rubric 基线值非数值 ({criterion_name})", "rubric"
                            )
                        operator = self._normalize_operator(criterion_config.get("operator", ">="))
                        if operator == "approx_ratio" and baseline_value == 0:
                            return _unavailable(
                                f"判定配置不可用：rubric approx_ratio 基线为 0 ({criterion_name})", "rubric"
                            )
                        tolerance = criterion_config.get("tolerance", "0%")
                        ok, reason = self._compare(value, operator, baseline_value, tolerance)
                        score = 4 if ok else 1
                        evidence.append(
                            f"{criterion_name}: {value} {operator} 基线 {baseline_value} ({reason}) -> 得分 {score}"
                        )
                    elif fallback_levels:
                        score = self._score_by_levels(value, fallback_levels)
                        evidence.append(
                            f"{criterion_name}: {value} -> 得分 {score} (无基线，使用固定阈值)"
                        )
                    else:
                        return _unavailable(
                            f"判定配置不可用：rubric 基线缺失且无 fallback_levels ({criterion_name})",
                            "rubric",
                        )
                else:
                    if not levels or not isinstance(levels, list):
                        return _unavailable(
                            f"判定配置不可用：rubric 缺少 levels ({criterion_name})", "rubric"
                        )
                    score = self._score_by_levels(value, levels)
                    evidence.append(f"{criterion_name}: {value} -> 得分 {score}")
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                return _unavailable(f"判定配置不可用：rubric 评分规则执行异常 ({exc})", "rubric")

            total_score += score
            total_max += 4  # 统一按 4 分制计算

        if total_max == 0:
            return _unavailable("判定配置不可用：rubric 无有效评分", "rubric")

        final_score = round(total_score / total_max * 4)
        status = "pass" if final_score >= 2 else "fail"
        return JudgementResult(
            status=status,
            confidence=1.0,
            score=final_score,
            metrics=metrics,
            evidence=evidence,
            judgement_type="rubric",
            fail_reason="" if status == "pass" else f"Rubrics 评分低于及格线（得分 {final_score}）"
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

    def _resolve_source(self, source: str, output: str) -> Optional[Any]:
        """从命令输出中解析实际值；无法提取返回 None。"""
        if source.startswith("regex:"):
            pattern = source[6:]
            if not pattern:
                return None
            matches = re.findall(pattern, output, re.IGNORECASE)
            if not matches or matches[0] is None or matches[0] == "":
                return None
            try:
                return float(matches[0])
            except (ValueError, TypeError):
                return matches[0]
        elif source.startswith("node:"):
            # 节点路径，在执行引擎中应已读取，这里不支持
            return None
        return None

    def _resolve_target(self, target: Any, spec: Dict[str, Any]) -> Optional[Any]:
        """解析期望值；无法解析返回 None。"""
        if isinstance(target, str) and target.startswith("spec:"):
            key = target[5:]
            return spec.get(key) if key in spec else None
        if isinstance(target, bool):
            return target
        if isinstance(target, (int, float)):
            return float(target)
        if isinstance(target, str):
            try:
                return float(target)
            except ValueError:
                return target or None
        return None

    def _compare(
        self,
        actual: Any,
        operator: str,
        expected: Any,
        tolerance: str = "0%"
    ) -> Tuple[bool, str]:
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

            # V1-02：零目标不是合法 approx_ratio 配置，任何实际值都不得直接判通过。
            if not (math.isfinite(a) and math.isfinite(e)) or e == 0:
                return False, f"approx_ratio 目标为 0 或非有限数值（{expected}），非法配置"
            tol = float(str(tolerance).replace("%", "")) / 100.0
            ratio = abs(a - e) / e
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
        """调用 LLM 进行判定（§2 行10 / 行11）。

        LLM schema 允许返回 unknown/skip，但二者与缺失字段、异常一样
        属于「AI 无有效结论」，一律落 error，绝不落 unknown 或 pass。
        """
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

            if not isinstance(result, dict):
                return JudgementResult(
                    status="error",
                    confidence=0.0,
                    fail_reason="AI 判定无有效结论（返回结构非法）",
                    judgement_type="ai_fallback"
                )

            status = result.get("status")
            if status not in ("pass", "fail"):
                # schema 中的 unknown（以及 skip/缺失/非法值）统一落 error
                return JudgementResult(
                    status="error",
                    confidence=0.0,
                    evidence=result.get("evidence", []) or [],
                    fail_reason=f"AI 判定无有效结论（status={status!r}）",
                    suggestions=result.get("suggestions", ""),
                    judgement_type="ai_fallback"
                )

            return JudgementResult(
                status=status,
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
                status="error",
                confidence=0.0,
                fail_reason=f"AI 判定服务异常: {exc}",
                suggestions="请检查 LLM 配置或稍后重试",
                judgement_type="ai_fallback"
            )


class JudgementEngine:
    """组合判定引擎：按状态机 §2 优先级形成唯一判定。

    行1（timeout）与行2（执行器内部异常）由执行引擎/任务执行器先行处理，
    不进入本方法；此处实现行3～行11。
    """

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
        knowledge_context: str = "",
        result_parse: Optional[Dict[str, Any]] = None
    ) -> JudgementResult:
        """执行唯一判定，返回的 status 只可能是 pass/fail/skip/error。"""
        # 行3：非零退出码优先于任何输出内容（SKIP / pass_pattern 均不得改判）。
        if returncode not in (0, None):
            return JudgementResult(
                status="fail",
                confidence=1.0,
                evidence=[f"命令返回码非零: {returncode}"],
                fail_reason=f"命令返回码非零: {returncode}（退出码 {returncode}）",
                judgement_type="returncode"
            )

        # 行4：rc=0 且输出存在独立整行原生 SKIP → skip，原因完整保存到 fail_reason。
        skip_reason = find_native_skip(output)
        if skip_reason is not None:
            return JudgementResult(
                status="skip",
                confidence=1.0,
                evidence=[f"原生 SKIP 行: RESULT: SKIP: {skip_reason}" if skip_reason else "原生 SKIP 行: RESULT: SKIP"],
                fail_reason=skip_reason,
                judgement_type="native_skip"
            )

        # 行11（前置校验，V1-02）：先按原始 JSON 类型校验根结构，再做默认值处理。
        # `rules=[]`/标量/null 等非法根结构必须直接 error，绝不能被 truthiness
        # （`or {}`）擦除成空对象后被 pass_pattern 变成 pass。
        if not isinstance(rules, dict):
            return _unavailable(
                f"判定配置不可用：conditional_rules 非法根结构（{type(rules).__name__}，必须为对象）"
            )
        if result_parse is not None and not isinstance(result_parse, dict):
            return _unavailable(
                f"判定配置不可用：result_parse 非法根结构（{type(result_parse).__name__}，必须为对象）"
            )
        if rubric_criteria is not None and not isinstance(rubric_criteria, dict):
            return _unavailable(
                f"判定配置不可用：rubric_criteria 非法根结构（{type(rubric_criteria).__name__}，必须为对象）"
            )
        result_parse = result_parse or {}

        # 行5：fail_pattern 命中（含 pass/fail 双命中）→ fail，全局生效。
        fail_pattern = result_parse.get("fail_pattern")
        if fail_pattern:
            try:
                fail_hit = bool(re.search(str(fail_pattern), output, re.IGNORECASE))
            except re.error as exc:
                return _unavailable(f"判定配置不可用：fail_pattern 非法正则 ({exc})", "pattern")
            if fail_hit:
                return JudgementResult(
                    status="fail",
                    confidence=1.0,
                    evidence=[f"失败模式命中: {fail_pattern}"],
                    fail_reason=f"失败模式命中: {fail_pattern}；{extract_fail_reason(output)}",
                    judgement_type="pattern"
                )

        rules = rules or {}
        device_context = device_context if isinstance(device_context, dict) else {}

        # 行6/行7：assertion（条件规则或正则模式）；行11：配置缺失/非法结构。
        if judgement_type == "assertion":
            if rules.get("conditions"):
                return self.rule_judger.judge_assertion(output, returncode, rules, spec)
            return parse_patterns(output, result_parse)

        # 行8/行9/行11：rubric 有效评分。
        if judgement_type == "rubric":
            return self.rule_judger.judge_rubric(
                output,
                rubric_criteria or {},
                device_model=device_context.get("model"),
                baselines=baselines
            )

        # 行10/行11：ai_fallback 明确 pass/fail 或 error。
        if judgement_type == "ai_fallback":
            return await self.ai_judger.judge(
                output, item_name, item_description, device_context, ai_context, knowledge_context
            )

        # 行11：未知 judgement_type 等一切无有效判定的情况，绝不回退默认 pass。
        return _unavailable(f"判定配置不可用：未知 judgement_type={judgement_type!r}")
