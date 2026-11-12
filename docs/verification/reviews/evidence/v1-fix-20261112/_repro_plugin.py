"""评审方 shim 插件：把 backend/tests/conftest.py 的 fixtures 注册到本插件模块。

仅用于在不动业务 tests/ 目录的前提下，对
docs/verification/reviews/evidence/v1-readiness-20261112/targeted-defect-repro.py
运行定向反例（pytest 对 evidence 目录文件不会自动收集 backend conftest）。
不修改任何业务代码；conftest 只被 import 一次，由 pytest 以插件形式装配。
"""
import importlib.util
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_CONFTEST = os.path.abspath(os.path.join(
    _HERE, "..", "..", "..", "..", "..", "test-platform", "backend", "tests", "conftest.py"
))

_spec = importlib.util.spec_from_file_location("v1_repro_conftest", _CONFTEST)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

for _name, _obj in list(vars(_mod).items()):
    if _name.startswith("__"):
        continue
    globals()[_name] = _obj
