"""
A minimal in-process stand-in for SQS -> Lambda semantics: at-least-once
delivery, retry with backoff, idempotency keys, and a dead-letter queue.

Swapping this for real SQS + Lambda in production means:
  - enqueue()      -> sqs.send_message() (idempotency via message dedup ID
                       or an idempotency table, same pattern as below)
  - run_worker()   -> the Lambda handler invoked per SQS message
  - retry/backoff  -> SQS visibility timeout + redrive policy
  - self.dlq       -> an actual SQS DLQ, with a redrive/replay tool
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable


@dataclass
class JobResult:
    ok: bool
    error: str | None = None


@dataclass
class Job:
    doc_id: str
    idempotency_key: str
    attempts: int = 0


class QueueSimulator:
    def __init__(
        self,
        handler: Callable[[str], Awaitable[JobResult]],
        max_attempts: int = 3,
        base_backoff_seconds: float = 0.5,
        on_dead_letter: Callable[[str, str], Awaitable[None]] | None = None,
    ):
        self._handler = handler
        self._max_attempts = max_attempts
        self._base_backoff = base_backoff_seconds
        self._on_dead_letter = on_dead_letter
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._seen_idempotency_keys: set[str] = set()
        self.dlq: list[dict] = []

    async def enqueue(self, doc_id: str, idempotency_key: str):
        # Idempotent enqueue: a duplicate message for the same content is
        # dropped rather than double-processed.
        if idempotency_key in self._seen_idempotency_keys:
            return
        self._seen_idempotency_keys.add(idempotency_key)
        await self._queue.put(Job(doc_id=doc_id, idempotency_key=idempotency_key))

    async def run_worker(self):
        while True:
            job = await self._queue.get()
            job.attempts += 1
            try:
                result = await self._handler(job.doc_id)
                if not result.ok:
                    raise RuntimeError(result.error or "handler_reported_failure")
            except Exception as e:
                if job.attempts < self._max_attempts:
                    backoff = self._base_backoff * (2 ** (job.attempts - 1))
                    await asyncio.sleep(backoff)
                    await self._queue.put(job)
                else:
                    self.dlq.append(
                        {
                            "doc_id": job.doc_id,
                            "attempts": job.attempts,
                            "error": str(e),
                            "failed_at": time.time(),
                        }
                    )
                    if self._on_dead_letter:
                        await self._on_dead_letter(job.doc_id, str(e))
            finally:
                self._queue.task_done()
