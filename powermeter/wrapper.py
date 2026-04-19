from .base import Powermeter
import time
import threading
from config.logger import logger
import collections

class LowPassFilter(Powermeter):
    def __init__(self, powermeter, slope_on, slope_off, max_filter_time):
        self._powermeter = powermeter
        self._filtering = False
        self._last_power = [0, 0, 0]
        self._last_spike_time = 0
        self._slope_on = slope_on
        self._slope_off = slope_off
        self._max_filter_time = max_filter_time
        self._lock = threading.Lock()
    
    def get_powermeter_watts(self):
        with self._lock:
            powers = self._powermeter.get_powermeter_watts() 
            total = sum(powers)
            last_total = sum(self._last_power)
            diff = abs(total - last_total)
            if self._filtering:
                if diff > self._slope_off: 
                    if time.perf_counter() - self._last_spike_time <= self._max_filter_time:
                        powers = self._last_power
                        logger.info(f"Filtering")
                    else:
                        logger.info(f"Stop filtering")
                        self._filtering = False
                else:
                    logger.info(f"Stop filtering")
                    self._filtering = False
            else:
                if diff > self._slope_on:
                    logger.info(f"Start filtering")
                    self._filtering = True
                    self._last_spike_time = time.perf_counter()
                    powers = self._last_power
            self._last_power = powers
            return powers


class AntiWindup(Powermeter):
    def __init__(self, powermeter, fast, slow, threshold_low, threshold_high, damping):
        self._powermeter = powermeter
        self._deque = collections.deque([[0, 0, 0]], maxlen=10)
        self._fast = fast
        self._slow = slow
        self._threshold_low = threshold_low
        self._threshold_high = threshold_high
        self._damping = damping
        self._factor = slow
        self._lock = threading.Lock()

    def get_powermeter_watts(self):
        with self._lock:
            powers = self._powermeter.get_powermeter_watts() 
            total = abs(sum(powers))
            # stdev-based offset
            if self._deque[-1] != powers:
                self._deque.append(powers)
                if total > self._threshold_low:
                    diff = min(total, self._threshold_high) - self._threshold_low
                    self._factor = ((diff/(self._threshold_high-self._threshold_low)) * (self._fast -self._slow)) + self._slow
                else:
                    self._factor = self._slow
            else:
                self._factor *= self._damping
            powers = [float(p)*(self._factor) for p in powers]
            logger.info(sum(powers))
            return powers