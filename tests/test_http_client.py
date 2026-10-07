import httpx
import pytest

import orchestrator_service.http_client as http_client


class FakeResponse:

    def __init__(self, status_code):
        self.status_code = status_code


# 1. POST: prva dva pokusaja 500, treci uspe
def test_post_retry_success_after_failures(monkeypatch):

    call_count = 0

    def fake_post(url, json, timeout):
        nonlocal call_count
        call_count += 1

        if call_count < 3:
            return FakeResponse(500)

        return FakeResponse(200)

    monkeypatch.setattr(
        http_client.httpx,
        "post",
        fake_post
    )

    # Da test ne ceka 0.5 sekundi izmedju retry pokusaja
    monkeypatch.setattr(
        http_client.time,
        "sleep",
        lambda seconds: None
    )

    response = http_client.post_with_retry(
        "http://test",
        json={"test": "data"}
    )

    assert response.status_code == 200
    assert call_count == 3


# 2. POST: 400 se ne retry-uje
def test_post_no_retry_on_400(monkeypatch):

    call_count = 0

    def fake_post(url, json, timeout):
        nonlocal call_count
        call_count += 1

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

    assert response.status_code == 400
    assert call_count == 1


# 3. POST: sva tri pokusaja vracaju 500
def test_post_all_retries_fail(monkeypatch):

    call_count = 0

    def fake_post(url, json, timeout):
        nonlocal call_count
        call_count += 1

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

    assert response.status_code == 500
    assert call_count == 3


# 4. POST: timeout, pa sledeci pokusaj uspe
def test_post_retry_after_timeout(monkeypatch):

    call_count = 0

    def fake_post(url, json, timeout):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            raise httpx.TimeoutException("Timeout")

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

    assert response.status_code == 200
    assert call_count == 2

def test_post_all_timeouts(monkeypatch):

    call_count = 0

    def fake_post(url, json, timeout):
        nonlocal call_count
        call_count += 1

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

    assert response.status_code == 503
    assert call_count == 3


# 5. PUT: prvi pokusaj 500, drugi uspe
def test_put_retry_success(monkeypatch):

    call_count = 0

    def fake_put(url, json, timeout):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            return FakeResponse(500)

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

    assert response.status_code == 200
    assert call_count == 2