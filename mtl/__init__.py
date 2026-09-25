"""Market Tape Ledger - deterministic engine.

Everything in this package is pure: same inputs, same outputs, no network,
no clock, no judgment. The judgment layer (which facts, which side, which
reason) lives outside and arrives as votes.json.
"""
__version__ = "1.0.0"
