#!/usr/bin/env python3
"""Explicit simulation clock normalization using the existing tested converter.

Receipt alignment is provisional; this process uses FCU references and /clock,
never simulator truth. The Monitor helper is mounted read-only by the runner.
"""
import sys
sys.path.insert(0, '/clock-tools')
import live_clock

live_clock.ALIGNED_POSE = '/navigation/mapping_odometry'
if __name__ == '__main__':
    live_clock.main()
