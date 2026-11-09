"""Terminal, CSV and replayable JSONL output for a validated IMU sample."""
import csv
import json
import math
import time

from .imu_formatter import CSV_FIELDS, format_line, to_csv_row


class ImuOutput:
    def __init__(self, csv_path="", print_period_s=1., log=print, *, jsonl_path="", on_sample=None):
        if not math.isfinite(print_period_s) or print_period_s < 0:
            raise ValueError("invalid_print_period")
        self.latest = None
        self._log, self._period, self._last = log, print_period_s, float("-inf")
        self._files = []
        self._csv_writer = self._jsonl = None
        self._on_sample = on_sample
        self._closed = False
        try:
            # Exclusive create prevents accidental loss of a previous recording.
            if csv_path:
                stream = open(csv_path, "x", newline="", buffering=1)
                self._files.append(stream)
                self._csv_writer = csv.writer(stream)
                self._csv_writer.writerow(CSV_FIELDS)
            if jsonl_path:
                self._jsonl = open(jsonl_path, "x", buffering=1)
                self._files.append(self._jsonl)
        except Exception:
            self.close()
            raise

    def handle(self, sample):
        if self._closed:
            raise ValueError("imu_output_closed")
        self.latest = sample
        if self._csv_writer:
            self._csv_writer.writerow(to_csv_row(sample))
        if self._jsonl:
            self._jsonl.write(json.dumps(sample.to_record(), allow_nan=False) + "\n")
        if self._on_sample is not None:
            self._on_sample(sample)
        now = time.monotonic()
        if self._period > 0 and now - self._last >= self._period:
            self._log(format_line(sample))
            self._last = now

    def close(self):
        for stream in self._files:
            stream.close()
        self._files.clear()
        self._closed = True
