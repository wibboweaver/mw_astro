"""Read-only analysis of NINA advanced-sequencer JSON exports.

Format reference: isbeorn/nina, NINA.Sequencer/Serialization and SequenceItem.
No NINA types, expressions, scripts or equipment commands are executed here.
"""
import json
import math
import re
from dataclasses import dataclass


COLUMNS = ['Trigger or instruction', 'Type', 'Enabled', 'Expected time', 'Note']
COMPOSITES = {'SmartExposure', 'TakeManyExposures'}
ADAPTIVE = {'AutoBrightnessFlat', 'AutoExposureFlat', 'SkyFlat', 'TrainedFlatExposure',
            'TrainedDarkFlatExposure', 'LinkedTemplateContainer'}
NOTES = {
    'TakeExposure': 'Capture one image.',
    'TakeSubframeExposure': 'Capture one image using a cropped sensor area.',
    'SmartExposure': 'Capture a set of images with filter selection and dithering.',
    'TakeManyExposures': 'Capture a set of images.',
    'WaitForTimeSpan': 'Pause for a fixed interval.',
    'WaitForTime': 'Wait until the configured clock or astronomical time.',
    'WaitForAltitude': 'Wait until the target reaches the configured altitude.',
    'WaitUntilAboveHorizon': 'Wait until the target is above the horizon.',
    'WaitForSunAltitude': 'Wait for the configured Sun altitude.',
    'WaitForMoonAltitude': 'Wait for the configured Moon altitude.',
    'WaitUntilSafe': 'Wait until the safety monitor reports safe conditions.',
    'RunAutofocus': 'Measure star focus and adjust the focuser.',
    'SwitchFilter': 'Move the filter wheel to the selected filter.',
    'Dither': 'Offset the pointing slightly and let guiding settle.',
    'DitherAfterExposures': 'Dither after the configured number of images.',
    'MeridianFlipTrigger': 'Flip the mount when the target crosses the meridian.',
    'AutofocusAfterExposures': 'Refocus after the configured number of images.',
    'AutofocusAfterFilterChange': 'Refocus after changing filters.',
    'AutofocusAfterHFRIncreaseTrigger': 'Refocus when measured star sizes increase.',
    'AutofocusAfterTemperatureChangeTrigger': 'Refocus after a temperature change.',
    'AutofocusAfterTimeTrigger': 'Refocus after the configured time interval.',
    'CenterAfterDriftTrigger': 'Recenter the target when pointing drifts.',
    'RestoreGuiding': 'Restart guiding if it stops.',
    'ReconnectOnDownloadFailure': 'Reconnect the camera after a download failure.',
    'ReconnectTrigger': 'Reconnect equipment when required.',
    'SynchronizeDomeTrigger': 'Keep the dome aligned with the telescope.',
    'StartGuiding': 'Start guiding and wait for settling.',
    'StopGuiding': 'Stop guiding.',
    'SlewToCoordinates': 'Slew the mount to the specified coordinates.',
    'SlewToTarget': 'Slew the mount to the current target.',
    'Center': 'Plate solve and adjust the pointing to center the target.',
    'CenterAndRotate': 'Center the target and set the camera rotation.',
    'SolveAndSync': 'Plate solve an image and sync the mount coordinates.',
    'ParkScope': 'Move the telescope to its parked position.',
    'UnparkScope': 'Unpark the telescope.',
    'SetTracking': 'Set the mount tracking mode.',
    'CoolCamera': 'Cool the camera to the selected temperature.',
    'WarmCamera': 'Warm the camera.',
    'ConnectAllEquipment': 'Connect the configured equipment.',
    'DisconnectAllEquipment': 'Disconnect the configured equipment.',
    'ConnectEquipment': 'Connect the selected device.',
    'DisconnectEquipment': 'Disconnect the selected device.',
    'OpenDomeShutter': 'Open the dome shutter.',
    'CloseDomeShutter': 'Close the dome shutter.',
    'OpenCover': 'Open the telescope cover.',
    'CloseCover': 'Close the telescope cover.',
    'AutoBrightnessFlat': 'Adjust panel brightness and capture flat frames.',
    'AutoExposureFlat': 'Find a suitable exposure and capture flat frames.',
    'SkyFlat': 'Capture flat frames using sky illumination.',
    'TrainedFlatExposure': 'Capture flats using previously trained exposure settings.',
    'TrainedDarkFlatExposure': 'Capture matching dark frames for trained flats.',
    'DewHeater': 'Switch the camera dew heater on or off.',
    'DisableDomeSynchronization': 'Stop automatic dome tracking.',
    'EnableDomeSynchronization': 'Enable automatic dome tracking.',
    'SynchronizeDome': 'Align the dome opening with the telescope.',
    'ExternalScript': 'Run the configured external script.',
    'FindHome': 'Move the mount to its home position.',
    'FindHomeDome': 'Find the dome home position.',
    'MessageBox': 'Display a message; may wait for the operator.',
    'MoveFocuserAbsolute': 'Move the focuser to the configured position.',
    'MoveFocuserRelative': 'Move the focuser by the configured offset.',
    'MoveFocuserByTemperature': 'Compensate focus for a temperature change.',
    'MoveRotatorMechanical': 'Rotate the camera to the configured mechanical angle.',
    'ParkDome': 'Move the dome to its parked position.',
    'SaveSequence': 'Save the current sequence to disk.',
    'SetBrightness': 'Set the flat panel brightness.',
    'SetReadoutMode': 'Select the camera readout mode.',
    'SetSwitchValue': 'Set the selected equipment switch value.',
    'SetUSBLimit': 'Set the camera USB bandwidth limit.',
    'SlewDomeAzimuth': 'Move the dome to the configured azimuth.',
    'SlewScopeToAltAz': 'Slew the mount to the configured altitude and azimuth.',
    'SlewScopeToRaDec': 'Slew the mount to the configured sky coordinates.',
    'SolveAndRotate': 'Plate solve and adjust the camera rotation.',
    'SwitchProfile': 'Change the NINA equipment profile.',
    'ToggleLight': 'Switch the flat panel light on or off.',
    'Annotation': 'Sequence comment; no equipment action.',
}


def duration_text(seconds):
    if seconds == 0:
        return '0 s'
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f'{int(hours)} h')
    if minutes:
        parts.append(f'{int(minutes)} min')
    if seconds:
        parts.append(f'{seconds:.3g} s')
    return ' '.join(parts)


def class_name(node):
    if not isinstance(node, dict):
        return ''
    return str(node.get('$type', '')).split(',')[0].rsplit('.', 1)[-1]


def display_name(node):
    name = node.get('Name')
    return str(name) if name else re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', class_name(node)) or 'Unnamed instruction'


def enabled(node):
    for key, reverse in (('IsEnabled', False), ('Enabled', False), ('IsDisabled', True), ('Disabled', True)):
        if key in node:
            value = node[key]
            if isinstance(value, bool):
                return not value if reverse else value
            if str(value).lower() in ('true', 'false', '0', '1'):
                flag = str(value).lower() in ('true', '1')
                return not flag if reverse else flag
    status = str(node.get('Status', '')).strip().lower()
    if status in ('disabled', '5'):
        return False
    if status in ('created', 'running', 'finished', 'failed', 'skipped', '0', '1', '2', '3', '4'):
        return True
    return None


def number(node, field):
    # New NINA exports may store a numeric literal in an Expression.Definition.
    # Nonliteral expressions need runtime information and must remain unknown.
    value = node.get(field + 'Expression', node.get(field))
    if isinstance(value, dict):
        value = value.get('Definition')
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def camera_ramp_seconds(node):
    if class_name(node) not in {'CoolCamera', 'WarmCamera'}:
        return None
    minutes = number(node, 'Duration')
    # Zero requests immediate regulation; elapsed time then needs camera state.
    return minutes * 60 if minutes is not None and minutes > 0 else None


def instruction_note(node):
    kind = class_name(node)
    note = NOTES.get(kind, 'Plugin or unrecognised step; duration depends on its implementation.')
    if kind in {'CoolCamera', 'WarmCamera'}:
        seconds = camera_ramp_seconds(node)
        if seconds is not None:
            note += f' Configured ramp: {duration_text(seconds)}; actual time depends on camera temperature.'
        if kind == 'CoolCamera' and isinstance(node.get('Temperature'), (int, float)):
            note += f' Target: {node["Temperature"]:g}°C.'
    if kind == 'Annotation' and node.get('Text'):
        text = str(node['Text'])
        note = text[:157] + '…' if len(text) > 160 else text
    return note


@dataclass
class Analysis:
    name: str
    rows: list
    unknown_enabled: bool


class SequenceReader:
    def __init__(self, document):
        self.document = document
        self.references = {}
        self.rows = []
        self.unknown_enabled = False
        pending = [document]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                if '$id' in value:
                    key = str(value['$id'])
                    if key in self.references:
                        raise ValueError('The sequence contains duplicate object references.')
                    self.references[key] = value
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)

    def enabled(self, node):
        return enabled(node)

    def resolve(self, node):
        seen = set()
        while isinstance(node, dict) and '$ref' in node:
            reference = str(node['$ref'])
            if reference in seen or reference not in self.references:
                raise ValueError('The sequence contains a missing or circular object reference.')
            seen.add(reference)
            node = self.references[reference]
        return node

    def collection(self, node, key):
        value = self.resolve(node.get(key, []))
        if isinstance(value, dict):
            value = value.get('$values', [])
        if not isinstance(value, list):
            raise ValueError(f'The sequence has an invalid {key} list.')
        result = [self.resolve(item) for item in value]
        if any(not isinstance(item, dict) for item in result):
            raise ValueError(f'The sequence has an invalid entry in {key}.')
        return result

    def repetitions(self, node):
        if class_name(node) in ADAPTIVE:
            return None
        counts = []
        conditions = self.collection(node, 'Conditions')
        for condition in conditions:
            if self.enabled(condition) is False:
                continue
            if class_name(condition) != 'LoopCondition':
                return None
            count = number(condition, 'Iterations')
            if count is None or not count.is_integer():
                return None
            counts.append(count)
        if counts:
            # Conditions are ANDed; the first exhausted count stops the loop.
            return min(counts)
        if any(class_name(condition) == 'LoopCondition' and self.enabled(condition) is False
               for condition in conditions):
            return 1
        if class_name(node) in COMPOSITES:
            count = number(node, 'Iterations')
            return count if count is not None and count.is_integer() else None
        return 1

    def estimate(self, node, ancestors=()):
        """Return programmed seconds and whether unquantified work remains."""
        if not isinstance(node, dict):
            raise ValueError('The sequence contains an invalid instruction or trigger.')
        if id(node) in ancestors or len(ancestors) > 100:
            raise ValueError('The sequence nesting is circular or too deep.')
        if self.enabled(node) is False:
            return 0, False
        kind = class_name(node)
        if kind in {'CoolCamera', 'WarmCamera'}:
            seconds = camera_ramp_seconds(node)
            return (seconds, False) if seconds is not None else (0, True)
        if kind in {'TakeExposure', 'TakeSubframeExposure'}:
            seconds = number(node, 'ExposureTime')
            return (seconds or 0), seconds is None
        if kind == 'WaitForTimeSpan':
            seconds = number(node, 'Time')
            return (seconds or 0), seconds is None
        if kind == 'Annotation':
            return 0, False
        if 'Items' not in node:
            return 0, True
        children = self.collection(node, 'Items')
        triggers = self.collection(node, 'Triggers')
        if not any(self.enabled(child) is not False for child in children + triggers):
            return 0, False
        count = self.repetitions(node)
        if count == 0:
            return 0, False
        if count is None:
            return 0, True
        estimates = [self.estimate(child, ancestors + (id(node),)) for child in self.collection(node, 'Items')]
        strategy = self.resolve(node.get('Strategy', {}))
        parallel = 'Parallel' in class_name(strategy) or kind == 'ParallelContainer'
        seconds = (max((x[0] for x in estimates), default=0) if parallel else sum(x[0] for x in estimates)) * count
        variable = any(x[1] for x in estimates) or any(self.enabled(t) is not False for t in self.collection(node, 'Triggers'))
        return seconds, variable

    def walk(self, node, path=(), multiplier=1, parent_enabled=True, conditional=False, ancestors=(), role='Instruction'):
        if not isinstance(node, dict):
            raise ValueError('The sequence contains an invalid instruction or trigger.')
        if id(node) in ancestors or len(ancestors) > 100 or len(self.rows) > 10000:
            raise ValueError('The sequence nesting is circular or too large.')
        ancestors = ancestors + (id(node),)
        own_enabled = self.enabled(node)
        if parent_enabled is False or own_enabled is False:
            active = False
        elif parent_enabled is None or own_enabled is None:
            active = None
        else:
            active = True
        kind = class_name(node)
        is_group = 'Items' in node and kind not in COMPOSITES and role != 'Trigger'
        name = display_name(node)
        if is_group:
            count = self.repetitions(node)
            if kind in {'AutoBrightnessFlat', 'AutoExposureFlat', 'SkyFlat', 'TrainedFlatExposure', 'TrainedDarkFlatExposure', 'LinkedTemplateContainer'}:
                # These containers choose exposures/counts at runtime or need
                # another file; their saved internal placeholders are not plans.
                count = None
            factor = None if multiplier is None or count is None else multiplier * count
            for child in self.collection(node, 'Items'):
                self.walk(child, path + (name,), factor, active, conditional, ancestors)
        else:
            if active is None:
                self.unknown_enabled = True
            seconds, variable = self.estimate(node)
            note = instruction_note(node)
            if active is False:
                time = '0 s'
                note += ' Disabled' + (' by its parent.' if parent_enabled is False else '.')
            elif role == 'Trigger' or conditional or multiplier is None:
                time = 'Variable'
                if seconds:
                    note += f' Per activation/pass: {duration_text(seconds)}' + (' + overhead.' if variable else '.')
            else:
                total = seconds * multiplier
                if not math.isfinite(total):
                    raise ValueError('The configured duration is too large.')
                time = ('≥ ' if variable and total else '') + duration_text(total) if total or not variable else 'Variable'
                if multiplier != 1:
                    note += f' Across {int(multiplier)} repetitions.'
                if camera_ramp_seconds(node) is not None:
                    time = '≈ ' + time
            if active is None:
                note += ' Time assumes enabled; status is not saved.'
            self.rows.append({
                'Trigger or instruction': ' › '.join(path + (name,)),
                'Type': role,
                'Enabled': 'Unknown' if active is None else 'Yes' if active else 'No',
                'Expected time': time,
                'Note': note,
            })
            if role == 'Trigger' and node.get('TriggerRunner'):
                runner = self.resolve(node['TriggerRunner'])
                self.walk(runner, path + (name,), 1, active, True, ancestors)
            # Composite instructions show their total once; their triggers
            # are still listed below, without duplicating the internal exposures.
        for trigger in self.collection(node, 'Triggers'):
            self.walk(trigger, path + (name,), 1, active, True, ancestors, 'Trigger')


def parse_document(content):
    try:
        document = json.loads(content)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError('Cannot read this JSON file. Choose a valid NINA advanced sequence export.') from exc
    if not isinstance(document, dict) or not ('Items' in document or '.SequenceItem.' in str(document.get('$type', ''))):
        raise ValueError('This JSON is not a NINA advanced sequence or instruction template.')
    return document


def analyse_sequence(content):
    document = parse_document(content)
    reader = SequenceReader(document)
    reader.walk(document)
    return Analysis(display_name(document), reader.rows, reader.unknown_enabled)


def render_page():
    from sequence_view import render_page as render_tree_page
    render_tree_page()
