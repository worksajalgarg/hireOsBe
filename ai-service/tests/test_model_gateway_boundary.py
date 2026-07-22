"""
Enforces the CTO guardrail as an automated check rather than only a comment:
no module outside app/model_gateway may import a provider SDK. Today no
provider SDK dependency exists yet, so this test guards against future
regressions once openai/anthropic/google client libraries are added.
"""

import ast
from pathlib import Path

PROVIDER_MODULE_PREFIXES = ("openai", "anthropic", "google.generativeai", "google.genai")
APP_ROOT = Path(__file__).resolve().parent.parent / "app"
ALLOWED_DIR = APP_ROOT / "model_gateway"


def _imported_modules(file_path: Path) -> set[str]:
    tree = ast.parse(file_path.read_text(), filename=str(file_path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_no_provider_sdk_imports_outside_model_gateway() -> None:
    violations: list[str] = []
    for py_file in APP_ROOT.rglob("*.py"):
        if ALLOWED_DIR in py_file.parents:
            continue
        modules = _imported_modules(py_file)
        for module in modules:
            if module.startswith(PROVIDER_MODULE_PREFIXES):
                violations.append(f"{py_file}: imports '{module}'")

    assert not violations, "Provider SDK imported outside model_gateway/: " + ", ".join(violations)
