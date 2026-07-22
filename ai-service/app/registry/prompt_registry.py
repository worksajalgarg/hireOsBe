"""
Minimal versioned registry satisfying FR-805: "unapproved versions cannot be
promoted to production". This Sprint-1 pass is in-memory only — a real
Postgres-backed table with an approval workflow lands alongside the agents
that need it (Sprint 2+).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class RegisteredVersion:
    name: str
    version: str
    approved: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PromptRegistry:
    def __init__(self) -> None:
        self._versions: dict[tuple[str, str], RegisteredVersion] = {}

    def register(self, name: str, version: str) -> RegisteredVersion:
        entry = RegisteredVersion(name=name, version=version)
        self._versions[(name, version)] = entry
        return entry

    def approve(self, name: str, version: str) -> RegisteredVersion:
        entry = self._versions[(name, version)]
        entry.approved = True
        return entry

    def is_approved(self, name: str, version: str) -> bool:
        entry = self._versions.get((name, version))
        return entry is not None and entry.approved


prompt_registry = PromptRegistry()
