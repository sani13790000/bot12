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
    """Read Dockerfile once per module."""
    if not os.path.exists(DOCKERFILE_PATH):
        pytest.skip("Dockerfile not found")
    with open(DOCKERFILE_PATH, encoding="utf-8", errors="replace") as fh:
        return fh.read()


class TestDockerfileStructure:
    """Validate Dockerfile best practices."""

    def test_multi_stage_build(self, dockerfile_content: str) -> None:
        assert dockerfile_content.count("FROM") >= 2, "Expected multi-stage build"

    def test_non_root_user(self, dockerfile_content: str) -> None:
        assert re.search(r"^USER\s+(?!root)", dockerfile_content, re.M), \
            "Container should not run as root"

    def test_healthcheck_present(self, dockerfile_content: str) -> None:
        assert "HEALTHCHECK" in dockerfile_content, "HEALTHCHECK instruction missing"

    def test_health_endpoint(self, dockerfile_content: str) -> None:
        assert "/health" in dockerfile_content, "/health endpoint not referenced in HEALTHCHECK"

    def test_no_pip_cache(self, dockerfile_content: str) -> None:
        assert "PIP_NO_CACHE_DIR" in dockerfile_content or "--no-cache-dir" in dockerfile_content

    def test_no_gcc_in_runtime(self, dockerfile_content: str) -> None:
        lines = dockerfile_content.splitlines()
        final_stage_start = max(
            i for i, ln in enumerate(lines) if ln.strip().startswith("FROM")
        )
        runtime_section = "\n".join(lines[final_stage_start:])
        assert "gcc" not in runtime_section.lower(), "gcc should not be in final runtime stage"

    def test_env_variables_set(self, dockerfile_content: str) -> None:
        assert "ENV" in dockerfile_content, "No ENV instructions found"

    def test_workdir_set(self, dockerfile_content: str) -> None:
        assert "WORKDIR" in dockerfile_content, "WORKDIR not set"

    def test_copy_instruction(self, dockerfile_content: str) -> None:
        assert "COPY" in dockerfile_content, "No COPY instruction found"

    def test_cmd_or_entrypoint(self, dockerfile_content: str) -> None:
        has_cmd = "CMD" in dockerfile_content
        has_entrypoint = "ENTRYPOINT" in dockerfile_content
        assert has_cmd or has_entrypoint, "Neither CMD nor ENTRYPOINT found"
