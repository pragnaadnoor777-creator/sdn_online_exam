"""Sends exam events from the server to the SDN controller. Owner: Member C."""
import datetime
import json
import os
import urllib.request

_CONFIG = os.path.join(os.path.dirname(__file__), "..", "config.json")

def _load_config():
    with open(_CONFIG) as f:
        return json.load(f)

def notify_controller(event, data=None, timeout=1.0):
    """POST an event to the controller. Never raises: the exam must not crash
    if the controller is unreachable. Returns True on success."""
    try:
        cfg = _load_config()
        url = "http://{}:{}/exam/event".format(
            cfg["controller_ip"], cfg["controller_rest_port"])
        payload = {
            "event": event,
            "timestamp": datetime.datetime.now().isoformat(timespec="milliseconds"),
        }
        payload.update(data or {})
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        print("[notifier] could not send '{}': {}".format(event, e))
        return False