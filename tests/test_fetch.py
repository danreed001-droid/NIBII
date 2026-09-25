"""Pure-function tests for the yfinance data layer - no network required.

Covers the yield*10 scaling fix and the plausibility guards, which exist
because live scaling could not be spot-checked in the environment that wrote
them (Yahoo Finance is blocked by that environment's outbound network
policy). See the module docstring in mtl/fetch.py.
"""
import pytest

from mtl.fetch import scaled_yield, rsi14, sma


def test_x10_tickers_are_divided_by_ten():
    assert scaled_yield(43.3, '^TNX') == 4.33
    assert scaled_yield(21.5, '^FVX') == 2.15
    assert scaled_yield(49.1, '^TYX') == 4.91


def test_irx_is_not_scaled():
    assert scaled_yield(5.3, '^IRX') == 5.3


def test_scaled_yield_rejects_implausible_result():
    with pytest.raises(ValueError):
        scaled_yield(430.0, '^TNX')  # unscaled input passed by mistake -> 43.0%


def test_rsi_and_sma_unaffected_by_fetch_changes():
    closes = [100 + i * 0.1 for i in range(60)]
    assert sma(closes, 50) is not None
    assert 0 <= rsi14(closes) <= 100
