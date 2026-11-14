import httpx
from django.conf import settings


class ApiError(Exception):
    pass


class RetryableStatusError(Exception):
    pass


RETRYABLE_ERRORS = (httpx.TimeoutException, httpx.TransportError, RetryableStatusError)


def is_retryable(status):
    return status == 429 or status >= 500


def fetch(path):
    timeout = httpx.Timeout(settings.API_TIMEOUT, connect=30)
    response = httpx.get(f'{settings.API_BASE_URL}{path}', timeout=timeout)
    if is_retryable(response.status_code):
        raise RetryableStatusError(f'{path}: HTTP {response.status_code}')
    if response.is_error:
        raise ApiError(f'{path}: HTTP {response.status_code}')
    payload = response.json()
    status = payload.get('status', 200)
    if is_retryable(status):
        raise RetryableStatusError(f'{path}: status {status}')
    if status != 200:
        raise ApiError(f'{path}: {payload.get("data")}')
    return payload


def fetch_people():
    return fetch('/people')['data']


def fetch_draft(batch):
    return fetch(f'/draft/{batch}')['data']


def fetch_fights(batch):
    return fetch(f'/fight/{batch}')['data']
