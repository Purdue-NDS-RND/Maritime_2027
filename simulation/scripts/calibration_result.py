"""Qualification shared by calibration execution and reporting."""
import math

def restoration_verified(result):
    original, restored = result.get('original', {}), result.get('restored', {})
    return (set(original) == set(restored)
            and all(math.isfinite(restored[name]) and abs(restored[name] - value) <= max(1e-4, abs(value) * 1e-5)
                    for name, value in original.items())
            and not result.get('restoration_error'))


def successful(result):
    return (result.get('boat_outcome', {}).get('state') == 'complete'
            and not result.get('error') and not result.get('cleanup_error')
            and restoration_verified(result))
