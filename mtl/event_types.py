"""Event types for the market events page and what usually followed each (data/event_patterns.json, built by
scripts/event_patterns.py). Information only: no trading rule reads this.

Curated events carry the type they were given (data/major_events.json, 'type'). New ones are typed here: a Fed change
by its direction, a big move by its headline (else as a plain big up or down day), a VIX spike, a market-phase
change and a macro signal (mtl/macro_events.py) by their rule, and your own items by the type picked on the form (else
by their words)."""
import re

from mtl.macro_events import TYPES as MACRO_TYPES

# name -> (group, one-line description). Order is the page's order.
TYPES = {
    'Fed hike / hawkish': ('Tightening', 'a rate hike, the last hike of a cycle, tapering or hawkish Fed talk'),
    'Inflation / yields': ('Tightening', 'a hot inflation report or a jump in long-term yields'),
    'Fed cut': ('Policy support', 'a scheduled rate cut or a dovish Fed turn'),
    'Emergency Fed cut': ('Policy support', 'a cut between meetings or a coordinated cut in a crisis'),
    'QE / backstop': ('Policy support', 'bond buying, lending programs and other central-bank backstops'),
    'Rescue / fiscal': ('Policy support', 'bailouts, stimulus, tax laws and deals that avert a crisis'),
    'Trade relief': ('Policy support', 'a tariff pause or truce'),
    'Bank / credit failure': ('Credit shock', 'a bank, broker, fund or big company failing'),
    'Debt crisis / shutdown': ('Credit shock', 'sovereign debt scares, downgrades, Brexit, government shutdowns'),
    'War / terror': ('Outside shock', 'attacks, invasions and military strikes'),
    'Trade war / China': ('Outside shock', 'new tariffs, trade threats and China currency or market shocks'),
    'Pandemic / disaster': ('Outside shock', 'outbreaks, earthquakes and hurricanes'),
    'Oil shock': ('Outside shock', 'oil price collapses and spikes'),
    'Crash / glitch': ('Outside shock', 'crashes and market accidents with no single news cause'),
    'Good news': ('Good news', 'elections the market liked, a vaccine, the AI boom'),
    'Big down day': ('Rule', 'the S&P 500 falling 2.5% or more in a day'),
    'Big up day': ('Rule', 'the S&P 500 rising 2.5% or more in a day'),
    'Fear spike': ('Rule', 'the VIX closing above 30 for the first time in three months'),
    'Correction starts': ('Rule', 'the S&P 500 closing 10% below its high'),
    'Bear market starts': ('Rule', 'the S&P 500 closing 20% below its high'),
    'New bull run': ('Rule', 'the S&P 500 up 20% from a bear-market low'),
    'Back to bull run': ('Rule', 'a new high after a bear market'),
    **{t: ('Rule', d) for t, d in MACRO_TYPES.items()},   # macro signals (mtl/macro_events.py)
    'Turning point': ('Hindsight', 'a market top or bottom, known only afterwards (no pattern)'),
    'Other': ('Other', 'not one of the types above'),
}
GROUP_NAME = {'Outside shock': 'outside shocks (war, trade, pandemic, oil, crashes)',
              'Credit shock': 'credit shocks (bank failures, debt crises, shutdowns)',
              'Policy support': 'policy support (Fed cuts, QE, rescues)',
              'Tightening': 'tightening (Fed hikes, inflation, yields)'}
GROUP_SHORT = {'Outside shock': 'outside shocks', 'Credit shock': 'credit shocks', 'Policy support': 'Fed and rescue moves',
               'Tightening': 'hikes and inflation scares'}
RULE_TYPES = ('Big down day', 'Big up day', 'Fear spike', 'Correction starts', 'Bear market starts', 'New bull run',
              'Back to bull run') + tuple(MACRO_TYPES)
PHASE_TYPE = {'S&P 500 enters a correction (10%+ below its high)': 'Correction starts',
              'S&P 500 enters a bear market (20%+ below its high)': 'Bear market starts',
              'New bull run: S&P 500 up 20% from its bear-market low': 'New bull run',
              'S&P 500 back in a bull run (new high after a bear market)': 'Back to bull run'}

# words in a headline -> type (first match wins)
WORDS = [
    ('Bank / credit failure', r'\b(bank|banks|lender|credit|default|bankrupt\w*|insolven\w*|collapse[sd]?|contagion|hedge fund)\b'),
    ('Debt crisis / shutdown', r'\b(debt ceiling|shutdown|downgrade[sd]?|sovereign|gilt|bond market rout)\b'),
    ('War / terror', r'\b(war|attack\w*|invasion|invades?|strikes? on|missile\w*|terror\w*|military|troops|hormuz|iran|israel|ukraine|russia)\b'),
    ('Trade war / China', r'\b(tariffs?|trade war|trade deal|china|yuan|export controls?)\b'),
    ('Pandemic / disaster', r'\b(pandemic|virus|covid|outbreak|earthquake|hurricane|tsunami)\b'),
    ('Oil shock', r'\b(oil|crude|opec|brent|gasoline)\b'),
    ('Inflation / yields', r'\b(inflation|cpi|ppi|prices? index|yields?|treasur(y|ies)|bond rout)\b'),
    ('Fed hike / hawkish', r'\b(fed|powell|warsh|rate hike|hawkish|fomc)\b'),
]


def classify(e):
    """The type of an event that doesn't have one yet."""
    src, what = e.get('src', ''), e.get('what', '')
    if src == 'auto: Fed':
        return 'Fed cut' if re.search(r'\b(cuts?|lowers?)\b', what, re.I) else 'Fed hike / hawkish'
    if src == 'auto: VIX':
        return 'Fear spike'
    if src == 'auto: signal':
        t = what.split(':', 1)[0]
        return t if t in MACRO_TYPES else 'Other'
    if src == 'auto: market phase':
        return PHASE_TYPE.get(what, 'Other')
    text = what.split(':', 1)[1] if src == 'auto: big move' and ':' in what else what
    for t, rx in WORDS:
        if re.search(rx, text, re.I):
            if t == 'Fed hike / hawkish' and re.search(r'\b(cuts?|lowers?|eases?|dovish)\b', text, re.I):
                return 'Fed cut'
            return t
    if src == 'auto: big move':
        return 'Big down day' if '−' in what.split(':', 1)[0] else 'Big up day'
    return 'Other'


def group(t):
    return TYPES.get(t, ('Other', ''))[0]


def slug(t):
    return re.sub(r'[^a-z0-9]+', '-', t.lower()).strip('-')


# the curated list's types, as set by the Oct 2026 event study
CURATED = {}
for _t, _ds in {
    'Fed hike / hawkish': '2000-05-16 2004-06-30 2006-06-29 2013-05-22 2013-12-18 2015-12-16 2018-10-03 2021-11-30 2022-03-16 '
                          '2022-06-15 2022-08-26 2023-07-26 2024-12-18 2026-08-28 2026-09-16',
    'Fed cut': '2003-06-25 2007-09-18 2008-12-16 2019-01-04 2019-06-04 2019-07-31 2023-12-13 2024-09-18 2025-09-17',
    'Emergency Fed cut': '2001-01-03 2001-04-18 2007-08-17 2008-01-22 2008-10-08 2020-03-03 2020-03-16',
    'QE / backstop': '2008-11-25 2009-03-18 2010-08-27 2010-11-03 2011-09-21 2011-11-30 2012-07-26 2012-09-06 2012-09-13 '
                     '2012-12-12 2015-01-22 2016-01-29 2019-09-17 2020-03-23 2020-04-09 2023-03-13',
    'Bank / credit failure': '2001-12-03 2002-07-22 2007-07-17 2007-08-09 2008-03-14 2008-07-11 2008-09-08 2008-09-15 '
                             '2008-09-16 2008-09-25 2013-03-18 2021-03-26 2021-09-20 2022-09-23 2022-11-11 2023-03-10 2023-03-20 2023-05-01',
    'Rescue / fiscal': '2008-07-13 2008-09-19 2008-10-03 2008-10-13 2009-02-17 2009-03-23 2009-05-07 2010-05-10 2010-07-21 '
                       '2013-01-02 2015-07-13 2017-12-22 2020-03-26 2025-07-04 2023-06-03 2011-08-02',
    'Debt crisis / shutdown': '2008-09-29 2010-04-27 2011-08-04 2011-08-08 2011-11-01 2012-05-07 2013-10-01 2015-06-29 '
                              '2016-06-24 2023-08-02 2025-10-01 2018-12-24',
    'War / terror': '2001-09-17 2003-03-20 2017-08-08 2020-01-03 2022-02-24 2023-10-09 2024-04-15 2025-06-13 2025-06-23',
    'Trade war / China': '2015-08-11 2016-01-07 2018-03-22 2019-05-06 2019-08-01 2019-08-05 2025-03-10 2025-04-03 2025-10-10',
    'Trade relief': '2025-04-09 2025-05-12',
    'Pandemic / disaster': '2005-08-29 2011-03-11 2014-09-30 2020-01-23 2020-02-24 2020-03-12 2021-11-26',
    'Oil shock': '2014-11-28 2016-02-11 2020-03-09 2020-04-20 2026-09-14',
    'Crash / glitch': '2000-04-14 2007-02-27 2010-05-06 2014-10-15 2015-01-15 2015-08-24 2018-02-05 2021-01-27 2024-08-05 2025-01-27',
    'Inflation / yields': '2022-06-10 2022-11-10 2026-10-01 2026-10-14',
    'Good news': '2016-11-09 2020-11-09 2022-11-30 2023-05-24 2024-11-06',
    'Turning point': '2000-03-10 2002-10-09 2007-10-09 2009-03-09 2020-02-19 2022-10-12 2025-02-19',
}.items():
    for _d in _ds.split():
        CURATED[_d] = _t
