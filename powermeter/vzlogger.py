from .base import Powermeter
import requests


class VZLogger(Powermeter):
    def __init__(self, ip: str, port: str, uuid: str):
        self.ip = ip
        self.port = port
        self.uuids = dict(zip([u.strip() for u in uuid.split(",")], [0,1,2]))
        self.session = requests.Session()

    def get_json(self):
        url = f"http://{self.ip}:{self.port}"
        return self.session.get(url, timeout=10).json()

    def get_powermeter_watts(self):
        powers = [0, 0, 0]
        for item in self.get_json()["data"]:
            uuid = item['uuid']
            pos = self.uuids.get(uuid, None)
            if pos != None:
                powers[pos] = item['tuples'][0][1]
        return powers