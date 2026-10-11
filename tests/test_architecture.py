"""Architecture guard-rails (see SPEC.md): layering rules enforced via AST."""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CORE_FORBIDDEN = {"streamlit", "app_state", "ui", "db", "pages"}


def _py_files(folder: str) -> list[Path]:
    return sorted(p for p in (ROOT / folder).rglob("*.py") if "__pycache__" not in p.parts)


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


@pytest.mark.parametrize("path", _py_files("core"), ids=lambda p: p.name)
def test_core_has_no_framework_or_layer_imports(path):
    bad = _imported_roots(_parse(path)) & CORE_FORBIDDEN
    assert not bad, f"{path.name} imports forbidden modules: {sorted(bad)}"


@pytest.mark.parametrize("path", _py_files("pages"), ids=lambda p: p.name)
def test_pages_contain_no_sql_execution(path):
    offenders = []
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if name in {"text", "execute", "get_engine"}:
                offenders.append(f"{name}() at line {node.lineno}")
    assert not offenders, f"{path.name} runs SQL directly: {offenders}"


@pytest.mark.parametrize("path", _py_files("ui"), ids=lambda p: p.name)
def test_ui_does_not_import_db(path):
    assert "db" not in _imported_roots(_parse(path)), f"{path.name} imports db"


def _public_core_functions():
    for path in _py_files("core"):
        for node in _parse(path).body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                yield pytest.param(node, id=f"{path.stem}.{node.name}")


@pytest.mark.parametrize("fn", _public_core_functions())
def test_core_public_functions_are_typed_and_documented(fn):
    a = fn.args
    params = a.posonlyargs + a.args + a.kwonlyargs + [x for x in (a.vararg, a.kwarg) if x]
    missing = [p.arg for p in params if p.annotation is None and p.arg not in ("self", "cls")]
    assert not missing, f"{fn.name}: unannotated params {missing}"
    assert fn.returns is not None, f"{fn.name}: missing return annotation"
    assert ast.get_docstring(fn), f"{fn.name}: missing docstring"
