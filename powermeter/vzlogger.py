from .base import Powermeter
import requests
import http.server
import time
import json
import queue
import threading
import time
from config.logger import logger


def getPowerFromVZLoggerData(data, uuids):
    powers = [0, 0, 0]
    for item in data:
        uuid = item['uuid']
        pos = uuids.get(uuid, None)
        if pos is not None:
            powers[pos] = item['tuples'][0][1]
    return powers

class VZLogger(Powermeter):
    def __init__(self, uuids: str, ip: str, port: int):
        self.ip = ip
        self.port = port
        self.url = f"http://{self.ip}:{self.port}"
        self.uuids = dict(zip([u.strip() for u in uuids.split(",")], [0,1,2]))
        self.session = requests.Session()

    def get_json(self):
        return self.session.get(self.url, timeout=10).json()

    def get_powermeter_watts(self):
        data = self.get_json()["data"]
        return getPowerFromVZLoggerData(data, self.uuids)

class VZLoggerListener(Powermeter):
    def __init__(self, uuids : str, timeout : float, ip: str = "0.0.0.0", port: int = 8088):

        class VZLogger_DataHandler(http.server.BaseHTTPRequestHandler):
            vzlogger_listener = self

            def _set_headers(self):
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()

            def log_message(format, *args):
                pass

            def do_POST(self):
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                self._set_headers()
                decoded_data = post_data.decode()
                json_data = json.loads(decoded_data)
                data = json_data['data']
                if len(data) > 6:
                    logger.info("Push from VZLogger received!")
                    self.vzlogger_listener.queue.put(data)

        logger.info(f"Created VZLogger Listener using timeout={timeout}, uuids = {uuids}")
        self.server = http.server.HTTPServer((ip, port), VZLogger_DataHandler)
        self._http_thread = threading.Thread(target=self.server.serve_forever)
        self._http_thread.start()
        logger.info(f"Started HTTP Server on {ip}:{port}")

        self._uuids = dict(zip([u.strip() for u in uuids.split(",")], [0,1,2]))
        self._timeout = timeout
        self._last_get_time = time.perf_counter()
        self._last_value = [0, 0, 0]
        self.queue = queue.Queue(maxsize=2)

    def get_powermeter_watts(self):
        try:    
            data = self.queue.get(timeout = self._timeout)
            now = time.perf_counter()
            diff = now - self._last_get_time
            self._last_get_time = now
            powers = getPowerFromVZLoggerData(data, self._uuids)
            self._last_value = powers
            logger.info(f"Power after push {powers} ({round(diff, 2)} s)")
            return powers
        except queue.Empty:
            now = time.perf_counter()
            diff = now - self._last_get_time
            self._last_get_time = now
            logger.info(f"Power after timeout (no push received): {self._last_value} ({round(diff, 2)} s)")
            return self._last_value



