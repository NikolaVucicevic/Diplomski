
import httpx
import pytest

import orchestrator_service.http_client as http_client


class FakeResponse:

    def __init__(self, status_code):
        self.status_code = status_code


# 1. POST: prva dva pokusaja 500, treci uspe
def test_post_retry_success_after_failures(monkeypatch):

    call_count = 0

    print("\n========== RETRY: 500 -> 500 -> 200 ==========")

    def fake_post(url, json, timeout):
        nonlocal call_count
        call_count += 1

        if call_count < 3:
            print(f"Attempt {call_count}: HTTP 500")
            return FakeResponse(500)

        print(f"Attempt {call_count}: HTTP 200")
        return FakeResponse(200)

    monkeypatch.setattr(
        http_client.httpx,
        "post",
        fake_post
    )

    monkeypatch.setattr(
        http_client.time,
        "sleep",
        lambda seconds: None
    )

    response = http_client.post_with_retry(
        "http://test",
        json={"test": "data"}
    )

    print("Total attempts:", call_count)
    print("Final HTTP status:", response.status_code)

    assert response.status_code == 200
    assert call_count == 3

    print("TEST PASSED")


# 2. POST: 400 se ne retry-uje
def test_post_no_retry_on_400(monkeypatch):

    call_count = 0

    print("\n========== RETRY: HTTP 400 ==========")

    def fake_post(url, json, timeout):
        nonlocal call_count
        call_count += 1

        print(f"Attempt {call_count}: HTTP 400")
        return FakeResponse(400)

    monkeypatch.setattr(
        http_client.httpx,
        "post",
        fake_post
    )

    response = http_client.post_with_retry(
        "http://test",
        json={"test": "data"}
    )

    print("Total attempts:", call_count)
    print("Final HTTP status:", response.status_code)

    assert response.status_code == 400
    assert call_count == 1

    print("TEST PASSED - No retry on client error")


# 3. POST: sva tri pokusaja vracaju 500
def test_post_all_retries_fail(monkeypatch):

    call_count = 0

    print("\n========== RETRY: 500 -> 500 -> 500 ==========")

    def fake_post(url, json, timeout):
        nonlocal call_count
        call_count += 1

        print(f"Attempt {call_count}: HTTP 500")
        return FakeResponse(500)

    monkeypatch.setattr(
        http_client.httpx,
        "post",
        fake_post
    )

    monkeypatch.setattr(
        http_client.time,
        "sleep",
        lambda seconds: None
    )

    response = http_client.post_with_retry(
        "http://test",
        json={"test": "data"}
    )

    print("Total attempts:", call_count)
    print("Final HTTP status:", response.status_code)

    assert response.status_code == 500
    assert call_count == 3

    print("TEST PASSED - All retries exhausted")


# 4. POST: timeout, pa sledeci pokusaj uspe
def test_post_retry_after_timeout(monkeypatch):

    call_count = 0

    print("\n========== RETRY: TIMEOUT -> 200 ==========")

    def fake_post(url, json, timeout):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            print(f"Attempt {call_count}: TIMEOUT")
            raise httpx.TimeoutException("Timeout")

        print(f"Attempt {call_count}: HTTP 200")
        return FakeResponse(200)

    monkeypatch.setattr(
        http_client.httpx,
        "post",
        fake_post
    )

    monkeypatch.setattr(
        http_client.time,
        "sleep",
        lambda seconds: None
    )

    response = http_client.post_with_retry(
        "http://test",
        json={"test": "data"}
    )

    print("Total attempts:", call_count)
    print("Final HTTP status:", response.status_code)

    assert response.status_code == 200
    assert call_count == 2

    print("TEST PASSED - Recovered after timeout")


# 5. POST: sva tri pokusaja zavrsavaju timeout-om
def test_post_all_timeouts(monkeypatch):

    call_count = 0

    print("\n========== RETRY: ALL TIMEOUTS ==========")

    def fake_post(url, json, timeout):
        nonlocal call_count
        call_count += 1

        print(f"Attempt {call_count}: TIMEOUT")
        raise httpx.TimeoutException("Timeout")

    monkeypatch.setattr(
        http_client.httpx,
        "post",
        fake_post
    )

    monkeypatch.setattr(
        http_client.time,
        "sleep",
        lambda seconds: None
    )

    response = http_client.post_with_retry(
        "http://test",
        json={"test": "data"}
    )

    print("Total attempts:", call_count)
    print("Final HTTP status:", response.status_code)

    assert response.status_code == 503
    assert call_count == 3

    print("TEST PASSED - Service unavailable after retries")


# 6. PUT: prvi pokusaj 500, drugi uspe
def test_put_retry_success(monkeypatch):

    call_count = 0

    print("\n========== PUT RETRY: 500 -> 200 ==========")

    def fake_put(url, json, timeout):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            print(f"Attempt {call_count}: HTTP 500")
            return FakeResponse(500)

        print(f"Attempt {call_count}: HTTP 200")
        return FakeResponse(200)

    monkeypatch.setattr(
        http_client.httpx,
        "put",
        fake_put
    )

    monkeypatch.setattr(
        http_client.time,
        "sleep",
        lambda seconds: None
    )

    response = http_client.put_with_retry(
        "http://test",
        json={"status": "PAID"}
    )

    print("Total attempts:", call_count)
    print("Final HTTP status:", response.status_code)

    assert response.status_code == 200
    assert call_count == 2

    print("TEST PASSED")
