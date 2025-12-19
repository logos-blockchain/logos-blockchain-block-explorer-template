import requests
from rusty_results import Option

from core.authentication import Authentication


def get(url, params=None, auth: Option[Authentication] = None, **kwargs):
    headers = kwargs.get("headers", {})
    if auth.is_some:
        headers["Authorization"] = auth.unwrap().for_requests()
    return requests.get(url, params, headers=headers, **kwargs)
