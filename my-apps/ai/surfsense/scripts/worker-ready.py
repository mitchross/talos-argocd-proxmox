#!/usr/bin/env python3
"""Readiness requires this Celery worker to answer through its broker."""
import os
import socket


def ready(app, hostname):
    destination = f'celery@{hostname}'
    replies = app.control.inspect(destination=[destination], timeout=3).ping()
    return bool(replies and replies.get(destination, {}).get('ok') == 'pong')


if __name__ == '__main__':
    from celery import Celery
    probe = Celery('readiness', broker=os.environ['CELERY_BROKER_URL'])
    probe.conf.update(broker_connection_timeout=2, broker_connection_retry=False,
                      broker_connection_max_retries=0, task_publish_retry=False)
    try:
        result = ready(probe, socket.gethostname())
    except Exception:
        result = False
    raise SystemExit(0 if result else 1)
