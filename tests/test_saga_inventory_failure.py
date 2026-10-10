
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import uuid

import httpx
import pytest


ORCHESTRATOR_URL = "http://localhost:8004"
ORDER_URL = "http://localhost:8001"
INVENTORY_URL = "http://localhost:8002"
PAYMENT_URL = "http://localhost:8003"

NUM_SAGAS = 20
TIMEOUT = 60.0

INITIAL_QUANTITY = 10
INITIAL_BALANCE = 1000.0
ORDER_PRICE = 100.0


def test_concurrent_complete_sagas():

    product_id = None
    account_id = None
    existing_saga_ids = set()

    with httpx.Client(timeout=TIMEOUT) as client:

        # 1. Sacuvamo postojece Saga ID-jeve
        response = client.get(
            f"{ORCHESTRATOR_URL}/sagas"
        )
        assert response.status_code == 200

        existing_saga_ids = {
            saga["id"] for saga in response.json()
        }

        try:

            # 2. Kreiranje testnog proizvoda
            response = client.post(
                f"{INVENTORY_URL}/products",
                json={
                    "name": f"Integration Test {uuid.uuid4().hex}",
                    "quantity": INITIAL_QUANTITY
                }
            )

            assert response.status_code == 200
            product_id = response.json()["id"]

            # 3. Kreiranje testnog racuna
            response = client.post(
                f"{PAYMENT_URL}/accounts",
                json={
                    "client_id": 99999,
                    "balance": INITIAL_BALANCE
                }
            )

            assert response.status_code == 200
            account_id = response.json()["id"]

            print("\n========== INITIAL STATE ==========")
            print("Product ID:", product_id)
            print("Initial quantity:", INITIAL_QUANTITY)
            print("Account ID:", account_id)
            print("Initial balance:", INITIAL_BALANCE)
            print("Number of sagas:", NUM_SAGAS)

            # 4. Jedna kompletna Saga transakcija
            def execute_saga(index):

                with httpx.Client(timeout=TIMEOUT) as worker:
                    response = worker.post(
                        f"{ORCHESTRATOR_URL}/saga",
                        json={
                            "product_id": product_id,
                            "quantity": 1,
                            "price": ORDER_PRICE,
                            "account_id": account_id
                        }
                    )

                return index, response

            # 5. Pokretanje 20 Saga konkurentno
            with ThreadPoolExecutor(
                max_workers=NUM_SAGAS
            ) as executor:

                results = list(
                    executor.map(
                        execute_saga,
                        range(NUM_SAGAS)
                    )
                )

            # 6. Analiza HTTP odgovora
            successful = [
                response
                for _, response in results
                if response.status_code == 200
            ]

            failed = [
                response
                for _, response in results
                if response.status_code in (400, 409)
            ]

            print("\n========== SAGA RESULTS ==========")

            for index, response in results:
                print(
                    f"Request {index + 1}: "
                    f"HTTP {response.status_code}"
                )

            print("Successful sagas:", len(successful))
            print("Failed sagas:", len(failed))

            assert len(successful) + len(failed) == NUM_SAGAS

            assert all(
                response.json()["status"] == "PAID"
                for response in successful
            )

            # 7. Provera Saga statusa u bazi
            response = client.get(
                f"{ORCHESTRATOR_URL}/sagas"
            )

            assert response.status_code == 200

            new_sagas = [
                saga for saga in response.json()
                if saga["id"] not in existing_saga_ids
            ]

            assert len(new_sagas) == NUM_SAGAS

            status_counts = Counter(
                saga["status"] for saga in new_sagas
            )

            print("\n========== SAGA STATUSES ==========")

            for status, count in status_counts.items():
                print(f"{status}: {count}")

            completed_sagas = [
                saga for saga in new_sagas
                if saga["status"] == "COMPLETED"
            ]

            assert len(completed_sagas) == len(successful)

            assert all(
                saga["current_step"] == "COMPLETED"
                for saga in completed_sagas
            )

            assert status_counts["COMPENSATION_FAILED"] == 0

            assert all(
                saga["status"] in (
                    "COMPLETED",
                    "COMPENSATED",
                    "FAILED"
                )
                for saga in new_sagas
            )

            # 8. Provera porudzbina
            response = client.get(
                f"{ORDER_URL}/orders"
            )

            assert response.status_code == 200

            saga_ids = {
                saga["id"] for saga in new_sagas
            }

            orders = [
                order for order in response.json()
                if order["saga_id"] in saga_ids
            ]

            successful_order_ids = {
                response.json()["order_id"]
                for response in successful
            }

            paid_orders = [
                order for order in orders
                if order["status"] == "PAID"
            ]

            cancelled_orders = [
                order for order in orders
                if order["status"] == "CANCELLED"
            ]

            print("\n========== ORDER RESULTS ==========")
            print("Total orders:", len(orders))
            print("Paid orders:", len(paid_orders))
            print("Cancelled orders:", len(cancelled_orders))

            assert len(paid_orders) == len(successful)

            assert {
                order["id"] for order in paid_orders
            } == successful_order_ids

            assert len(orders) == (
                len(paid_orders) + len(cancelled_orders)
            )

            # 9. Provera rezervacija
            response = client.get(
                f"{INVENTORY_URL}/reservations"
            )

            assert response.status_code == 200

            reservations = [
                reservation for reservation in response.json()
                if reservation["saga_id"] in saga_ids
            ]

            active_reservations = [
                reservation for reservation in reservations
                if reservation["status"] == "RESERVED"
            ]

            released_reservations = [
                reservation for reservation in reservations
                if reservation["status"] == "RELEASED"
            ]

            print("\n========== INVENTORY RESULTS ==========")
            print("Reservations:", len(reservations))
            print("Active reservations:", len(active_reservations))
            print("Released reservations:", len(released_reservations))

            assert len(active_reservations) == len(successful)

            assert len(reservations) == (
                len(active_reservations) +
                len(released_reservations)
            )

            # 10. Provera placanja
            response = client.get(
                f"{PAYMENT_URL}/payments"
            )

            assert response.status_code == 200

            payments = [
                payment for payment in response.json()
                if payment["saga_id"] in saga_ids
            ]

            completed_payments = [
                payment for payment in payments
                if payment["status"] == "COMPLETED"
            ]

            refunded_payments = [
                payment for payment in payments
                if payment["status"] == "REFUNDED"
            ]

            print("\n========== PAYMENT RESULTS ==========")
            print("Total payments:", len(payments))
            print("Completed payments:", len(completed_payments))
            print("Refunded payments:", len(refunded_payments))

            assert len(completed_payments) == len(successful)

            assert len(payments) == (
                len(completed_payments) +
                len(refunded_payments)
            )

            # Detaljan pregled po Saga ID-ju (stanje nakon svih zahteva)
            print("\n========== DETAILED SAGA RESULTS ==========")
            orders_by_saga = {order["saga_id"]: order for order in orders}
            reservations_by_saga = {}
            for reservation in reservations:
                reservations_by_saga.setdefault(reservation["saga_id"], []).append(reservation)
            payments_by_saga = {}
            for payment in payments:
                payments_by_saga.setdefault(payment["saga_id"], []).append(payment)

            for saga in sorted(new_sagas, key=lambda item: item["id"]):
                saga_id = saga["id"]
                order = orders_by_saga.get(saga_id)
                saga_reservations = reservations_by_saga.get(saga_id, [])
                saga_payments = payments_by_saga.get(saga_id, [])

                order_description = (
                    f"{order['id']} ({order['status']})" if order else "NOT CREATED"
                )
                reservation_description = (
                    ", ".join(
                        f"{r['id']} ({r['status']})" for r in saga_reservations
                    ) if saga_reservations else "NONE"
                )
                payment_description = (
                    ", ".join(
                        f"{p['id']} ({p['status']})" for p in saga_payments
                    ) if saga_payments else "NONE"
                )

                print(f"\nSaga {saga_id} | {saga['status']} | step: {saga['current_step']}")
                print(f"  Order:       {order_description}")
                print(f"  Inventory:   {reservation_description}")
                print(f"  Payment:     {payment_description}")

            print("========== END DETAILED RESULTS ==========\n")

            # 11. Provera konacnog stanja proizvoda
            response = client.get(
                f"{INVENTORY_URL}/products"
            )

            assert response.status_code == 200

            product = next(
                product for product in response.json()
                if product["id"] == product_id
            )

            final_quantity = product["quantity"]

            expected_quantity = (
                INITIAL_QUANTITY - len(successful)
            )

            # 12. Provera konacnog stanja racuna
            response = client.get(
                f"{PAYMENT_URL}/accounts/{account_id}"
            )

            assert response.status_code == 200

            final_balance = response.json()["balance"]

            expected_balance = (
                INITIAL_BALANCE -
                len(successful) * ORDER_PRICE
            )

            print("\n========== FINAL STATE ==========")

            print("Final quantity:", final_quantity)
            print("Expected quantity:", expected_quantity)

            print("Final balance:", final_balance)
            print("Expected balance:", expected_balance)

            # 13. Zavrsne provere konzistentnosti
            assert final_quantity >= 0
            assert final_balance >= 0

            assert final_quantity == expected_quantity

            assert abs(
                final_balance - expected_balance
            ) < 0.001

            assert len(successful) <= INITIAL_QUANTITY

            print("\n========== TEST PASSED ==========")

        finally:

            # 14. Automatsko ciscenje testnih podataka
            print("\n========== CLEANUP ==========")

            cleanup_errors = []

            def delete_test_data(url, description):
                try:
                    response = client.delete(url)

                    if response.status_code != 200:
                        raise RuntimeError(
                            f"HTTP {response.status_code}: "
                            f"{response.text}"
                        )

                    print("Deleted:", description)

                except Exception as exc:
                    cleanup_errors.append(
                        f"{description}: {exc}"
                    )
                    print("Cleanup failed:", description, exc)

            # Pronalazimo nove Sage
            new_sagas = []

            try:
                response = client.get(
                    f"{ORCHESTRATOR_URL}/sagas"
                )
                response.raise_for_status()

                new_sagas = [
                    saga for saga in response.json()
                    if saga["id"] not in existing_saga_ids
                ]

            except Exception as exc:
                cleanup_errors.append(
                    f"Fetching sagas: {exc}"
                )

            saga_ids = {
                saga["id"] for saga in new_sagas
            }

            # Brisanje porudzbina
            try:
                response = client.get(
                    f"{ORDER_URL}/orders"
                )
                response.raise_for_status()

                orders = [
                    order for order in response.json()
                    if order["saga_id"] in saga_ids
                ]

                for order in orders:
                    delete_test_data(
                        f"{ORDER_URL}/test-data/order/{order['id']}",
                        f"Order {order['id']}"
                    )

            except Exception as exc:
                cleanup_errors.append(
                    f"Fetching orders: {exc}"
                )

            # Brisanje rezervacija i proizvoda
            if product_id is not None:
                delete_test_data(
                    f"{INVENTORY_URL}/test-data/product/{product_id}",
                    f"Product {product_id} and reservations"
                )

            # Brisanje placanja i racuna
            if account_id is not None:
                delete_test_data(
                    f"{PAYMENT_URL}/test-data/account/{account_id}",
                    f"Account {account_id} and payments"
                )

            # Brisanje Saga zapisa
            for saga in new_sagas:
                delete_test_data(
                    f"{ORCHESTRATOR_URL}/test-data/saga/{saga['id']}",
                    f"Saga {saga['id']}"
                )

            print("========== CLEANUP FINISHED ==========")

            if cleanup_errors:
                print("\nCleanup errors:")
                for error in cleanup_errors:
                    print("-", error)

                pytest.fail(
                    "Cleanup nije potpuno uspeo: "
                    + "; ".join(cleanup_errors)
                )

