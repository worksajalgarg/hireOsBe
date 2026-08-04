"""Module-level circuit breaker for ModelGateway provider health tracking.

When a provider returns a rate-limit error (HTTP 429) or accumulates
consecutive failures, it is placed into a temporary cooldown window.
During cooldown, gateway.py skips the provider instantly without making
any network call — no wasted quota, no candidate-facing latency.

Design:
- Singleton (module-level `_breaker`) accessed via the module functions below.
- Thread-safe via asyncio (all gateway calls are async; no lock needed for
  Python-level dict mutations from a single event loop).
- Stateless across worker restarts — breaker state lives only in memory,
  so a process restart always starts fresh. That's intentional: a cooldown
  surviving a restart would silently hide a provider for longer than intended.
"""

import logging
import time

from .providers import Provider

logger = logging.getLogger("model_gateway")

# Default cooldown durations (seconds):
# - Rate limit (429): wait at least 5 min before retrying.
# - Repeated failures: shorter window — transient errors clear sooner.
_RATE_LIMIT_COOLDOWN_S = 300  # 5 minutes
_FAILURE_COOLDOWN_S = 60       # 1 minute
_FAILURE_THRESHOLD = 3         # consecutive failures before tripping


class _ProviderState:
    __slots__ = ("failure_count", "cooldown_until")

    def __init__(self) -> None:
        self.failure_count: int = 0
        self.cooldown_until: float = 0.0


class ProviderCircuitBreaker:
    """Tracks per-provider health and enforces cooldown windows."""

    def __init__(self) -> None:
        self._state: dict[Provider, _ProviderState] = {}

    def _get(self, provider: Provider) -> _ProviderState:
        if provider not in self._state:
            self._state[provider] = _ProviderState()
        return self._state[provider]

    def is_available(self, provider: Provider) -> bool:
        """Returns False if the provider is currently in a cooldown window."""
        state = self._get(provider)
        if state.cooldown_until > time.monotonic():
            return False
        return True

    def record_success(self, provider: Provider) -> None:
        """Clear failure count on a successful response."""
        state = self._get(provider)
        state.failure_count = 0
        state.cooldown_until = 0.0

    def record_rate_limit(
        self, provider: Provider, cooldown_s: float = _RATE_LIMIT_COOLDOWN_S
    ) -> None:
        """Provider hit HTTP 429 — apply a long cooldown."""
        state = self._get(provider)
        state.cooldown_until = time.monotonic() + cooldown_s
        state.failure_count = 0
        logger.warning(
            "circuit_breaker: provider %s rate-limited, cooling down for %.0fs",
            provider.value,
            cooldown_s,
        )

    def record_failure(self, provider: Provider) -> None:
        """Record a generic provider failure. Trips breaker after threshold."""
        state = self._get(provider)
        state.failure_count += 1
        if state.failure_count >= _FAILURE_THRESHOLD:
            state.cooldown_until = time.monotonic() + _FAILURE_COOLDOWN_S
            logger.warning(
                "circuit_breaker: provider %s hit %d consecutive failures, "
                "cooling down for %.0fs",
                provider.value,
                state.failure_count,
                _FAILURE_COOLDOWN_S,
            )

    def cooldown_remaining(self, provider: Provider) -> float:
        """Seconds remaining in cooldown, 0.0 if not cooling down."""
        state = self._get(provider)
        remaining = state.cooldown_until - time.monotonic()
        return max(0.0, remaining)


# Module-level singleton — imported directly by gateway.py.
circuit_breaker = ProviderCircuitBreaker()
