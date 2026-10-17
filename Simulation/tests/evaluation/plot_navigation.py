#!/usr/bin/env python3
"""Render an independent navigation trajectory result for visual inspection."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result', type=Path)
    args = parser.parse_args()
    result = json.loads(args.result.read_text())
    fig, ax = plt.subplots(figsize=(13, 4))
    samples = result['samples']
    ax.plot([p[0] for p in samples], [p[1] for p in samples], color='navy', label='Actual boat path')
    for name, check in result['checks'].items():
        if 'position' not in check:
            continue
        x, y = check['position']
        ax.scatter(x, y, color='red' if 'red' in name else 'green', s=80)
        ax.text(x, y+.3, name.replace('slalom_', ''), ha='center', fontsize=8)
    ax.set_aspect('equal')
    ax.set(xlabel='World X (m)', ylabel='World Y (m)', title='Dual RGB gate and slalom: '+('PASS' if result['passed'] else 'FAIL'))
    ax.grid(alpha=.3)
    ax.legend(loc='upper left')
    fig.tight_layout()
    fig.savefig(args.result.with_suffix('.png'), dpi=160)


if __name__ == '__main__':
    main()
