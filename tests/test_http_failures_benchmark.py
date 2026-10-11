
"""
Benchmark Saga orchestrator with injected transient HTTP 503 failures.

Run from project root with all services and PostgreSQL running:

    python -m pytest tests/test_http_failures_benchmark.py -v -s

WARNING:
Uses real service databases.
Run against disposable test databases only.
"""

import csv
import os
import random
import statistics
import time
from pathlib import Path

import httpx
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

from fastapi.testclient import TestClient

import orchestrator_service.http_client as retry_client
import orchestrator_service.main as saga_main


ORDER = "http://127.0.0.1:8001"
INVENTORY = "http://127.0.0.1:8002"
PAYMENT = "http://127.0.0.1:8003"
ORCHESTRATOR = "http://127.0.0.1:8004"

RATES = (0.0, 0.05, 0.10, 0.20, 0.30)

SAMPLES = int(
    os.getenv("SAGA_BENCHMARK_SAMPLES", "5")
)

OUTPUT = Path(
    os.getenv(
        "SAGA_BENCHMARK_OUTPUT",
        "saga_benchmark_results"
    )
)


def request_ok(response):
    response.raise_for_status()
    return response.json()


def cleanup_saga(client, saga_id, order_id):

    # Brisemo rezervaciju
    if saga_id is not None:
        response = client.delete(
            f"{INVENTORY}/reservations/{saga_id}",
            timeout=10
        )

        if response.status_code not in (200, 404):
            raise RuntimeError(
                f"Reservation cleanup failed: "
                f"{response.status_code}: {response.text}"
            )

    # Brisemo porudzbinu
    if order_id is not None:
        response = client.delete(
            f"{ORDER}/test-data/order/{order_id}",
            timeout=10
        )

        if response.status_code not in (200, 404):
            raise RuntimeError(
                f"Order cleanup failed: "
                f"{response.status_code}: {response.text}"
            )

    # Brisemo Sagu
    if saga_id is not None:
        response = client.delete(
            f"{ORCHESTRATOR}/test-data/saga/{saga_id}",
            timeout=10
        )

        if response.status_code not in (200, 404):
            raise RuntimeError(
                f"Saga cleanup failed: "
                f"{response.status_code}: {response.text}"
            )


def plot_results(rows):

    OUTPUT.mkdir(parents=True, exist_ok=True)

    csv_path = OUTPUT / "http_failures_results.csv"

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0])
        )

        writer.writeheader()
        writer.writerows(rows)

    for key, ylabel, filename in (
        (
            "success_pct",
            "Successful Sagas (%)",
            "http_success.png"
        ),
        (
            "mean_seconds",
            "Average duration per Saga (s)",
            "http_latency.png"
        ),
    ):

        plt.figure(figsize=(8, 5))

        for retries, label in (
            (False, "Without retry"),
            (True, "With retry")
        ):

            subset = [
                row for row in rows
                if row["retry"] == retries
            ]

            plt.plot(
                [row["error_pct"] for row in subset],
                [row[key] for row in subset],
                marker="o",
                label=label
            )

        plt.xlabel(
            "Injected HTTP 503 probability (%)"
        )

        plt.ylabel(ylabel)

        plt.title(
            "Saga execution with transient HTTP failures"
        )

        plt.legend()
        plt.grid(alpha=0.3)
        plt.tight_layout()

        plt.savefig(
            OUTPUT / filename,
            dpi=180
        )

        plt.close()


@pytest.mark.integration
@pytest.mark.benchmark
def test_http_failures_benchmark(monkeypatch):

    if SAMPLES < 1:
        raise ValueError(
            "SAGA_BENCHMARK_SAMPLES must be >= 1"
        )

    rows = []
    created_sagas = []

    product_id = None
    account_id = None

    # Koristimo poseban klijent za pripremu i ciscenje.
    # Ovaj klijent nije obuhvacen simulacijom gresaka.
    with httpx.Client(trust_env=False) as setup_client:

        # Provera dostupnosti servisa
        for base in (
            ORDER,
            INVENTORY,
            PAYMENT,
            ORCHESTRATOR
        ):

            request_ok(
                setup_client.get(
                    base + "/",
                    timeout=5
                )
            )

        try:

            # Priprema testnih podataka
            product = request_ok(
                setup_client.post(
                    f"{INVENTORY}/products",
                    json={
                        "name": "benchmark-http-failures",
                        "quantity": (
                            SAMPLES * len(RATES) * 2 + 20
                        )
                    },
                    timeout=10
                )
            )

            product_id = product["id"]

            account = request_ok(
                setup_client.post(
                    f"{PAYMENT}/accounts",
                    json={
                        "client_id": 900001,
                        "balance": float(
                            SAMPLES * len(RATES) * 2 + 20
                        )
                    },
                    timeout=10
                )
            )

            account_id = account["id"]

            # Cuvamo originalne metode zajednickog klijenta
            real_post = retry_client.client.post
            real_put = retry_client.client.put

            with TestClient(saga_main.app) as client:

                for retries in (False, True):

                    for rate in RATES:

                        successes = 0
                        durations = []

                        rng = random.Random(
                            20261010 + int(rate * 1000)
                        )

                        # Simulacija HTTP 503 greske pre slanja
                        def injected_post(
                            url,
                            *args,
                            **kwargs
                        ):

                            if rng.random() < rate:
                                return httpx.Response(
                                    status_code=503
                                )

                            return real_post(
                                url,
                                *args,
                                **kwargs
                            )

                        def injected_put(
                            url,
                            *args,
                            **kwargs
                        ):

                            if rng.random() < rate:
                                return httpx.Response(
                                    status_code=503
                                )

                            return real_put(
                                url,
                                *args,
                                **kwargs
                            )

                        # Ukljucivanje/iskljucivanje retry-ja
                        def call_post(
                            url,
                            json,
                            max_retries=3,
                            timeout=2.0
                        ):

                            return retry_client.post_with_retry(
                                url,
                                json,
                                max_retries=(
                                    3 if retries else 1
                                ),
                                timeout=timeout
                            )

                        def call_put(
                            url,
                            json,
                            max_retries=3,
                            timeout=2.0
                        ):

                            return retry_client.put_with_retry(
                                url,
                                json,
                                max_retries=(
                                    3 if retries else 1
                                ),
                                timeout=timeout
                            )

                        # Presrecemo samo zahteve orkestratora
                        with monkeypatch.context() as patch:

                            patch.setattr(
                                retry_client.client,
                                "post",
                                injected_post
                            )

                            patch.setattr(
                                retry_client.client,
                                "put",
                                injected_put
                            )

                            patch.setattr(
                                saga_main,
                                "post_with_retry",
                                call_post
                            )

                            patch.setattr(
                                saga_main,
                                "put_with_retry",
                                call_put
                            )

                            for _ in range(SAMPLES):

                                # Stanje pre pokretanja Sage
                                before_ids = {
                                    saga["id"]
                                    for saga in client.get(
                                        "/sagas"
                                    ).json()
                                }

                                started = time.perf_counter()

                                response = client.post(
                                    "/saga",
                                    json={
                                        "product_id": product_id,
                                        "quantity": 1,
                                        "price": 1.0,
                                        "account_id": account_id
                                    }
                                )

                                elapsed = (
                                    time.perf_counter() - started
                                )

                                durations.append(elapsed)

                                if response.status_code == 200:
                                    successes += 1

                                # Pronalazimo novokreiranu Sagu
                                after = client.get(
                                    "/sagas"
                                ).json()

                                new_sagas = [
                                    saga
                                    for saga in after
                                    if saga["id"] not in before_ids
                                ]

                                if len(new_sagas) != 1:
                                    raise AssertionError(
                                        "Expected exactly one "
                                        "new Saga, found "
                                        f"{len(new_sagas)}"
                                    )

                                saga = new_sagas[0]

                                created_sagas.append(
                                    (
                                        saga["id"],
                                        saga.get("order_id")
                                    )
                                )

                                if saga["status"] == "COMPENSATION_FAILED":
                                    print(
                                        "WARNING: compensation failed "
                                        f"for saga {saga['id']}"
                                    )

                        row = {
                            "retry": retries,
                            "error_pct": round(rate * 100),
                            "samples": SAMPLES,
                            "success_pct": round(
                                100 * successes / SAMPLES,
                                2
                            ),
                            "mean_seconds": round(
                                statistics.mean(durations),
                                4
                            )
                        }

                        rows.append(row)
                        print(row)

        finally:

            # Ciscenje se izvrsava bez simuliranih gresaka
            try:

                for saga_id, order_id in created_sagas:

                    cleanup_saga(
                        setup_client,
                        saga_id,
                        order_id
                    )

            finally:

                if account_id is not None:

                    setup_client.delete(
                        f"{PAYMENT}/test-data/account/{account_id}",
                        timeout=10
                    ).raise_for_status()

                if product_id is not None:

                    setup_client.delete(
                        f"{INVENTORY}/test-data/product/{product_id}",
                        timeout=10
                    ).raise_for_status()

    plot_results(rows)

    print(
        f"Saved CSV and charts in: {OUTPUT.resolve()}"
    )
