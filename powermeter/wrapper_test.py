import unittest
from unittest.mock import patch, MagicMock
from powermeter import VZLogger
from powermeter import AntiWindup


class TestAntiWindupWithVZLogger(unittest.TestCase):

    @patch("requests.Session.get")
    def test_anti_windup_get_powermeter_watts(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "version": "0.8.9",
            "generator": "vzlogger",
            "data": [
                { "uuid": "5", "last": 1776549041735, "interval": -1, "protocol": "sml", "tuples": [ [ 1776549041735, 100] ] },
                { "uuid": "6", "last": 1776549041735, "interval": -1, "protocol": "sml", "tuples": [ [ 1776549041735, 200] ] },
                { "uuid": "7", "last": 1776549041735, "interval": -1, "protocol": "sml", "tuples": [ [ 1776549041735, 300] ] },

                { "uuid": "1", "last": 1776549041735, "interval": -1, "protocol": "sml", "tuples": [ [ 1776549041735, 1] ] },
                { "uuid": "2", "last": 1776549041735, "interval": -1, "protocol": "sml", "tuples": [ [ 1776549041735, 2] ] },
                { "uuid": "3", "last": 1776549041735, "interval": -1, "protocol": "sml", "tuples": [ [ 1776549041735, 3] ] }

            ]
        }
        mock_get.return_value = mock_response

        vzlogger = VZLogger("192.168.1.9", "8088", "5,6,7")
        aw = AntiWindup(vzlogger, 1.5, 0.5, 25, 150, 0.7)
        self.assertEqual(aw.get_powermeter_watts(), [150, 300, 450])
        self.assertEqual([round(ii) for ii in aw.get_powermeter_watts()], [105, 210, 315])

        vzlogger = VZLogger("192.168.1.9", "8088", "1,2,3")
        aw = AntiWindup(vzlogger, 1.5, 0.5, 25, 150, 0.7)
        self.assertEqual(aw.get_powermeter_watts(), [0.5, 1, 1.5])


if __name__ == "__main__":
    unittest.main()
