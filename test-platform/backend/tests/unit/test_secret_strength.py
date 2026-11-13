"""T-18 SECRET_KEY 强度校验契约测试（先于实现编写的红测）。

覆盖 docs/design/scheduler-and-data.md 第 6 节：
- 至少 32 字符；拒绝空、Compose 示例占位值、单字符重复；
- 错误信息只指出配置项 SECRET_KEY，绝不打印密钥值；
- docker-compose.yml 默认占位必须改为强制显式提供（${SECRET_KEY:?...}）；
- main.py 启动校验必须走 config 的强度校验（弱密钥拒绝启动）。
"""
from pathlib import Path

import pytest

from app.config import (  # noqa: F401  实现前：ImportError 即红测
    SECRET_KEY_MIN_LENGTH,
    WeakSecretKeyError,
    assert_secret_key_strength,
    secret_key_problem,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

# 与 conftest 一致的 32+ 字符非占位测试密钥（仅测试使用，非生产密钥）
LEGAL_KEY = "x9F2k7Qp4Lm8Nv3Bw6Yz1Rt5Hj0Cd4Es7Ag2Ui5Oq8PnT3Wv"


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "",
        "   ",
        "secret",
        "SECRET",
        "change-me",
        "changeme",
        "your-secret-key",
        "please-change-me-in-production",
        "please-change-me-in-production-but-much-longer-than-32-chars",
        "a" * 40,  # 单字符重复
        "a" * 31,  # 长度不足
        "short",
    ],
)
def test_weak_secret_keys_are_rejected(bad):
    problem = secret_key_problem(bad)
    assert problem, f"应拒绝弱密钥: {bad!r}"
    assert "SECRET_KEY" in problem  # 只指出配置项
    with pytest.raises(WeakSecretKeyError):
        assert_secret_key_strength(bad)


@pytest.mark.parametrize(
    "bad",
    ["please-change-me-in-production-but-much-longer-than-32-chars", "a" * 40],
)
def test_error_message_never_echoes_the_key_value(bad):
    with pytest.raises(WeakSecretKeyError) as excinfo:
        assert_secret_key_strength(bad)
    message = str(excinfo.value)
    assert bad not in message
    assert "SECRET_KEY" in message


def test_legal_and_boundary_keys_accepted():
    assert secret_key_problem(LEGAL_KEY) is None
    assert assert_secret_key_strength(LEGAL_KEY) is None


def test_minimum_length_boundary():
    assert secret_key_problem("k" * (SECRET_KEY_MIN_LENGTH - 1)) is not None
    assert secret_key_problem("k9" * (SECRET_KEY_MIN_LENGTH // 2)) is None


def test_compose_requires_explicit_secret_key():
    """docker-compose.yml 不得再提供弱默认占位，必须 ${SECRET_KEY:?...} 强制显式。"""
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "${SECRET_KEY:?" in compose
    assert "please-change-me-in-production" not in compose
    assert "${SECRET_KEY:-" not in compose


def test_env_example_documents_strength_rules():
    env_example = (REPO_ROOT / "backend" / ".env.example").read_text(encoding="utf-8")
    assert "32" in env_example  # 至少 32 字符的规则必须写进示例
    assert "please-change-me-in-production" not in env_example


def test_main_startup_validation_rejects_weak_secret(monkeypatch):
    """main.py 的启动校验必须复用 config 的 SECRET_KEY 强度校验。"""
    import app.main as main_module

    monkeypatch.setattr(main_module.settings, "SECRET_KEY", "change-me")
    with pytest.raises(WeakSecretKeyError):
        main_module.validate_startup_config()


def test_main_startup_validation_accepts_legal_secret(monkeypatch, tmp_path):
    """合法密钥 + 合法（A5 非空）工具清单 → 启动校验通过。

    契约 v1.1 §6.1 A5 连带夹具适配（非放宽）：A5 废除了空 TEST_TOOLS_PATH 的静默
    启动，因此此处必须提供最小合法 manifest（module + tools 四段声明），sha256
    按实际文件计算。
    """
    import hashlib

    import app.main as main_module

    tools_root = tmp_path / "test-tools"
    runner = tools_root / "mod" / "host" / "run.py"
    runner.parent.mkdir(parents=True)
    runner.write_text("print('ok')\n", encoding="utf-8")
    shared = tools_root / "common" / "logger.py"
    shared.parent.mkdir(parents=True)
    shared.write_text("def setup_logger(): pass\n", encoding="utf-8")
    manifest = tools_root / "mod" / "manifest.yaml"
    manifest.write_text(
        "module:\n  name: mod\nitems: []\n"
        "tools:\n"
        "  host:\n"
        "    - path: mod/host/run.py\n"
        f'      sha256: "{hashlib.sha256(runner.read_bytes()).hexdigest()}"\n'
        "  shared:\n"
        "    - path: common/logger.py\n"
        f'      sha256: "{hashlib.sha256(shared.read_bytes()).hexdigest()}"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(main_module.settings, "SECRET_KEY", LEGAL_KEY)
    monkeypatch.setattr(main_module.settings, "TEST_TOOLS_PATH", str(tools_root))
    assert main_module.validate_startup_config() is None
