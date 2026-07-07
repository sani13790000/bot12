"""
Test Phase 17 -- Deployment configuration validation.

Checks Dockerfile structure, environment variables, health checks,
and non-root user setup for production readiness.
"""

from __future__ import annotations

import os
import re

import pytest

DOCKERFILE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "Dockerfile")


@pytest.fixture(scope="module")
def dockerfile_content() -> str:
    if not os.path.exists(DOCKERFILE_PATH):
        pytest.skip("Dockerfile not found")
    with open(DOCKERFILE_PATH, encoding="utf-8", errors="replace") as fh:
        return fh.read()


class TestDockerfileStructure:
    """Validate Dockerfile best practices."""

    def test_multi_stage_build(self, dockerfile_content: str) -> None:
        assert dockerfile_content.count("FROM") >= 2

    def test_non_root_user(self, dockerfile_content: str) -> None:
        assert re.search(r"^USER\s+(?!root)", dockerfile_content, re.M)

    def test_healthcheck_present(self, dockerfile_content: str) -> None:
        assert "HEALTHCHECK" in dockerfile_content

    def test_health_endpoint(self, dockerfile_content: str) -> None:
        assert "/health" in dockerfile_content

    def test_no_pip_cache(self, dockerfile_content: str) -> None:
        assert "PIP_NO_CACHE_DIR" in dockerfile_content or "--no-cache-dir" in dockerfile_content

    def test_env_variables_set(self, dockerfile_content: str) -> None:
        assert "ENV" in dockerfile_content

    def test_workdir_set(self, dockerfile_content: str) -> None:
        assert "WORKDIR" in dockerfile_content

    def test_copy_instruction(self, dockerfile_content: str) -> None:
        assert "COPY" in dockerfile_content

    def test_cmd_or_entrypoint(self, dockerfile_content: str) -> None:
        assert "CMD" in dockerfile_content or "ENTRYPOINT" in dockerfile_content
