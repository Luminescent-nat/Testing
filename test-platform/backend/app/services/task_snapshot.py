"""任务测试项配置快照（R20，scheduler-and-data §1）。

创建任务/daily 模板时对选中测试项的执行与判定配置做快照落库：
- 实例使用创建时快照，之后测试项被修改不影响已建任务的历史追溯；
- 历史无快照任务显示 legacy，不得用当前测试项反填冒充原配置。
"""
from typing import Any, Dict, Iterable


def build_item_snapshot(items: Iterable[Any]) -> Dict[str, Any]:
    """从测试项 ORM 对象生成执行配置快照（键为 item_id 的十进制字符串）。"""
    return {
        str(item.id): {
            "name": item.name,
            "exec_type": item.exec_type,
            "exec_command": item.exec_command,
            "parameters": item.parameters or {},
            "compatibility": item.compatibility or {},
            "judgement_type": item.judgement_type,
            "conditional_rules": item.conditional_rules,
            "rubric_criteria": item.rubric_criteria,
            "result_parse": item.result_parse or {},
            "timeout": item.timeout,
            "retry_count": item.retry_count,
            "on_failure": item.on_failure,
        }
        for item in items
    }
