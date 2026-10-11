
import time
import httpx

from fastapi.testclient import TestClient

import orchestrator_service.http_client as retry_client
from orchestrator_service.main import app


ORDER = "http://127.0.0.1:8001"
INVENTORY = "http://127.0.0.1:8002"
PAYMENT = "http://127.0.0.1:8003"


def test_single_saga_timing(monkeypatch):

    timings = []

    # Originalne metode zajednickog HTTP klijenta
    real_post = retry_client.client.post
    real_put = retry_client.client.put

    def timed_post(url, *args, **kwargs):
        start = time.perf_counter()

        try:
            return real_post(url, *args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            timings.append((f"POST {url}", elapsed))

    def timed_put(url, *args, **kwargs):
        start = time.perf_counter()

        try:
            return real_put(url, *args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            timings.append((f"PUT {url}", elapsed))

    # Priprema testnih podataka
    with httpx.Client(trust_env=False) as setup_client:

        product = setup_client.post(
            f"{INVENTORY}/products",
            json={
                "name": "timing-test",
                "quantity": 1
            },
            timeout=10
        )
        product.raise_for_status()

        account = setup_client.post(
            f"{PAYMENT}/accounts",
            json={
                "client_id": 999999,
                "balance": 100
            },
            timeout=10
        )
        account.raise_for_status()

    product_id = product.json()["id"]
    account_id = account.json()["id"]

    # Presrecemo metode zajednickog HTTP klijenta
    monkeypatch.setattr(retry_client.client, "post", timed_post)
    monkeypatch.setattr(retry_client.client, "put", timed_put)

    # Pokrecemo jednu Sagu
    with TestClient(app) as client:

        start = time.perf_counter()

        response = client.post(
            "/saga",
            json={
                "product_id": product_id,
                "quantity": 1,
                "price": 1.0,
                "account_id": account_id
            }
        )

        total = time.perf_counter() - start

    # Ispis rezultata
    print("\n===== VREME IZVRSAVANJA JEDNE SAGE =====")

    for operation, elapsed in timings:
        print(f"{operation}: {elapsed:.4f} s")

    http_total = sum(elapsed for _, elapsed in timings)

    print(f"\nUKUPNO VREME HTTP POZIVA: {http_total:.4f} s")
    print(f"OSTALO VREME (orkestrator, baza): {total - http_total:.4f} s")
    print(f"UKUPNO VREME SAGE: {total:.4f} s")
    print(f"HTTP status: {response.status_code}")
    print(f"Odgovor: {response.text}")

    assert response.status_code == 200
    assert response.json()["status"] == "PAID"
    assert len(timings) == 4
