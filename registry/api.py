import httpx
from django.conf import settings


class ApiError(Exception):
    pass


RETRYABLE_ERRORS = (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError)


def fetch(path):
    timeout = httpx.Timeout(settings.API_TIMEOUT, connect=30)
    response = httpx.get(f'{settings.API_BASE_URL}{path}', timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if payload.get('status', 200) != 200:
        raise ApiError(f'{path}: {payload.get("data")}')
    return payload


def fetch_people():
    return fetch('/people')['data']


def fetch_draft(batch):
    return fetch(f'/draft/{batch}')['data']


def fetch_fights(batch):
    return fetch(f'/fight/{batch}')['data']
