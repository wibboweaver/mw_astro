"""Shared Earth-rotation data policy for a planning app, not precision pointing.

Calculations are offline and may use stale predictions, with UI/report notice.
A deliberate refresh uses Astropy's official IERS sources with bounded timeouts.
https://docs.astropy.org/en/stable/utils/iers.html#working-offline
"""
from contextlib import contextmanager
from threading import RLock
from astropy.time import Time
from astropy.utils import iers

_lock = RLock()
_table = None


def current_table():
    global _table
    with _lock:
        if _table is None:
            with iers.conf.set_temp('auto_download', False):
                _table = iers.IERS_Auto.open()
        return _table


@contextmanager
def planning_earth_rotation():
    """Scope tolerant IERS configuration to calculations and restore it afterwards.

    Lock because Astropy's configuration and science state are process-global.
    Explicit table selection retains a refreshed table even with downloads off.
    """
    with _lock, iers.conf.set_temp('auto_download', False), \
            iers.conf.set_temp('auto_max_age', None), \
            iers.conf.set_temp('iers_degraded_accuracy', 'warn'), \
            iers.earth_orientation_table.set(current_table()):
        yield


def data_notice(start, end=None):
    """Describe stale predictions or dates outside the table without implying precision."""
    table = current_table()
    first, last = Time(start).mjd, Time(end or start).mjd
    lower, upper = sorted((first, last))
    if lower < float(table['MJD'][0].value) or upper > float(table['MJD'][-1].value):
        return ('The selected dates extend beyond the available Earth-rotation data. '
                'Altitude, Moon and event-time estimates have reduced accuracy. '
                'Refresh the data or use dates within its coverage; this app is for planning, not precision pointing.')
    predictive = table.meta.get('predictive_mjd')
    if predictive is not None and upper >= float(predictive) and Time.now().mjd-float(predictive) > 30:
        return ('Earth-rotation predictions are more than 30 days old. Planning continues with reduced accuracy; '
                'refresh the data when online. This app is for planning, not precision pointing.')
    return None


def refresh_data():
    """Refresh for the current epoch; failure retains usable local planning data."""
    global _table
    with _lock:
        previous = current_table()
        try:
            with iers.conf.set_temp('auto_download', True), \
                    iers.conf.set_temp('auto_max_age', 30), \
                    iers.conf.set_temp('remote_timeout', 4):
                candidate = iers.IERS_Auto.open()
                # Astropy 8 defers downloading until a conversion needs new values.
                candidate.ut1_utc(Time.now())
            _table = candidate
        except (OSError, ValueError, RuntimeError) as exc:
            _table = previous
            return False, 'Could not refresh Earth-rotation data; local data remain available. '+str(exc)
        return True, 'Earth-rotation data checked against the current epoch.'
