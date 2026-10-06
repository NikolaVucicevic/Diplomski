import time
import httpx


def post_with_retry(url, json, max_retries=3, timeout=2.0):

    for attempt in range(max_retries):

        try:
            response = httpx.post(
                url,
                json=json,
                timeout=timeout
            )

            # Serverska greska - pokusaj ponovo
            if response.status_code >= 500:
                if attempt < max_retries - 1:
                    time.sleep(0.5)
                    continue

            # 2xx ili 4xx - nema retry-ja
            return response

        except httpx.RequestError:
            # Mrezna greska ili timeout
            if attempt < max_retries - 1:
                time.sleep(0.5)
                continue

            raise


def put_with_retry(url, json, max_retries=3, timeout=2.0):

    for attempt in range(max_retries):

        try:
            response = httpx.put(
                url,
                json=json,
                timeout=timeout
            )

            # Serverska greska - pokusaj ponovo
            if response.status_code >= 500:
                if attempt < max_retries - 1:
                    time.sleep(0.5)
                    continue

            # 2xx ili 4xx - nema retry-ja
            return response

        except httpx.RequestError:
            # Mrezna greska ili timeout
            if attempt < max_retries - 1:
                time.sleep(0.5)
                continue

            raise