import re
import logging
from typing import Dict, Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, TestModule, TestItem
from app.services.llm_client import LLMClient, TASK_PLAN_SCHEMA
from app.services.knowledge_matcher import get_device_knowledge

logger = logging.getLogger(__name__)


class NLTaskPlanner:
    """自然语言任务规划器，结合知识库进行设备画像匹配与测试推荐。"""

    MODULE_KEYWORDS = {
        "ddr": ["ddr", "内存", "ram", "memory"],
        "emmc": ["emmc", "存储", "flash", "disk", "硬盘"],
        "wifi": ["wifi", "wi-fi", "无线"],
        "bluetooth": ["蓝牙", "bt", "bluetooth"],
        "ethernet": ["以太网", "eth", "有线", "ethernet"],
        "cpu": ["cpu", "处理器", "processor"]
    }

    TYPE_KEYWORDS = {
        "functional": ["功能", "基础", "常规", "开关", "状态"],
        "performance": ["性能", "速度", "吞吐量", "信号", "强度", "rssi", "读写", "速度"],
        "stability": ["稳定性", "稳定"],
        "stress": ["压力", "压测", "stress"],
        "aging": ["老化", "aging"],
        "all": ["所有", "全部", "所有功能", "完整"]
    }

    def __init__(self, db: AsyncSession, llm_client: Optional[LLMClient] = None):
        self.db = db
        self.llm_client = llm_client
        self.llm_invoked = False

    async def resolve_device(self, text: str, pc_identifier: str = "") -> Optional[Device]:
        """仅做设备候选匹配（契约 v1.1 §10：授权前唯一允许的查询）。

        不读取知识库、不调用 LLM；在全量登记设备中按文本匹配（序列号/型号/品牌/
        主板），使他人设备在授权阶段得到 403，而不是因候选不可见被 400 掩盖。
        """
        return await self._match_device(text.lower(), pc_identifier)

    async def plan_for_device(self, text: str, device: Device) -> Dict[str, Any]:
        """生成针对已确定设备的测试计划（契约 v1.1 §10）。

        仅允许在设备授权（403）与可用性（409）校验通过后调用：
        本方法会读取该设备相关知识条目并可能调用 LLM。
        """
        text_lower = text.lower()

        # 1. 规则匹配模块和类型
        modules = self._match_modules(text_lower)
        test_type = self._match_type(text_lower)

        # 2. 从知识库获取与设备相关的推荐
        knowledge_items = await get_device_knowledge(
            self.db, device,
            entry_types=["device_profile", "baseline", "rule", "test_case", "failure_pattern"],
            limit=10
        )

        # 3. 如果规则无法匹配模块或类型，调用 LLM 辅助（注入知识库上下文）
        use_llm = not modules or test_type == "all" or not self._is_clear_intent(text_lower)
        if use_llm and self.llm_client:
            try:
                self.llm_invoked = True
                llm_plan = await self._llm_plan(text, device, knowledge_items)
                if llm_plan:
                    modules = llm_plan.get("selected_modules") or modules
                    test_type = llm_plan.get("test_type") or test_type
            except Exception as exc:
                logger.warning("LLM 任务规划失败: %s", exc)

        # 4. 查询测试项
        item_ids = await self._select_items(modules, test_type)

        # 5. 构造推荐说明
        notes = self._build_knowledge_notes(knowledge_items, modules)

        return {
            "device_serial": device.serial_number,
            "device_id": device.id,
            "intent": self._summarize_intent(modules, test_type),
            "selected_modules": modules,
            "test_type": test_type,
            "item_ids": item_ids,
            "knowledge_matches": knowledge_items[:5],
            "notes": notes,
            "llm_used": self.llm_invoked
        }

    async def _match_device(self, text: str, pc_identifier: str = "") -> Optional[Device]:
        """从文本中在全量登记设备中匹配目标设备（授权判断交给创建服务）。"""
        result = await self.db.execute(select(Device))
        all_devices = result.scalars().all()
        return self._find_best_match(text, all_devices)

    def _find_best_match(self, text: str, devices: List[Device]) -> Optional[Device]:
        """在设备列表中按优先级找最佳匹配。"""
        if not devices:
            return None

        # 优先精确匹配 model / serial / board
        for device in devices:
            candidate = device.model or device.serial_number or device.board or ""
            if candidate and candidate.lower() in text:
                return device

        # 模糊匹配：检查文本中是否包含品牌/型号/主板/序列号关键词
        for device in devices:
            model = (device.model or "").lower()
            brand = (device.brand or "").lower()
            board = (device.board or "").lower()
            serial = (device.serial_number or "").lower()

            for keyword in [model, brand, board, serial]:
                if len(keyword) >= 3 and keyword in text:
                    return device

        # 如果只有一个设备，默认选中
        if len(devices) == 1:
            return devices[0]

        return None

    def _match_modules(self, text: str) -> List[str]:
        """匹配测试模块。"""
        matched = []
        for module_name, keywords in self.MODULE_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    matched.append(module_name)
                    break
        return matched

    def _match_type(self, text: str) -> str:
        """匹配测试类型。"""
        for type_name, keywords in self.TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    return type_name
        return "functional"

    def _is_clear_intent(self, text: str) -> bool:
        """判断意图是否足够清晰。"""
        has_module = any(
            keyword.lower() in text
            for keywords in self.MODULE_KEYWORDS.values()
            for keyword in keywords
        )
        has_type = any(
            keyword.lower() in text
            for keywords in self.TYPE_KEYWORDS.values()
            for keyword in keywords
        )
        return has_module or has_type

    @staticmethod
    def _build_knowledge_notes(knowledge_items: List[Dict[str, Any]], modules: List[str]) -> str:
        """根据知识库匹配结果生成推荐说明。"""
        if not knowledge_items:
            return ""
        notes = []
        for item in knowledge_items[:3]:
            title = item.get("title", "")
            etype = item.get("entry_type", "")
            if etype == "rule":
                notes.append(f"参考判定规则《{title}》")
            elif etype == "baseline":
                notes.append(f"参考基线指标《{title}》")
            elif etype == "device_profile":
                notes.append(f"参考设备画像《{title}》")
            elif etype == "failure_pattern":
                notes.append(f"注意失败模式《{title}》")
            else:
                notes.append(f"参考《{title}》")
        return "；".join(notes) if notes else ""

    async def _llm_plan(
        self,
        text: str,
        device: Device,
        knowledge_items: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """调用 LLM 解析任务意图，并注入知识库上下文。"""
        if not self.llm_client:
            return None

        # 查询可用模块
        result = await self.db.execute(select(TestModule).where(TestModule.enabled == True))
        modules = result.scalars().all()
        module_names = [m.name for m in modules]

        # 构造知识库上下文摘要
        knowledge_summary = ""
        if knowledge_items:
            knowledge_summary = "\n".join(
                f"- [{item.get('entry_type', '')}] {item.get('title', '')}"
                for item in knowledge_items[:5]
            )

        system_prompt = (
            "你是一位测试任务规划助手。请根据用户自然语言指令、目标设备信息和知识库推荐，"
            "解析出要测试的模块和测试类型。必须返回结构化 JSON。"
        )

        user_prompt = f"""用户指令: {text}

目标设备信息:
- 序列号: {device.serial_number}
- 型号: {device.model}
- 品牌: {device.brand}
- Android 版本: {device.android_version}
- 主板: {device.board}
- CPU 架构: {device.cpu_abi}
- 能力特征: {', '.join(device.features or [])}

可用测试模块: {', '.join(module_names)}

知识库推荐:
{knowledge_summary or '无'}

请输出测试计划 JSON，selected_modules 必须是可用模块名称的子集。
"""

        return await self.llm_client.chat_completion_structured(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            schema=TASK_PLAN_SCHEMA
        )

    async def _select_items(self, modules: List[str], test_type: str) -> List[int]:
        """根据模块和类型选择测试项 ID。"""
        if not modules:
            return []

        # 查询所有模块
        result = await self.db.execute(select(TestModule))
        all_modules = result.scalars().all()

        item_ids = []
        for module_name in modules:
            keywords = self.MODULE_KEYWORDS.get(module_name.lower(), [module_name.lower()])
            module_id = None
            for module in all_modules:
                if any(
                    keyword.lower() == module.name.lower() or keyword.lower() in module.name.lower()
                    for keyword in keywords
                ):
                    module_id = module.id
                    break

            if not module_id:
                continue

            result = await self.db.execute(
                select(TestItem).where(
                    TestItem.module_id == module_id,
                    TestItem.enabled == True
                )
            )
            items = result.scalars().all()

            # 根据类型过滤 tag（SQLite JSON contains 兼容性处理）
            if test_type != "all":
                items = [item for item in items if item.tags and test_type in item.tags]

            item_ids.extend([item.id for item in items])

        return item_ids

    def _summarize_intent(self, modules: List[str], test_type: str) -> str:
        """生成意图摘要。"""
        module_str = ",".join(modules) if modules else "全部模块"
        return f"{test_type}_{module_str}"
