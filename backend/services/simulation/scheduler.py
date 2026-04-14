"""In-process async auto-loop scheduler for simulation re-runs.

Runs inside the FastAPI process as a background asyncio task.
Reads all is_auto_loop=True simulations, evaluates their cron expressions
using croniter, and calls SimulationService.run_auto_loop() when due.

Lifecycle:
  - start(session_factory) — creates background task, sets is_running=True
  - stop()                 — cancels background task, sets is_running=False
  - status()               — returns SchedulerStatusResponse snapshot

Usage in FastAPI lifespan:
  async with lifespan(app):
      scheduler.start(async_session_factory)
      yield
      await scheduler.stop()
"""

from __future__ import annotations

import asyncio
import datetime
from typing import Any, Optional

import structlog
from croniter import croniter, CroniterBadCronError  # type: ignore[import-untyped]

log = structlog.get_logger()

_POLL_INTERVAL_SECONDS = 60


class SimulationScheduler:
    """Singleton in-process scheduler for auto-loop simulations.

    Thread-safe for a single asyncio event loop.
    """

    def __init__(self) -> None:
        self._is_running: bool = False
        self._task: Optional[asyncio.Task[None]] = None
        self._last_run_at: Optional[datetime.datetime] = None
        self._next_run_at: Optional[datetime.datetime] = None
        self._active_simulations: int = 0
        self._session_factory: Optional[Any] = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self, session_factory: Any) -> None:
        """Start the background scheduler task.

        Args:
            session_factory: async_sessionmaker that produces AsyncSession.
        """
        if self._is_running:
            log.warning("scheduler_already_running")
            return

        self._session_factory = session_factory
        self._is_running = True
        self._task = asyncio.create_task(self._run_loop())
        log.info("scheduler_started", poll_interval_seconds=_POLL_INTERVAL_SECONDS)

    async def stop(self) -> None:
        """Stop the scheduler and cancel the background task."""
        self._is_running = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._task = None
        log.info("scheduler_stopped")

    def status(self) -> dict[str, Any]:
        """Return current scheduler status as a plain dict."""
        return {
            "is_running": self._is_running,
            "active_simulations": self._active_simulations,
            "last_run_at": self._last_run_at,
            "next_run_at": self._next_run_at,
        }

    async def _run_loop(self) -> None:
        """Main poll loop — runs until stop() is called."""
        log.info("scheduler_loop_start")
        while self._is_running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                log.info("scheduler_loop_cancelled")
                break
            except Exception as exc:
                log.error("scheduler_loop_error", error=str(exc))

            try:
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                log.info("scheduler_sleep_cancelled")
                break

        log.info("scheduler_loop_exit")

    async def _tick(self) -> None:
        """Single scheduler tick — find due simulations and re-run them."""
        from backend.clients.jip_data_service import JIPDataService
        from backend.services.simulation.service import SimulationService

        if self._session_factory is None:
            log.warning("scheduler_no_session_factory")
            return

        now = datetime.datetime.now(tz=datetime.timezone.utc)

        async with self._session_factory() as session:
            from backend.services.simulation.repo import SimulationRepo

            repo = SimulationRepo(session)
            all_sims = await repo.list_simulations(user_id=None, limit=500)
            auto_sims = [s for s in all_sims if s.is_auto_loop and not s.is_deleted]
            self._active_simulations = len(auto_sims)

            due_sims = [s for s in auto_sims if _is_due(s, now)]

            if not due_sims:
                self._next_run_at = _compute_next_run(auto_sims, now)
                log.debug(
                    "scheduler_tick_no_due_sims",
                    active=self._active_simulations,
                    next_run=str(self._next_run_at) if self._next_run_at else None,
                )
                return

            log.info("scheduler_tick_running", due_count=len(due_sims))

            jip = JIPDataService(session)
            service = SimulationService(session)
            results = await service.run_auto_loop(jip=jip)

            self._last_run_at = now
            self._next_run_at = _compute_next_run(auto_sims, now)

            succeeded = sum(1 for r in results if r.status == "success")
            failed = sum(1 for r in results if r.status == "error")
            log.info(
                "scheduler_tick_complete",
                ran=len(results),
                succeeded=succeeded,
                failed=failed,
            )


def _is_due(sim: Any, now: datetime.datetime) -> bool:
    """Determine if a simulation is due for re-run based on its cron expression.

    Returns True if:
    - It has a valid cron expression, AND
    - Either it has never run, OR the previous cron fire time is after last_auto_run.
    """
    cron_expr = sim.auto_loop_cron
    if not cron_expr:
        return False

    try:
        cron = croniter(cron_expr, now)
        # Get the previous scheduled time
        prev_fire = cron.get_prev(datetime.datetime)
        if prev_fire.tzinfo is None:
            prev_fire = prev_fire.replace(tzinfo=datetime.timezone.utc)
    except (CroniterBadCronError, ValueError, TypeError) as exc:
        log.warning("scheduler_invalid_cron", cron=cron_expr, error=str(exc))
        return False

    last_run = sim.last_auto_run
    if last_run is None:
        # Never run — if a cron fire time has passed, it's due
        return True

    if last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=datetime.timezone.utc)

    return bool(prev_fire > last_run)


def _compute_next_run(
    sims: list[Any],
    now: datetime.datetime,
) -> Optional[datetime.datetime]:
    """Compute the nearest next cron fire time across all auto-loop sims."""
    next_times: list[datetime.datetime] = []

    for sim in sims:
        cron_expr = sim.auto_loop_cron
        if not cron_expr:
            continue
        try:
            cron = croniter(cron_expr, now)
            nxt = cron.get_next(datetime.datetime)
            if nxt.tzinfo is None:
                nxt = nxt.replace(tzinfo=datetime.timezone.utc)
            next_times.append(nxt)
        except (CroniterBadCronError, ValueError, TypeError):
            pass

    return min(next_times) if next_times else None


# Module-level singleton
scheduler = SimulationScheduler()
