"""Shared Earth-rotation data policy for a planning app, not precision pointing.

Calculations are offline and may use stale predictions, with UI/report notice.
Startup checks cached data and refreshes stale predictions once per process.
Updates use Astropy's official IERS sources with bounded timeouts.
https://docs.astropy.org/en/stable/utils/iers.html#working-offline
"""
from contextlib import contextmanager
from threading import RLock
from astropy.time import Time
from astropy.utils import data, iers

_lock = RLock()
_table = None
_startup_checked = False


def current_table():
    global _table
    with _lock:
        if _table is None:
            with iers.conf.set_temp('auto_download', False):
                _table = iers.IERS_Auto.open()
        return _table


def initialize_data(progress=None):
    """Reuse newer cached IERS data and check freshness once per app process.

    Return whether callers should invalidate calculations using the old table.
    Failed startup checks are not retried on every Streamlit widget rerun.
    The optional progress callback receives a completed stage fraction and label.
    """
    global _table, _startup_checked
    with _lock:
        if _startup_checked:
            return False
        _startup_checked = True
        if progress:
            progress(0.0, "Loading local Earth-rotation data…")
        previous = current_table()
        if progress:
            progress(1 / 3, "Checking saved Earth-rotation updates…")
        urls = (iers.conf.iers_auto_url, iers.conf.iers_auto_url_mirror)
        try:
            cached = data.cache_contents()
        except OSError:
            cached = {}
        for url in urls:
            if url not in cached:
                continue
            try:
                candidate = iers.IERS_Auto.read(file=cached[url])
                if candidate.meta['predictive_mjd'] > _table.meta['predictive_mjd']:
                    _table = candidate
            except (OSError, ValueError, KeyError):
                # An unreadable cache must not prevent offline planning.
                continue
        if progress:
            progress(2 / 3, "Checking for Earth-rotation updates…")
        refreshed, _ = refresh_data()
        if progress:
            progress(1.0, "Earth-rotation data ready" if refreshed else "Using local Earth-rotation data")
        return refreshed or _table is not previous


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
                'Restart the app when online to check for updates, or use dates within its coverage; this app is for planning, not precision pointing.')
    predictive = table.meta.get('predictive_mjd')
    if predictive is not None and upper >= float(predictive) and Time.now().mjd-float(predictive) > 30:
        return ('Earth-rotation predictions are more than 30 days old. Planning continues with reduced accuracy; '
                'restart the app when online to check for updates. This app is for planning, not precision pointing.')
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
                # Work on a copy so a failed refresh cannot mutate the fallback.
                candidate = previous.copy()
                # Astropy 8 defers downloading until a conversion needs new values.
                candidate.ut1_utc(Time.now())
            _table = candidate
        except (OSError, ValueError, RuntimeError) as exc:
            _table = previous
            return False, 'Could not refresh Earth-rotation data; local data remain available. '+str(exc)
        return True, 'Earth-rotation data checked against the current epoch.'
