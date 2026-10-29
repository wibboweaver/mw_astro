"""Astronomical darkness: geometric solar centre below -18 degrees."""
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import astropy.units as u
from astropy.coordinates import AltAz, EarthLocation, get_sun
from astropy.time import Time
from astropy.utils import iers


@dataclass(frozen=True)
class NightInterval:
    start: datetime
    end: datetime
    start_is_event: bool = True
    end_is_event: bool = True


def solar_altitudes(times, latitude, longitude, height=0):
    location = EarthLocation.from_geodetic(longitude*u.deg, latitude*u.deg, height*u.m)
    moments = Time(times)
    with iers.conf.set_temp('auto_download', False):
        return get_sun(moments).transform_to(AltAz(obstime=moments, location=location, pressure=0*u.hPa)).alt.deg


def night_intervals(start, end, latitude, longitude, height=0):
    """Return dark intervals clipped to an aware UTC range; refine events to 1 s."""
    if start.tzinfo is None or end.tzinfo is None or start.utcoffset() is None or end.utcoffset() is None:
        raise ValueError('Night calculation requires timezone-aware times.')
    start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    if end <= start:
        raise ValueError('End must follow start.')
    offsets = np.append(np.arange(0, (end-start).total_seconds(), 120), (end-start).total_seconds())
    times = [start+timedelta(seconds=float(seconds)) for seconds in offsets]
    altitudes = solar_altitudes(times, latitude, longitude, height)
    dark = np.asarray(altitudes) < -18
    intervals = []
    opened = (start, False) if dark[0] else None
    for index in np.flatnonzero(dark[:-1] != dark[1:]):
        left, right = times[index], times[index+1]
        left_dark = bool(dark[index])
        while (right-left).total_seconds() > 1:
            middle = left+(right-left)/2
            middle_dark = float(solar_altitudes([middle], latitude, longitude, height)[0]) < -18
            if middle_dark == left_dark:
                left = middle
            else:
                right = middle
        crossing = left+(right-left)/2
        if not left_dark:
            opened = (crossing, True)
        else:
            intervals.append(NightInterval(opened[0], crossing, opened[1], True))
            opened = None
    if opened is not None:
        intervals.append(NightInterval(opened[0], end, opened[1], False))
    return tuple(intervals)


def night_for_chart(evening_date, timezone_name, chart_start, chart_end, latitude, longitude, height=0):
    """Cover the plotted window plus the selected evening's noon-to-noon night."""
    zone = ZoneInfo(timezone_name)
    noon = datetime.combine(evening_date, time(12), tzinfo=zone).astimezone(timezone.utc)
    next_noon = datetime.combine(evening_date+timedelta(days=1), time(12), tzinfo=zone).astimezone(timezone.utc)
    return night_intervals(min(noon,chart_start.astimezone(timezone.utc)),
                           max(next_noon,chart_end.astimezone(timezone.utc)), latitude,longitude,height)


def night_text(intervals, evening_date, timezone_name):
    zone = ZoneInfo(timezone_name)
    noon = datetime.combine(evening_date,time(12),tzinfo=zone).astimezone(timezone.utc)
    next_noon = datetime.combine(evening_date+timedelta(days=1),time(12),tzinfo=zone).astimezone(timezone.utc)
    evening = [interval for interval in intervals if interval.end > noon and interval.start < next_noon]
    if not evening:
        return 'No astronomical night on this date.'
    interval = evening[0]
    if interval.start <= noon and interval.end >= next_noon:
        return f'Astronomical night throughout the noon-to-noon period ({timezone_name}); no dusk/dawn crossing.'
    beginning = interval.start.astimezone(zone).strftime('%H:%M') if interval.start_is_event and interval.start >= noon else 'before local noon'
    ending = interval.end.astimezone(zone).strftime('%H:%M') if interval.end_is_event and interval.end <= next_noon else 'after next local noon'
    return f'Astronomical night ({timezone_name})  \nStart: {beginning}  \nEnd: {ending}'
