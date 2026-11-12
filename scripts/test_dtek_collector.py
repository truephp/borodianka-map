"""Offline concurrency regression tests for the DTEK street collector."""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_dtek_shared_houses import collect_pairs


class DtekCollectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_bounded_parallelism_and_input_order(self):
        active = 0
        peak = 0
        async def fetch(city, street):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.015 if street.endswith("0") else 0.002)
            active -= 1
            return {"city": city, "street": street, "response": {"result": True, "data": {}}}

        pairs = [("с-ще Бородянка", str(i)) for i in range(5)]
        # Use a fast, but valid, fake sleeper to avoid wall-clock waits.
        original_sleep = asyncio.sleep
        async def no_delay(seconds):
            await original_sleep(0 if seconds >= 1 else seconds)
        import fetch_dtek_shared_houses as module
        module.asyncio.sleep = no_delay
        try:
            result = await collect_pairs(pairs, fetch, workers=2, delay_seconds=1)
        finally:
            module.asyncio.sleep = original_sleep
        self.assertEqual([r["street"] for r in result], [str(i) for i in range(5)])
        self.assertEqual(peak, 2)

    async def test_transient_failure_retried_and_persistent_error_retained(self):
        attempts = {}
        async def fetch(city, street):
            attempts[street] = attempts.get(street, 0) + 1
            if street == "broken" or (street == "transient" and attempts[street] == 1):
                raise RuntimeError("DTEK error")
            return {"city": city, "street": street, "response": {"result": True, "data": {}}}
        original_sleep = asyncio.sleep
        async def no_delay(_seconds):
            await original_sleep(0)
        import fetch_dtek_shared_houses as module
        module.asyncio.sleep = no_delay
        try:
            result = await collect_pairs(
                [("Бородянка", "transient"), ("Бородянка", "broken")],
                fetch, workers=2, delay_seconds=1
            )
        finally:
            module.asyncio.sleep = original_sleep
        self.assertIn("response", result[0])
        self.assertEqual(result[1]["error"], "DTEK error")
        self.assertEqual(attempts, {"transient": 2, "broken": 3})


if __name__ == "__main__":
    unittest.main()
