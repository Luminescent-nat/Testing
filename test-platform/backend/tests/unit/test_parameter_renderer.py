"""参数模板渲染单元测试。"""
import pytest

from app.models import Device
from app.services.parameter_renderer import ParameterRenderer


@pytest.fixture
def sample_device():
    device = Device(
        serial_number="rk3568-test",
        model="rk3568",
        cpu_abi="arm64-v8a",
        ddr_info={"total_mb": 2048, "type": "LPDDR4"},
        emmc_info={"total_gb": 32},
        features=["wifi", "bluetooth"],
    )
    return device


def test_render_simple_attribute(sample_device):
    assert ParameterRenderer.render(sample_device, "{device.model}") == "rk3568"


def test_render_nested_dict(sample_device):
    assert ParameterRenderer.render(sample_device, "{device.ddr_info.total_mb}") == 2048


def test_render_arithmetic_expression(sample_device):
    assert ParameterRenderer.render(sample_device, "{device.ddr_info.total_mb // 4}") == 512


def test_render_mixed_string(sample_device):
    result = ParameterRenderer.render(sample_device, "{device.model}-{device.cpu_abi}")
    assert result == "rk3568-arm64-v8a"


def test_render_with_size_suffix(sample_device):
    result = ParameterRenderer.render(sample_device, "{device.ddr_info.total_mb // 4}M")
    assert result == "512M"


def test_render_missing_attribute_returns_placeholder(sample_device):
    """缺失属性应保留原占位符，便于执行引擎报 error。"""
    result = ParameterRenderer.render(sample_device, "{device.missing}")
    assert result == "{device.missing}"


def test_render_non_string_value_unchanged(sample_device):
    """非字符串值直接返回。"""
    assert ParameterRenderer.render(sample_device, 123) == 123
    assert ParameterRenderer.render(sample_device, ["a"]) == ["a"]


def test_render_parameters_dict(sample_device):
    params = {
        "size": "{device.ddr_info.total_mb // 4}M",
        "model": "{device.model}",
        "fixed": 100,
    }
    result = ParameterRenderer.render_parameters(sample_device, params)
    assert result["size"] == "512M"
    assert result["model"] == "rk3568"
    assert result["fixed"] == 100
