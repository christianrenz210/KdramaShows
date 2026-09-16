import os

# Single worker: the Playwright daemon and its in-memory caches are
# per-process globals in app.py, so extra workers would each spawn their
# own Chromium instance (wasting memory) without sharing cached stream URLs.
workers = 1
worker_class = 'gthread'
threads = 4

# Chromium cold start (~15-30s) plus the kisskh scrape (multiple page
# navigations/polls) can take well over gunicorn's 30s default, which was
# killing the worker mid-request and surfacing as "No stream URL returned
# from server".
timeout = 180
graceful_timeout = 30


def post_fork(server, worker):
    """Warm up the Playwright daemon (and catalog builder) right after the
    worker boots, instead of lazily on the first stream request. Under
    `gunicorn app:app` the app module's `if __name__ == '__main__'` block
    never runs, so without this hook the daemon only ever cold-starts
    on-demand inside a request, racing the request timeout."""
    try:
        from app import _start_background_services
        _start_background_services()
    except Exception as e:
        server.log.error('post_fork daemon warm-up failed: %s', e)
