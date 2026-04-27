from .base import Powermeter
import time
import threading
from config.logger import logger
import statistics
from collections import deque

class PowermeterWrapper(Powermeter):
    def __init__(self, wrapped_powermeter : Powermeter):
        self._wrapped_powermeter = wrapped_powermeter

    def get_wrapped_powermeter_watts(self):
        return self._wrapped_powermeter.get_powermeter_watts()

class LowPassFilter(PowermeterWrapper):
    def __init__(self, wrapped_powermeter, slope_on, slope_off, max_filter_time, slope_on_max_add):
        super(LowPassFilter, self).__init__(wrapped_powermeter)
        self._filtering = False
        self._last_power = [0, 0, 0]
        self._last_spike_time = 0
        self._slope_on = slope_on
        self._slope_on_max = slope_on + slope_on_max_add
        self._slope_off = slope_off
        self._max_filter_time = max_filter_time
        self._lock = threading.Lock()
    
    def get_powermeter_watts(self):
        with self._lock:
            powers = self.get_wrapped_powermeter_watts() 
            total = sum(powers)
            last_total = sum(self._last_power)
            diff = abs(total - last_total)
            if self._filtering:
                if diff > self._slope_off:
                    if (time.perf_counter() - self._last_spike_time <= self._max_filter_time) and diff < self._slope_on_max:
                        powers = self._last_power
                        logger.info(f"Filtering")
                    else:
                        logger.info(f"Stop filtering")
                        self._filtering = False
                else:
                    logger.info(f"Stop filtering")
                    self._filtering = False
            else:
                if diff > self._slope_on and diff < self._slope_on_max:
                    logger.info(f"Start filtering")
                    self._filtering = True
                    self._last_spike_time = time.perf_counter()
                    powers = self._last_power
            self._last_power = powers
            return powers


class DeadbandFilter(PowermeterWrapper):
    def __init__(self, wrapped_powermeter, threshold):
        super(DeadbandFilter, self).__init__(wrapped_powermeter)
        self._threshold = threshold

    def get_powermeter_watts(self):
        powers = self.get_wrapped_powermeter_watts()
        if abs(sum(powers)) <= self._threshold: powers = [0,0,0]
        return powers


class AntiWindup(PowermeterWrapper):
    def __init__(self, wrapped_powermeter, fast, slow, threshold_low, threshold_high, damping):
        super(AntiWindup, self).__init__(wrapped_powermeter)
        self._last_powers = [0, 0, 0]
        self._fast = fast
        self._slow = slow
        self._threshold_low = threshold_low
        self._threshold_high = threshold_high
        self._damping = damping
        self._factor = slow
        self._lock = threading.Lock()

    def get_powermeter_watts(self):
        with self._lock:
            powers = self.get_wrapped_powermeter_watts() 

            total = abs(sum(powers))
            if self._last_powers != powers:
                self._last_powers = powers
                if total > self._threshold_low:
                    diff = min(total, self._threshold_high) - self._threshold_low
                    self._factor = ((diff/(self._threshold_high-self._threshold_low)) * (self._fast -self._slow)) + self._slow
                else:
                    self._factor = self._slow
            else:
                self._factor *= self._damping
            powers = [p*self._factor for p in powers]
            logger.info(round(sum(powers), 1))
            return powers

"""Hampel outlier-rejection powermeter wrapper."""

class HampelFilter(PowermeterWrapper):
    """Rolling-median outlier filter for sum-of-phases power readings.

    Maintains a rolling window of the most recent ``window`` totals. When the
    next total lies more than ``n_sigma * 1.4826 * MAD`` away from the window
    median (with a floor of ``min_threshold`` watts to handle the constant-
    signal MAD=0 degenerate case), the sample is treated as an outlier: the
    reported total is replaced by the median and per-phase values are
    redistributed proportionally (equal split when ``|raw_total|`` is near
    zero). The window entry itself is mutated to the median so a single spike
    does not poison future detections — this is the canonical Hampel
    identifier formulation used in control literature.

    Operates on the sum of phases, mirroring :class:`SmoothedPowermeter`.
    A phase-cancelling outlier (e.g. +1000 W on L1 and -1000 W on L2) is
    therefore invisible to this filter; that is acceptable because every
    downstream wrapper (EMA, deadband, PID) also operates on sum-of-phases.
    """

    MAD_SCALE = 1.4826

    def __init__(
        self,
        wrapped_powermeter: Powermeter,
        window: int,
        n_sigma: float = 3.0,
        min_threshold: float = 0.0,
    ) -> None:
        super(HampelFilter, self).__init__(wrapped_powermeter)
        if window < 1:
            raise ValueError(f"Hampel window must be >= 1, got {window}")
        if n_sigma < 0:
            raise ValueError(f"Hampel n_sigma must be >= 0, got {n_sigma}")
        if min_threshold < 0:
            raise ValueError(f"Hampel min_threshold must be >= 0, got {min_threshold}")
        self._window: deque[float] = deque(maxlen=window)
        self._window_size = window
        self._n_sigma = n_sigma
        self._min_threshold = min_threshold

    #def reset(self) -> None:
    #    super().reset()
    #    logger.debug("HampelPowermeter: reset (window size=%d)", len(self._window))
    #    self._window.clear()

    def get_powermeter_watts(self) -> list[float]:
        raw_values = self.get_wrapped_powermeter_watts()
        if not raw_values:
            return []

        raw_total = sum(raw_values)
        #if len(self._window) > 0:
        #    if self._window[-1] != raw_total:
        #        self._window.append(raw_total)
        #else:
        self._window.append(raw_total)
                

        if len(self._window) < self._window_size:
            return list(raw_values)

        median = statistics.median(self._window)
        mad = statistics.median(abs(x - median) for x in self._window)
        threshold = max(self._n_sigma * self.MAD_SCALE * mad, self._min_threshold)

        if threshold <= 0 or abs(raw_total - median) <= threshold:
            return list(raw_values)

        #self._window[-1] = median
        logger.info(
            "HampelFilter: outlier rejected raw=%.2f median=%.2f threshold=%.2f",
            raw_total,
            median,
            threshold,
        )

        if abs(raw_total) < 1e-9:
            return [median / len(raw_values)] * len(raw_values)
        ratio = median / raw_total
        return [v * ratio for v in raw_values]
