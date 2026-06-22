# -*- coding: utf-8 -*-
"""Static adoption guard for the repository dispatch boundary.

These tests ensure that GraphQL modules (``queries/``, ``mutations/``,
``types/``) route persistence exclusively through the repository dispatch
boundary in ``rfq_engine.models.repositories``. They fail if any module in
those layers re-introduces a direct ``models.dynamodb`` import or a direct
DynamoDB ``insert_update_*`` / ``delete_*`` function call, which would bypass
the PostgreSQL backend and break dual-backend parity.

The guard is purely static (source-text scanning), so it runs without any
external service and complements the runtime smoke tests in
``test_dual_backend_loaders.py``.
"""
from __future__ import print_function

__author__ = "bibow"

import os
import re
from typing import List

import pytest


# GraphQL layers that must stay backend-agnostic.
_GRAPHQL_LAYER_DIRS = ("queries", "mutations", "types")

# Direct imports of the DynamoDB model package. These are banned in the
# GraphQL layer because they tie the layer to the DynamoDB backend. The
# repository boundary exists specifically to keep these out.
_DIRECT_DYNAMODB_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+.*\bmodels\.dynamodb\b",
    re.MULTILINE,
)

# Direct calls to DynamoDB insert_update_* / delete_* functions. Once
# mutations route through ``get_repo(entity).insert_update(...)`` /
# ``.delete(...)``, these free function calls should never reappear.
_DIRECT_DDB_FN_CALL_RE = re.compile(
    r"\b(?:insert_update_[a-z_]+|delete_[a-z_]+)\s*\(",
)

# Comments and strings we should not flag. We only treat code lines as
# violations, so a docstring that *mentions* ``insert_update_quote`` is fine.
# Simplest heuristic: strip lines that are obviously comments.
_COMMENT_LINE_RE = re.compile(r"^\s*#")


def _graphql_layer_files() -> List[str]:
    """Return absolute paths of every ``*.py`` file in the GraphQL layers."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    files: List[str] = []
    for layer in _GRAPHQL_LAYER_DIRS:
        layer_dir = os.path.join(root, layer)
        if not os.path.isdir(layer_dir):
            continue
        for name in sorted(os.listdir(layer_dir)):
            if name.endswith(".py") and name != "__init__.py":
                files.append(os.path.join(layer_dir, name))
    return files


def _read_source(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def test_no_direct_dynamodb_imports_in_graphql_layer():
    """No ``queries/`` / ``mutations/`` / ``types/`` module may import
    ``models.dynamodb`` directly. All persistence must flow through
    ``rfq_engine.models.repositories``.
    """
    violations: List[str] = []
    for path in _graphql_layer_files():
        source = _read_source(path)
        for match in _DIRECT_DYNAMODB_IMPORT_RE.finditer(source):
            line_no = source.count("\n", 0, match.start()) + 1
            rel = os.path.relpath(path)
            violations.append(f"{rel}:{line_no}: {match.group(0).strip()}")

    assert not violations, (
        "GraphQL layer imports DynamoDB models directly — re-introduces a "
        "backend bypass. Route through rfq_engine.models.repositories "
        "instead. Violations:\n" + "\n".join(violations)
    )


def test_no_direct_dynamodb_function_calls_in_mutations():
    """No ``mutations/`` module may call DynamoDB ``insert_update_*`` /
    ``delete_*`` free functions. Mutations must use
    ``get_repo(entity).insert_update(...)`` / ``.delete(...)``.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mutations_dir = os.path.join(root, "mutations")
    if not os.path.isdir(mutations_dir):
        pytest.skip("mutations directory not found")

    violations: List[str] = []
    for name in sorted(os.listdir(mutations_dir)):
        if not name.endswith(".py") or name == "__init__.py":
            continue
        path = os.path.join(mutations_dir, name)
        source = _read_source(path)
        for lineno, line in enumerate(source.splitlines(), start=1):
            if _COMMENT_LINE_RE.match(line):
                continue
            # Skip the canonical repository-based calls: get_repo(...).insert_update(...)
            # and .delete(...). The banned pattern is a bare free function call
            # like ``insert_update_item(`` without a preceding ``.``.
            if _DIRECT_DDB_FN_CALL_RE.search(line):
                # Allow method calls: ``.insert_update_...(`` / ``.delete_...(``
                # by stripping the dotted form before re-checking.
                stripped = re.sub(r"\.\s*(?:insert_update_[a-z_]+|delete_[a-z_]+)\s*\(", "", line)
                if _DIRECT_DDB_FN_CALL_RE.search(stripped):
                    violations.append(f"{name}:{lineno}: {line.strip()}")

    assert not violations, (
        "Mutations call DynamoDB insert_update_* / delete_* free functions "
        "directly — must use get_repo(entity).insert_update(...) / .delete(...). "
        "Violations:\n" + "\n".join(violations)
    )


@pytest.mark.parametrize("layer", _GRAPHQL_LAYER_DIRS)
def test_graphql_layer_uses_repository_boundary(layer):
    """Sanity check that the layer routes persistence through the boundary.

    Not every module in a GraphQL layer touches persistence (some delegate to
    handlers or only define types), so we do not require every file to import
    ``models.repositories``. Instead we assert that any module that imports
    from ``models.`` imports from ``models.repositories`` (and not from
    ``models.dynamodb`` or ``models.postgresql`` directly), and that the
    layer as a whole references the boundary in at least one module.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    layer_dir = os.path.join(root, layer)
    if not os.path.isdir(layer_dir):
        pytest.skip(f"{layer} directory not found")

    models_import_re = re.compile(r"^\s*from\s+\.\.models\b", re.MULTILINE)
    boundary_re = re.compile(r"\bmodels\.repositories\b")
    direct_backend_re = re.compile(r"\bmodels\.(?:dynamodb|postgresql)\b")

    has_any_boundary_import = False
    bad: List[str] = []
    for name in sorted(os.listdir(layer_dir)):
        if not name.endswith(".py") or name == "__init__.py":
            continue
        path = os.path.join(layer_dir, name)
        source = _read_source(path)
        if not models_import_re.search(source):
            continue  # module does not touch the models package at all
        if boundary_re.search(source):
            has_any_boundary_import = True
        if direct_backend_re.search(source):
            bad.append(name)

    assert not bad, (
        f"{layer}/ modules import models.dynamodb / models.postgresql "
        f"directly instead of models.repositories: {bad}"
    )
    assert has_any_boundary_import, (
        f"{layer}/ layer never imports models.repositories — adoption guard "
        f"cannot confirm the boundary is in use."
    )