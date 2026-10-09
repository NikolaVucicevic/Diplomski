from concurrent.futures import ThreadPoolExecutor

import httpx

from threading import Barrier

ORDER_URL = "http://localhost:8001"
INVENTORY_URL = "http://localhost:8002"
PAYMENT_URL = "http://localhost:8003"

NUM_THREADS = 20
TIMEOUT = 20.0



# TEST 1
# 20 razlicitih Saga konkurentno rezervise isti proizvod


def test_concurrent_inventory_reserve():

    with httpx.Client(timeout=TIMEOUT) as client:

        response = client.post(
            f"{INVENTORY_URL}/products",
            json={
                "name": "Concurrency Test Product",
                "quantity": 5
            }
        )

        assert response.status_code == 200
        product_id = response.json()["id"]

        try:

            def reserve(saga_id):
                return client.post(
                    f"{INVENTORY_URL}/reserve",
                    json={
                        "saga_id": saga_id,
                        "product_id": product_id,
                        "quantity": 1
                    }
                )

            # 20 konkurentnih reserve operacija
            with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
                responses = list(
                    executor.map(
                        reserve,
                        range(10000, 10000 + NUM_THREADS)
                    )
                )

            successful = [
                response
                for response in responses
                if response.status_code == 200
            ]

            failed = [
                response
                for response in responses
                if response.status_code == 400
            ]

            print(
                "\nSuccessful reservations:",
                len(successful)
            )

            print(
                "Failed reservations:",
                len(failed)
            )

            assert len(successful) == 5
            assert len(failed) == 15

            # Provera konacnog stanja
            response = client.get(
                f"{INVENTORY_URL}/products"
            )

            assert response.status_code == 200

            products = response.json()

            product = next(
                product
                for product in products
                if product["id"] == product_id
            )

            print(
                "Final quantity:",
                product["quantity"]
            )

            assert product["quantity"] == 0

        finally:

            # Automatsko brisanje testnih podataka
            cleanup_response = client.delete(
                f"{INVENTORY_URL}/test-data/product/{product_id}"
            )

            assert cleanup_response.status_code == 200



# TEST 2
# 20 razlicitih Saga konkurentno radi reserve,
# a zatim konkurentno release


def test_concurrent_inventory_release_different_sagas():

    with httpx.Client(timeout=TIMEOUT) as client:

        response = client.post(
            f"{INVENTORY_URL}/products",
            json={
                "name": "Concurrent Multi Release Test Product",
                "quantity": 100
            }
        )

        assert response.status_code == 200
        product_id = response.json()["id"]

        try:

            number_of_sagas = NUM_THREADS

            saga_ids = [
                50000 + i
                for i in range(number_of_sagas)
            ]

            # =================================================
            # 1. Konkurentno pravimo 20 rezervacija
            # =================================================

            def reserve(saga_id):
                return client.post(
                    f"{INVENTORY_URL}/reserve",
                    json={
                        "saga_id": saga_id,
                        "product_id": product_id,
                        "quantity": 1
                    }
                )

            with ThreadPoolExecutor(
                max_workers=number_of_sagas
            ) as executor:

                reserve_responses = list(
                    executor.map(
                        reserve,
                        saga_ids
                    )
                )

            successful_reserves = [
                response
                for response in reserve_responses
                if response.status_code == 200
            ]

            print(
                "\nSuccessful initial reservations:",
                len(successful_reserves)
            )

            assert len(successful_reserves) == 20

            # =================================================
            # 2. Posle 20 rezervacija mora ostati 80
            # =================================================

            response = client.get(
                f"{INVENTORY_URL}/products"
            )

            assert response.status_code == 200

            products = response.json()

            product = next(
                product
                for product in products
                if product["id"] == product_id
            )

            print(
                "Quantity before concurrent release:",
                product["quantity"]
            )

            assert product["quantity"] == 80

            # =================================================
            # 3. 20 razlicitih Saga konkurentno radi release
            # =================================================

            def release(saga_id):
                return client.post(
                    f"{INVENTORY_URL}/release",
                    json={
                        "saga_id": saga_id
                    }
                )

            with ThreadPoolExecutor(
                max_workers=number_of_sagas
            ) as executor:

                release_responses = list(
                    executor.map(
                        release,
                        saga_ids
                    )
                )

            successful_releases = [
                response
                for response in release_responses
                if response.status_code == 200
            ]

            print(
                "Successful releases:",
                len(successful_releases)
            )

            assert len(successful_releases) == 20

            # =================================================
            # 4. Provera konacne kolicine
            # =================================================

            response = client.get(
                f"{INVENTORY_URL}/products"
            )

            assert response.status_code == 200

            products = response.json()

            product = next(
                product
                for product in products
                if product["id"] == product_id
            )

            print(
                "Quantity after concurrent release:",
                product["quantity"]
            )

            # 100 - 20 + 20 = 100
            assert product["quantity"] == 100

            # =================================================
            # 5. Provera Reservation statusa
            # =================================================

            response = client.get(
                f"{INVENTORY_URL}/reservations"
            )

            assert response.status_code == 200

            reservations = response.json()

            test_reservations = [
                reservation
                for reservation in reservations
                if reservation["saga_id"] in saga_ids
            ]

            released_reservations = [
                reservation
                for reservation in test_reservations
                if reservation["status"] == "RELEASED"
            ]

            print(
                "Released reservations:",
                len(released_reservations)
            )

            assert len(test_reservations) == 20
            assert len(released_reservations) == 20

        finally:

            # Automatsko brisanje testnih podataka
            cleanup_response = client.delete(
                f"{INVENTORY_URL}/test-data/product/{product_id}"
            )

            assert cleanup_response.status_code == 200





# TEST 3
# Concurrent payments


def test_concurrent_payments():

    with httpx.Client(timeout=20.0) as client:

        response = client.post(
            f"{PAYMENT_URL}/accounts",
            json={
                "client_id": 99999,
                "balance": 500.0
            }
        )

        assert response.status_code == 200
        account_id = response.json()["id"]

        try:
            saga_ids = [20000 + i for i in range(20)]

            def pay(saga_id):
                return client.post(
                    f"{PAYMENT_URL}/pay",
                    json={
                        "saga_id": saga_id,
                        "order_id": saga_id,
                        "account_id": account_id,
                        "amount": 100.0
                    }
                )

            with ThreadPoolExecutor(max_workers=20) as executor:
                responses = list(executor.map(pay, saga_ids))

            successful = [
                r for r in responses
                if r.status_code == 200
            ]

            failed = [
                r for r in responses
                if r.status_code == 400
            ]

            print("\nSuccessful payments:", len(successful))
            print("Failed payments:", len(failed))

            assert len(successful) == 5
            assert len(failed) == 15

            # Provera konacnog stanja racuna
            response = client.get(
                f"{PAYMENT_URL}/accounts/{account_id}"
            )

            assert response.status_code == 200

            balance = response.json()["balance"]

            print("Final balance:", balance)

            assert balance == 0.0

        finally:
            cleanup_response = client.delete(
                f"{PAYMENT_URL}/test-data/account/{account_id}"
            )

            assert cleanup_response.status_code == 200



# TEST 4
# Concurrent refunds - razlicite Sage


def test_concurrent_refunds():

    with httpx.Client(timeout=20.0) as client:

        response = client.post(
            f"{PAYMENT_URL}/accounts",
            json={
                "client_id": 99998,
                "balance": 2000.0
            }
        )

        assert response.status_code == 200
        account_id = response.json()["id"]

        try:
            saga_ids = [30000 + i for i in range(20)]

            # 1. Dvadeset razlicitih Saga placa po 100

            def pay(saga_id):
                return client.post(
                    f"{PAYMENT_URL}/pay",
                    json={
                        "saga_id": saga_id,
                        "order_id": saga_id,
                        "account_id": account_id,
                        "amount": 100.0
                    }
                )

            with ThreadPoolExecutor(max_workers=20) as executor:
                responses = list(executor.map(pay, saga_ids))

            assert all(r.status_code == 200 for r in responses)

            # Posle 20 placanja stanje mora biti 0
            response = client.get(
                f"{PAYMENT_URL}/accounts/{account_id}"
            )

            assert response.status_code == 200

            balance = response.json()["balance"]

            print("\nBalance before refunds:", balance)

            assert balance == 0.0

            # 2. Dvadeset razlicitih Saga konkurentno
            #    vraca po 100 na isti racun

            def refund(saga_id):
                return client.post(
                    f"{PAYMENT_URL}/refund",
                    json={
                        "saga_id": saga_id
                    }
                )

            with ThreadPoolExecutor(max_workers=20) as executor:
                responses = list(executor.map(refund, saga_ids))

            successful = [
                r for r in responses
                if r.status_code == 200
            ]

            print("Successful refunds:", len(successful))

            assert len(successful) == 20

            # 3. Provera konacnog stanja
            response = client.get(
                f"{PAYMENT_URL}/accounts/{account_id}"
            )

            assert response.status_code == 200

            balance = response.json()["balance"]

            print("Balance after refunds:", balance)

            assert balance == 2000.0

            # 4. Provera statusa svih uplata
            response = client.get(
                f"{PAYMENT_URL}/payments"
            )

            assert response.status_code == 200

            payments = response.json()

            test_payments = [
                p for p in payments
                if p["saga_id"] in saga_ids
            ]

            refunded = [
                p for p in test_payments
                if p["status"] == "REFUNDED"
            ]

            print("Refunded payments:", len(refunded))

            assert len(test_payments) == 20
            assert len(refunded) == 20

        finally:
            cleanup_response = client.delete(
                f"{PAYMENT_URL}/test-data/account/{account_id}"
            )

            assert cleanup_response.status_code == 200


# TEST 5
# Concurrent Order Creation - ista Saga


def test_concurrent_order_creation():

    saga_id = 40000
    order_id = None

    with httpx.Client(timeout=20.0) as client:

        try:
            def create_order(_):
                return client.post(
                    f"{ORDER_URL}/create",
                    json={
                        "saga_id": saga_id,
                        "product_id": 1,
                        "quantity": 1,
                        "price": 100.0
                    }
                )

            # 20 konkurentnih zahteva za istu Sagu
            with ThreadPoolExecutor(max_workers=20) as executor:
                responses = list(
                    executor.map(create_order, range(20))
                )

            successful = [
                r for r in responses
                if r.status_code == 200
            ]

            print("\nSuccessful order requests:", len(successful))

            assert len(successful) == 20

            # Svi zahtevi moraju vratiti isti order_id
            order_ids = [
                r.json()["id"]
                for r in successful
            ]

            order_id = order_ids[0]

            print("Unique order IDs:", len(set(order_ids)))

            assert len(set(order_ids)) == 1

            # Provera da u bazi postoji samo jedna porudzbina
            response = client.get(f"{ORDER_URL}/orders")

            assert response.status_code == 200

            orders = response.json()

            test_orders = [
                order for order in orders
                if order["id"] == order_id
            ]

            assert len(test_orders) == 1

            print("Concurrent order creation: PASSED")

        finally:
            # Ako je test pao pre nego sto smo sacuvali
            # order_id, pokusavamo da ga pronadjemo.
            if order_id is None:
                response = client.get(f"{ORDER_URL}/orders")

                if response.status_code == 200:
                    for order in response.json():
                        if order.get("saga_id") == saga_id:
                            order_id = order["id"]
                            break

            if order_id is not None:
                cleanup_response = client.delete(
                    f"{ORDER_URL}/test-data/order/{order_id}"
                )

                assert cleanup_response.status_code == 200


# TEST 6
# Concurrent Order Status Update vs Cancel


def test_concurrent_order_status_and_cancel():

    saga_id = 40001

    with httpx.Client(timeout=20.0) as client:

        # 1. Kreiramo porudzbinu
        response = client.post(
            f"{ORDER_URL}/create",
            json={
                "saga_id": saga_id,
                "product_id": 1,
                "quantity": 1,
                "price": 100.0
            }
        )

        assert response.status_code == 200

        order_id = response.json()["id"]

        try:
            # 2. Obe niti cekaju jedna drugu
            barrier = Barrier(2)

            def mark_as_paid():
                barrier.wait()

                return client.put(
                    f"{ORDER_URL}/orders/status",
                    json={
                        "id": order_id,
                        "status": "PAID"
                    }
                )

            def cancel_order():
                barrier.wait()

                return client.post(
                    f"{ORDER_URL}/cancel",
                    json={
                        "order_id": order_id
                    }
                )

            # 3. Konkurentno pokretanje
            with ThreadPoolExecutor(max_workers=2) as executor:

                future_paid = executor.submit(mark_as_paid)
                future_cancel = executor.submit(cancel_order)

                paid_response = future_paid.result()
                cancel_response = future_cancel.result()

            print("\nPAID response:", paid_response.status_code)
            print("CANCEL response:", cancel_response.status_code)

            # Jedna operacija uspeva, druga dobija 409
            status_codes = sorted([
                paid_response.status_code,
                cancel_response.status_code
            ])

            assert status_codes == [200, 409]

            # 4. Provera konacnog statusa
            response = client.get(f"{ORDER_URL}/orders")

            assert response.status_code == 200

            orders = response.json()

            order = next(
                order
                for order in orders
                if order["id"] == order_id
            )

            print("Final order status:", order["status"])

            assert order["status"] in ["PAID", "CANCELLED"]

            # Proveravamo da status odgovara uspesnoj operaciji
            if paid_response.status_code == 200:
                assert order["status"] == "PAID"
            else:
                assert order["status"] == "CANCELLED"

            print("Concurrent status/cancel: PASSED")

        finally:
            cleanup_response = client.delete(
                f"{ORDER_URL}/test-data/order/{order_id}"
            )

            assert cleanup_response.status_code == 200


