"""Sends exam events from the server to the SDN controller. Owner: Member C.

Environment overrides (handy for tests; no need to edit config.json):
  EXAM_EVENT_URL=http://127.0.0.1:8081/exam/event   send events to this URL instead of the one in config.json
  EXAM_NOTIFY=0                                      do not send events at all
"""
import datetime
import json
import os
import threading
import time
import urllib.request

_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.json")
_COOLDOWN_SECONDS = 30      # after a failure, skip sending for this long so a missing endpoint cannot slow the exam
_lock = threading.Lock()
_skip_until = 0.0


def _load_config():
    with open(_CONFIG) as f:
        return json.load(f)


def _event_url():
    override = os.environ.get("EXAM_EVENT_URL")
    if override:
        return override
    cfg = _load_config()
    return "http://{}:{}{}".format(cfg["controller_ip"], cfg["controller_rest_port"], cfg.get("event_path", "/exam/event"))


def notify_controller(event, data=None, timeout=0.5):
    """POST an event to the controller. Never raises and never holds the exam up for long:
    the first failure costs at most `timeout` seconds, then sending is skipped for _COOLDOWN_SECONDS.
    Returns True on success, False otherwise."""
    global _skip_until
    if os.environ.get("EXAM_NOTIFY") == "0" or time.time() < _skip_until:
        return False
    try:
        payload = {"event": event,
                   "timestamp": datetime.datetime.now().isoformat(timespec="milliseconds")}
        payload.update(data or {})
        req = urllib.request.Request(_event_url(), data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        with _lock:
            first = time.time() >= _skip_until
            _skip_until = time.time() + _COOLDOWN_SECONDS
        if first:
            print("[notifier] could not send '{}': {} (pausing notifications for {}s)".format(event, e, _COOLDOWN_SECONDS))
        return False