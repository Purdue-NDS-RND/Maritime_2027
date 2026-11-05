"""Decide where cleaned IMU data goes.

This is the ONLY file that knows about destinations (terminal, CSV, memory).
To add a new destination later (publish to another topic, send over the
network, write a database, ...), add it here; the listener and formatter
don't change.

No ROS imports, so it can be tested without ROS running.
"""

import csv
import time

from log.imu_formatter import CSV_FIELDS, format_line, to_csv_row


class ImuOutput:
    def __init__(self, csv_path="", print_period_s=1.0, log=print):
        """
        csv_path        -- file to save every sample to ("" = don't save)
        print_period_s  -- print at most once per this many seconds (0 = never print)
        log             -- function used to print a line (print, or a ROS logger)
        """
        self.latest = None  # most recent sample, for other code to read

        self._log = log
        self._print_period_s = print_period_s
        self._last_print_time = float("-inf")

        self._csv_file = None
        self._csv_writer = None
        if csv_path:
            # buffering=1 -> each line is written to disk right away
            self._csv_file = open(csv_path, "w", newline="", buffering=1)
            self._csv_writer = csv.writer(self._csv_file)
            self._csv_writer.writerow(CSV_FIELDS)
            self._log(f"Logging IMU data to {csv_path}")

    def handle(self, sample):
        """Send one cleaned ImuSample to every enabled destination."""
        self.latest = sample
        self._write_csv(sample)
        self._maybe_print(sample)

    # ---- individual destinations ------------------------------------------

    def _write_csv(self, sample):
        if self._csv_writer:
            self._csv_writer.writerow(to_csv_row(sample))

    def _maybe_print(self, sample):
        # The IMU sends ~20 messages/sec, so only print once per period.
        if self._print_period_s <= 0:
            return
        now = time.monotonic()
        if now - self._last_print_time >= self._print_period_s:
            self._log(format_line(sample))
            self._last_print_time = now

    def close(self):
        if self._csv_file:
            self._csv_file.close()
            self._csv_file = None
