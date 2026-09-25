"""Pure-function tests for the yfinance data layer - no network required.

The old yield*10 scaling assumption was live-verified wrong (2026-09-25,
via GitHub Actions) and removed - see mtl/fetch.py's module docstring for
the real values that disproved it. These tests now cover the corrected
pass-through behavior and the plausibility guard that would have caught
the original bug if it had ever run against real data.
"""
import pytest

from mtl.fetch import scaled_yield, rsi14, sma


def test_yields_pass_through_unscaled():
    # live-verified 2026-09-25: ^TNX printed 5.1620 directly as the percent
    # yield, not 51.620 - Yahoo does not scale these by 10
    assert scaled_yield(5.162, '^TNX') == 5.162
    assert scaled_yield(5.025, '^FVX') == 5.025
    assert scaled_yield(5.461, '^TYX') == 5.461
    assert scaled_yield(4.068, '^IRX') == 4.068


def test_scaled_yield_rejects_implausible_result():
    # this is exactly the bug the old *10 divide would have caused: a real
    # ~43% misread as plausible, or a real yield divided down to ~0.5% -
    # the guard exists so a future format change fails loudly instead of
    # publishing a silently wrong number
    with pytest.raises(ValueError):
        scaled_yield(430.0, '^TNX')
    with pytest.raises(ValueError):
        scaled_yield(-1.0, '^TNX')


def test_rsi_and_sma_unaffected_by_fetch_changes():
    closes = [100 + i * 0.1 for i in range(60)]
    assert sma(closes, 50) is not None
    assert 0 <= rsi14(closes) <= 100
