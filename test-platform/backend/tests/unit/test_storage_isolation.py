"""测试运行目录隔离的回归用例。"""
from pathlib import Path

from app.config import get_settings


def test_storage_paths_are_isolated_per_test(tmp_path):
    """所有可写存储路径必须位于当前用例的临时目录，而非仓库 storage。"""
    settings = get_settings()
    for setting_name in ("STORAGE_PATH", "TOOLS_PATH", "REPORTS_PATH", "LOGS_PATH"):
        actual = Path(getattr(settings, setting_name)).resolve()
        assert actual.is_relative_to(tmp_path.resolve()), (
            f"{setting_name} 未隔离: {actual}"
        )
