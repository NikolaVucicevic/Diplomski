from concurrent.futures import ThreadPoolExecutor

import httpx


INVENTORY_URL = "http://localhost:8002"


# =========================================================
# TEST 1
# Concurrent reserve
# =========================================================

def test_concurrent_inventory_reserve():

    # Kreiramo poseban proizvod samo za ovaj test.
    # Na stanju postoji 5 komada.
    response = httpx.post(
        f"{INVENTORY_URL}/products",
        json={
            "name": "Concurrency Test Product",
            "quantity": 5
        },
        timeout=10.0
    )

    assert response.status_code == 200

    product_id = response.json()["id"]

    try:

        # Svaka Saga pokusava da rezervise
        # 1 komad istog proizvoda.
        def reserve(saga_id):
            return httpx.post(
                f"{INVENTORY_URL}/reserve",
                json={
                    "saga_id": saga_id,
                    "product_id": product_id,
                    "quantity": 1
                },
                timeout=20.0
            )

        # Pokrecemo 20 zahteva paralelno.
        with ThreadPoolExecutor(max_workers=20) as executor:

            futures = [
                executor.submit(
                    reserve,
                    10000 + i
                )
                for i in range(20)
            ]

            responses = [
                future.result()
                for future in futures
            ]

        # Razdvajamo uspesne i neuspesne zahteve.
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

        # Postoji samo 5 proizvoda.
        # Tacno 5 Saga mora da uspe.
        assert len(successful) == 5

        # Preostalih 15 mora biti odbijeno.
        assert len(failed) == 15

        # -------------------------------------------------
        # Provera konacnog stanja proizvoda
        # -------------------------------------------------

        response = httpx.get(
            f"{INVENTORY_URL}/products",
            timeout=10.0
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

        # Kolicina mora biti tacno 0.
        # Ne sme otici u minus.
        assert product["quantity"] == 0

    finally:

        # -------------------------------------------------
        # CLEANUP
        # Brisemo rezervacije i proizvod napravljene testom
        # -------------------------------------------------

        cleanup_response = httpx.delete(
            f"{INVENTORY_URL}/test-data/product/{product_id}",
            timeout=10.0
        )

        assert cleanup_response.status_code == 200


# =========================================================
# TEST 2
# Concurrent release - razlicite Sage
# =========================================================

def test_concurrent_inventory_release_different_sagas():

    # Kreiramo proizvod sa 100 komada.
    response = httpx.post(
        f"{INVENTORY_URL}/products",
        json={
            "name": "Concurrent Multi Release Test Product",
            "quantity": 100
        },
        timeout=10.0
    )

    assert response.status_code == 200

    product_id = response.json()["id"]

    try:

        number_of_sagas = 20

        # -------------------------------------------------
        # 1. Kreiramo 20 RAZLICITIH rezervacija
        # -------------------------------------------------

        saga_ids = [
            50000 + i
            for i in range(number_of_sagas)
        ]

        for saga_id in saga_ids:

            response = httpx.post(
                f"{INVENTORY_URL}/reserve",
                json={
                    "saga_id": saga_id,
                    "product_id": product_id,
                    "quantity": 1
                },
                timeout=10.0
            )

            assert response.status_code == 200

        # Imali smo 100.
        # 20 Saga je rezervisalo po 1.
        #
        # 100 - 20 = 80

        response = httpx.get(
            f"{INVENTORY_URL}/products",
            timeout=10.0
        )

        assert response.status_code == 200

        products = response.json()

        product = next(
            product
            for product in products
            if product["id"] == product_id
        )

        print(
            "\nQuantity before concurrent release:",
            product["quantity"]
        )

        assert product["quantity"] == 80

        # -------------------------------------------------
        # 2. Svaka Saga oslobadja svoju rezervaciju
        # -------------------------------------------------

        def release(saga_id):
            return httpx.post(
                f"{INVENTORY_URL}/release",
                json={
                    "saga_id": saga_id
                },
                timeout=20.0
            )

        # Svih 20 release operacija pokrecemo konkurentno.
        with ThreadPoolExecutor(max_workers=20) as executor:

            futures = [
                executor.submit(
                    release,
                    saga_id
                )
                for saga_id in saga_ids
            ]

            responses = [
                future.result()
                for future in futures
            ]

        # -------------------------------------------------
        # 3. Proveravamo odgovore
        # -------------------------------------------------

        successful = [
            response
            for response in responses
            if response.status_code == 200
        ]

        print(
            "Successful releases:",
            len(successful)
        )

        # Svih 20 legitimnih release operacija
        # mora da uspe.
        assert len(successful) == 20

        # -------------------------------------------------
        # 4. Proveravamo konacnu kolicinu
        # -------------------------------------------------

        response = httpx.get(
            f"{INVENTORY_URL}/products",
            timeout=10.0
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

        # Pre release-a smo imali 80.
        #
        # 20 razlicitih Saga vraca po 1:
        #
        # 80 + 20 = 100
        assert product["quantity"] == 100

        # -------------------------------------------------
        # 5. Proveravamo Reservation statuse
        # -------------------------------------------------

        response = httpx.get(
            f"{INVENTORY_URL}/reservations",
            timeout=10.0
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

        # Mora da postoji svih 20 rezervacija.
        assert len(test_reservations) == 20

        # Svih 20 mora biti RELEASED.
        assert len(released_reservations) == 20

    finally:

        # -------------------------------------------------
        # CLEANUP
        # -------------------------------------------------

        cleanup_response = httpx.delete(
            f"{INVENTORY_URL}/test-data/product/{product_id}",
            timeout=10.0
        )

        assert cleanup_response.status_code == 200