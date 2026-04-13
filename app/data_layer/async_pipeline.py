"""
Async Producer-Consumer Pipeline
==================================
Generic pipeline that eliminates dead time between API calls.

Producer: fetches from external API at rate-limited speed, queues raw responses.
Consumer: parses and stores data concurrently — never blocks the producer.

While the consumer inserts row N, the producer is already fetching row N+1.
The rate limiter stays at 4.9/s but there's zero dead time between calls.

Usage:
    pipeline = EtherscanPipeline(
        provider="etherscan",
        caller="wallet_expansion",
        max_calls=250_000,
    )

    async def fetch_fn(client, item):
        resp = await client.get(...)
        return resp.json()

    async def process_fn(data, item):
        # parse + insert
        pass

    result = await pipeline.run(
        items=wallet_list,
        fetch_fn=fetch_fn,
        process_fn=process_fn,
    )
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class PipelineStats:
    """Statistics for a pipeline run."""
    items_queued: int = 0
    items_fetched: int = 0
    items_processed: int = 0
    items_failed: int = 0
    fetch_errors: int = 0
    process_errors: int = 0
    rate_limit_hits: int = 0
    total_latency_ms: float = 0
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0

    @property
    def elapsed_s(self) -> float:
        end = self.finished_at or time.time()
        return end - self.started_at

    @property
    def effective_rate(self) -> float:
        elapsed = self.elapsed_s
        return self.items_fetched / elapsed if elapsed > 0 else 0

    def to_dict(self) -> dict:
        return {
            "items_fetched": self.items_fetched,
            "items_processed": self.items_processed,
            "items_failed": self.items_failed,
            "fetch_errors": self.fetch_errors,
            "process_errors": self.process_errors,
            "rate_limit_hits": self.rate_limit_hits,
            "elapsed_s": round(self.elapsed_s, 1),
            "effective_rate_per_s": round(self.effective_rate, 2),
            "avg_latency_ms": (
                round(self.total_latency_ms / self.items_fetched)
                if self.items_fetched > 0 else 0
            ),
        }


class EtherscanPipeline:
    """
    Async producer-consumer pipeline for Etherscan API calls.
    Eliminates dead time between sequential fetch → parse → insert.

    The producer calls the API at the shared rate limiter's pace.
    The consumer processes responses concurrently.
    A bounded queue ensures the producer doesn't get too far ahead.
    """

    def __init__(
        self,
        provider: str = "etherscan",
        caller: str = "pipeline",
        max_calls: int = 250_000,
        queue_size: int = 100,
        consumer_count: int = 2,
    ):
        self.provider = provider
        self.caller = caller
        self.max_calls = max_calls
        self.queue_size = queue_size
        self.consumer_count = consumer_count
        self.stats = PipelineStats()
        self._queue: asyncio.Queue = None
        self._stop = False

    async def run(
        self,
        items: list[Any],
        fetch_fn: Callable[[httpx.AsyncClient, Any], Coroutine],
        process_fn: Callable[[Any, Any], Coroutine],
        client: Optional[httpx.AsyncClient] = None,
    ) -> PipelineStats:
        """
        Run the pipeline.

        Args:
            items: List of work items (wallets, contracts, etc.)
            fetch_fn: async (client, item) -> raw_response
            process_fn: async (raw_response, item) -> None
            client: Optional shared httpx client

        Returns:
            PipelineStats with throughput metrics.
        """
        self.stats = PipelineStats()
        self.stats.items_queued = len(items)
        self._queue = asyncio.Queue(maxsize=self.queue_size)
        self._stop = False

        owns_client = client is None
        if owns_client:
            client = httpx.AsyncClient(timeout=15)

        try:
            # Start consumers
            consumers = [
                asyncio.create_task(self._consumer(process_fn, i))
                for i in range(self.consumer_count)
            ]

            # Run producer (this blocks until all items fetched or budget exhausted)
            await self._producer(client, items, fetch_fn)

            # Signal consumers to stop
            for _ in range(self.consumer_count):
                await self._queue.put(None)

            # Wait for consumers to finish
            await asyncio.gather(*consumers)

        finally:
            if owns_client:
                await client.aclose()
            self.stats.finished_at = time.time()

        logger.info(
            f"Pipeline [{self.caller}]: {self.stats.items_fetched} fetched, "
            f"{self.stats.items_processed} processed, "
            f"{self.stats.items_failed} failed in {self.stats.elapsed_s:.1f}s "
            f"({self.stats.effective_rate:.1f}/s effective)"
        )

        return self.stats

    async def _producer(
        self,
        client: httpx.AsyncClient,
        items: list[Any],
        fetch_fn: Callable,
    ):
        """Fetch items at rate-limited speed, put responses on queue."""
        from app.shared_rate_limiter import rate_limiter
        from app.api_usage_tracker import track_api_call

        for item in items:
            if self.stats.items_fetched >= self.max_calls:
                logger.info(f"Pipeline [{self.caller}]: budget exhausted at {self.max_calls} calls")
                break

            try:
                # Wait for rate limiter
                acquired = await rate_limiter.acquire(self.provider, timeout=30)
                if not acquired:
                    self.stats.rate_limit_hits += 1
                    continue

                start = time.time()
                try:
                    result = await fetch_fn(client, item)
                    latency = (time.time() - start) * 1000
                    self.stats.total_latency_ms += latency
                    self.stats.items_fetched += 1

                    track_api_call(
                        self.provider, f"/{self.caller}",
                        caller=self.caller,
                        status=200,
                        latency_ms=int(latency),
                    )

                    rate_limiter.report_success(self.provider)

                    # Put on queue for consumer (blocks if queue is full)
                    await self._queue.put((result, item))

                except httpx.HTTPStatusError as e:
                    latency = (time.time() - start) * 1000
                    status = e.response.status_code if e.response else 500

                    track_api_call(
                        self.provider, f"/{self.caller}",
                        caller=self.caller,
                        status=status,
                        latency_ms=int(latency),
                    )

                    if status == 429:
                        rate_limiter.report_429(self.provider)
                        self.stats.rate_limit_hits += 1
                    else:
                        self.stats.fetch_errors += 1

            except Exception as e:
                self.stats.fetch_errors += 1
                logger.debug(f"Pipeline [{self.caller}] fetch error: {e}")

    async def _consumer(self, process_fn: Callable, consumer_id: int):
        """Process queued items — parse + insert to DB."""
        while True:
            entry = await self._queue.get()

            if entry is None:
                # Poison pill — stop this consumer
                self._queue.task_done()
                break

            result, item = entry
            try:
                await process_fn(result, item)
                self.stats.items_processed += 1
            except Exception as e:
                self.stats.process_errors += 1
                logger.debug(f"Pipeline [{self.caller}] consumer {consumer_id} error: {e}")
            finally:
                self._queue.task_done()
