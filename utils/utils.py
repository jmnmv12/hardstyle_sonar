import requests
import logging
import time

logger = logging.getLogger("hardstyle_watcher.utils")


def retry_with_backoff(tries=3, delay=1, backoff=2):
    """
    Retry calling the decorated function using an exponential backoff.

    :param tries: Number of times to try before giving up.
    :param delay: Initial delay between retries in seconds.
    :param backoff: Backoff multiplier (e.g. value of 2 will double the delay each retry).
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            local_delay = delay
            for i in range(tries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if i == tries - 1:
                        raise
                    logger.warning(
                        f"Failed to call {func.__name__} with {args} and {kwargs}. Retrying in {local_delay}s"
                    )
                    time.sleep(local_delay)
                    local_delay *= backoff

        return wrapper

    return decorator


@retry_with_backoff(tries=3, delay=1, backoff=2)
def web_request(url: str) -> requests.Response:
    """
    Make a web request to the given URL.

    :param url: URL to make the request to.
    :return: Response object.
    """
    web = requests.Session()
    response = web.get(url)
    return response
