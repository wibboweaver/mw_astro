"""Compact capture, finish-time and review summaries for an enabled sequence."""
from dataclasses import dataclass
from datetime import timedelta, timezone
import math
import re

from sequence_analyser import ADAPTIVE, class_name, number


def clock_duration(seconds):
    """Elapsed duration, retaining seconds when HH:MM would hide short actions."""
    seconds = max(0, math.ceil(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{hours:02}:{minutes:02}' + (f':{seconds:02}' if seconds else '')


def format_timing(value):
    if value.lower() == 'variable':
        return '--:-- variable'
    matches = re.findall(r'(\d+(?:\.\d+)?(?:e[+-]?\d+)?)\s+(h|min|s)\b', value)
    seconds = sum(float(amount) * {'h': 3600, 'min': 60, 's': 1}[unit] for amount, unit in matches)
    result = clock_duration(seconds)
    variable = 'variable' in value.lower() or '≥' in value
    if variable:
        result += ' variable'
    elif '≈' in value:
        result += ' estimated'
    if 'per activation each' in value:
        result += ' per activation each'
    elif 'per activation' in value:
        result += ' per activation'
    elif 'per pass' in value:
        result += ' per pass'
    return result


def heading(name, active, timing):
    return f'{name}: [{"Enabled" if active else "Disabled"}] Time: {format_timing(timing)}'


@dataclass
class Capture:
    target: str
    filter: str
    frame_type: str
    frames: int | None
    exposure: float | None
    conditional: bool = False

    @property
    def seconds(self):
        if self.frames is None or self.exposure is None or self.conditional:
            return None
        return self.frames * self.exposure

    def row(self):
        return {
            'Target': self.target, 'Filter': self.filter, 'Frame type': self.frame_type,
            'Frames': str(self.frames) if self.frames is not None else 'Variable',
            'Exposure/frame': f'{self.exposure:g} s' if self.exposure is not None else 'Not specified / trained',
            'Exposure time': clock_duration(self.seconds) if self.seconds is not None else '--:-- variable',
            'Note': 'Conditional trigger capture; not scheduled' if self.conditional else '',
        }


def target_for(plan, node, frame_type):
    for parent_key in reversed(node.parents):
        target = plan.resolve(plan.nodes[parent_key].data.get('Target'))
        if isinstance(target, dict) and target.get('TargetName'):
            return str(target['TargetName'])
    return 'Calibration' if frame_type != 'LIGHT' else 'Unspecified'


def filter_for(plan, node):
    branch_key = node.key
    for parent_key in reversed(node.parents):
        parent = plan.nodes[parent_key]
        earlier = []
        for sibling in plan.sections(parent)['Items']:
            if sibling.key == branch_key:
                break
            earlier.append(sibling)
        for sibling in reversed(earlier):
            if class_name(sibling.data) != 'SwitchFilter' or not plan.state(sibling):
                continue
            selected = plan.resolve(sibling.data.get('Filter'))
            if isinstance(selected, dict):
                name = selected.get('Name', selected.get('_name'))
                if name:
                    return str(name)
        branch_key = parent_key
    return 'Unspecified'


def capture_summary(plan):
    grouped = {}
    for node in plan.nodes.values():
        if class_name(node.data) not in {'TakeExposure', 'TakeSubframeExposure'} or not plan.state(node):
            continue
        parents = [plan.nodes[key] for key in node.parents]
        frame_type = str(node.data.get('ImageType') or 'LIGHT').upper()
        if any(class_name(parent.data) == 'TrainedDarkFlatExposure' for parent in parents):
            frame_type = 'DARK FLAT'
        exposure = number(node.data, 'ExposureTime')
        if any(class_name(parent.data) in ADAPTIVE for parent in parents):
            # Internal exposures in adaptive/trained instructions are placeholders,
            # even if an old numeric value remains in the saved sequence.
            exposure = None
        frames = 1
        conditional = any(parent.role == 'Trigger' for parent in parents)
        for parent in parents:
            count = 1 if class_name(parent.data) in ADAPTIVE else plan.repetitions(parent.data)
            if count is None:
                frames = None
                break
            frames *= int(count)
        if frames == 0:
            continue
        target, selected_filter = target_for(plan, node, frame_type), filter_for(plan, node)
        key = (target, selected_filter, frame_type, exposure, conditional)
        if key not in grouped:
            grouped[key] = Capture(target, selected_filter, frame_type, frames, exposure, conditional)
        else:
            previous = grouped[key]
            previous.frames = None if previous.frames is None or frames is None else previous.frames + frames
    return list(grouped.values())


def capture_totals(captures, lights=True):
    selected = [capture for capture in captures if (capture.frame_type == 'LIGHT') == lights and not capture.conditional]
    seconds = sum(capture.seconds or 0 for capture in selected)
    variable = any(capture.seconds is None for capture in selected)
    return clock_duration(seconds) + (' variable' if variable else '')


def projected_finish(plan, start):
    """Add elapsed time in UTC so crossing a clock change stays correct."""
    seconds, variable = plan.projection
    if seconds == 0 and variable:
        return None, variable
    end = (start.astimezone(timezone.utc) + timedelta(seconds=seconds)).astimezone(start.tzinfo)
    return end, variable


def render_insights(plan):
    import pandas as pd
    import streamlit as st

    captures = capture_summary(plan)
    with st.expander('Capture summary'):
        if captures:
            st.dataframe(pd.DataFrame([capture.row() for capture in captures]), hide_index=True, width='stretch')
            st.caption(f'Lights: {capture_totals(captures)} · Calibration: {capture_totals(captures, lights=False)}. '
                       'Exposure time only; downloads, setup and other actions are excluded. '
                       'Conditional trigger captures are shown separately from scheduled totals.')
        else:
            st.caption('No enabled image captures.')


def session_start_controls():
    from datetime import datetime, date, time
    from zoneinfo import ZoneInfo
    import streamlit as st
    from configuration import load_settings

    try:
        settings = load_settings()
        zone = ZoneInfo(settings.timezone)
        evening = date.fromisoformat(settings.evening_date) if settings.evening_date else datetime.now(zone).date()
        beginning = time(settings.start_hour, settings.start_minute)
    except (OSError, ValueError, TypeError, KeyError):
        zone = ZoneInfo('Europe/London')
        evening, beginning = datetime.now(zone).date(), time(18, 0)
    with st.sidebar:
        st.caption('Session timing')
        evening = st.date_input('Session date', value=evening, key='sequence_session_date')
        beginning = st.time_input('Start time', value=beginning, key='sequence_session_start')
        st.caption(str(zone))
    return datetime.combine(evening, beginning, tzinfo=zone)
