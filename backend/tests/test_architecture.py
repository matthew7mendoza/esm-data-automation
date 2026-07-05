import ast
from importlib.resources import files
from pathlib import Path

import pytest

PROJECT_ROOT: Path = Path(str(files("backend"))).parent
PYTHON_FILES: list[Path] = list((PROJECT_ROOT / "backend").rglob("*.py")) + list(
    (PROJECT_ROOT / "frontend").rglob("*.py")
)


@pytest.mark.parametrize("filepath", PYTHON_FILES, ids=lambda p: p.name)
def test_no_wildcard_imports(filepath: Path) -> None:
    tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    import_nodes = (n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom))
    aliases = ((node, alias) for node in import_nodes for alias in node.names)
    for node, alias in aliases:
        assert alias.name != "*", (
            f"Architecture Violation in {filepath.name}: "
            f"Wildcard import 'from {node.module} import *' "
            f"found on line {node.lineno}. Use explicit absolute imports."
        )


@pytest.mark.parametrize("filepath", PYTHON_FILES, ids=lambda p: p.name)
def test_no_mutable_default_arguments(filepath: Path) -> None:
    tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    functions = (
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    defaults = (
        (func, default)
        for func in functions
        for default in func.args.defaults + func.args.kw_defaults
        if default is not None
    )
    for func, default in defaults:
        assert not isinstance(default, (ast.List, ast.Dict, ast.Set)), (
            f"Architecture Violation in {filepath.name}: "
            f"Function '{func.name}' on line {func.lineno} "
            "uses a mutable default argument. Use 'None' and initialize "
            "inside the block."
        )


@pytest.mark.parametrize("filepath", PYTHON_FILES, ids=lambda p: p.name)
def test_explicit_return_type_hints(filepath: Path) -> None:
    tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    functions = (
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        if not (n.name.startswith("__") and n.name.endswith("__"))
    )
    for func in functions:
        assert func.returns is not None, (
            f"Architecture Violation in {filepath.name}: "
            f"Function '{func.name}' on line {func.lineno} "
            "is missing a return type hint. If it returns nothing, "
            "use '-> None'."
        )
