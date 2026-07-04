import ast
import inspect
from pathlib import Path

import pytest

# Find all python files in the project
PROJECT_ROOT = Path(__file__).parent.parent.parent
PYTHON_FILES = list((PROJECT_ROOT / "backend").rglob("*.py")) + list((PROJECT_ROOT / "frontend").rglob("*.py"))

@pytest.mark.parametrize("filepath", PYTHON_FILES, ids=lambda p: p.name)
def test_no_wildcard_imports(filepath: Path) -> None:
    """Rule 5.3: Eradicate Wildcard Imports (from module import *)"""
    tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name != "*", (
                    f"Architecture Violation in {filepath.name}: Wildcard import 'from {node.module} import *' "
                    f"found on line {node.lineno}. Use explicit absolute imports."
                )

@pytest.mark.parametrize("filepath", PYTHON_FILES, ids=lambda p: p.name)
def test_no_mutable_default_arguments(filepath: Path) -> None:
    """Rule 3.3: Ban All Mutable Default Arguments (e.g., items=[])"""
    tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults + node.args.kw_defaults:
                if default is None:
                    continue
                # Fail if the default argument is a List, Dict, or Set
                assert not isinstance(default, (ast.List, ast.Dict, ast.Set)), (
                    f"Architecture Violation in {filepath.name}: Function '{node.name}' on line {node.lineno} "
                    f"uses a mutable default argument. Use 'None' and initialize inside the block."
                )

@pytest.mark.parametrize("filepath", PYTHON_FILES, ids=lambda p: p.name)
def test_explicit_return_type_hints(filepath: Path) -> None:
    """Rule 3.5: Require Explicit Returns (Every function must declare -> type)"""
    tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Skip dunder methods like __init__ for this specific strict check
            if node.name.startswith("__") and node.name.endswith("__"):
                continue
            assert node.returns is not None, (
                f"Architecture Violation in {filepath.name}: Function '{node.name}' on line {node.lineno} "
                f"is missing a return type hint. If it returns nothing, use '-> None'."
            )