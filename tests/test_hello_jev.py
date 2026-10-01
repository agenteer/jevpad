"""hello_jev.py is TypeSafe's SDK example; check it stays valid Python that uses only the public SDK names."""
import ast
from pathlib import Path

import typesafe_sdk


def test_hello_jev_parses_and_uses_public_sdk_names():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "hello_jev.py").read_text())
    imported = [alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names]
    assert imported == ["Choice", "Noul", "Score", "TypeSafeClient"]
    assert all(hasattr(typesafe_sdk, name) for name in imported)
