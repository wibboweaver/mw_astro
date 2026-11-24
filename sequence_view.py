"""Hierarchical sequence planning with persistent local disable choices."""
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from sequence_analyser import (COMPOSITES, SequenceReader, camera_ramp_seconds,
                               class_name, display_name, duration_text, enabled,
                               instruction_note, parse_document)


SETTINGS_DIR = Path(__file__).with_name('.sequence-analysis')


@dataclass
class SequenceNode:
    key: str
    name: str
    role: str
    data: dict
    parents: tuple
    children: list = field(default_factory=list)


class SequencePlan(SequenceReader):
    """All projections use effective state, including every disabled ancestor."""
    def __init__(self, content, disabled=()):
        document = parse_document(content)
        super().__init__(document)
        self.disabled = set(disabled)
        self.nodes = {}
        self.by_object = {}
        self.root = self.build(document, 'root')
        self.document = self.root.data
        self.walk(self.document)

    def build(self, data, key, parents=(), role='Instruction', ancestors=()):
        if not isinstance(data, dict):
            raise ValueError('The sequence contains an invalid instruction or trigger.')
        if len(parents) > 100 or len(self.nodes) >= 10000:
            raise ValueError('The sequence nesting is too deep or too large.')
        if id(data) in ancestors:
            raise ValueError('The sequence contains a circular object reference.')
        ancestors = ancestors + (id(data),)
        # JSON.NET references may reuse one instruction in several positions.
        # Each occurrence gets independent controls and an independent subtree.
        original = data
        data = dict(original)
        group = 'Items' in data and class_name(data) not in COMPOSITES and role == 'Instruction'
        node = SequenceNode(key, display_name(data), 'Group' if group else role, data, parents)
        self.nodes[key] = node
        self.by_object.setdefault(id(data), []).append(key)
        parents = parents + (key,)
        items = [self.build(child, f'{key}/items/{index}', parents, ancestors=ancestors)
                 for index, child in enumerate(self.collection(original, 'Items'))]
        triggers = [self.build(trigger, f'{key}/triggers/{index}', parents, 'Trigger', ancestors)
                    for index, trigger in enumerate(self.collection(original, 'Triggers'))]
        conditions = [self.build(condition, f'{key}/conditions/{index}', parents, 'Condition', ancestors)
                      for index, condition in enumerate(self.collection(original, 'Conditions'))]
        node.children.extend(conditions + items + triggers)
        if 'Items' in original:
            data['Items'] = [child.data for child in items]
        if 'Triggers' in original:
            data['Triggers'] = [child.data for child in triggers]
        if 'Conditions' in original:
            data['Conditions'] = [child.data for child in conditions]
        if role == 'Trigger' and original.get('TriggerRunner'):
            runner = self.resolve(original['TriggerRunner'])
            actions = self.build(runner, f'{key}/runner', parents, ancestors=ancestors)
            actions.name = 'Actions'
            node.children.append(actions)
            data['TriggerRunner'] = actions.data
        return node

    def enabled(self, data):
        keys = self.by_object.get(id(data), [])
        for key in keys:
            node = self.nodes[key]
            if any(parent in self.disabled or enabled(self.nodes[parent].data) is False
                   for parent in node.parents + (key,)):
                return False
        return enabled(data) is not False

    def state(self, node):
        return self.enabled(node.data)

    def inherited_disabled(self, node):
        return any(parent in self.disabled or enabled(self.nodes[parent].data) is False
                   for parent in node.parents)

    def trigger_action_estimate(self, node):
        if not self.state(node):
            return 0, False
        runner = next((child for child in node.children if child.key == node.key + '/runner'), None)
        if runner is None:
            return 0, True
        seconds, _ = self.estimate(runner.data)
        # Trigger execution can also perform work outside the saved runner.
        return seconds, True

    def timing(self, node):
        if node.role == 'Condition' or not self.state(node):
            return '0 s'
        context = 'per activation' if node.role == 'Trigger' else ''
        repetitions = 1
        for parent_key in node.parents:
            parent = self.nodes[parent_key]
            if parent.role == 'Trigger':
                context = 'per activation'
                repetitions = 1
            count = self.repetitions(parent.data)
            if count is None:
                context = context or 'per pass'
            else:
                repetitions *= count
        if node.role == 'Trigger':
            seconds, variable = self.trigger_action_estimate(node)
            repetitions = 1
        else:
            seconds, variable = self.estimate(node.data)
        seconds *= repetitions
        if variable and not seconds:
            return 'Variable'
        if self.includes_camera_ramp(node):
            result = '≈ ' + duration_text(seconds) + (' + variable' if variable else '')
        else:
            result = ('≥ ' if variable else '') + duration_text(seconds)
        return result + (' ' + context if context and seconds else '')

    def section_timing(self, node, section):
        """Roll up the same enabled work used by the parent projection."""
        if not self.state(node) or section == 'Conditions':
            return '0 s'
        children = self.sections(node)[section]
        if not any(self.state(child) for child in children):
            return '0 s'
        if section == 'Triggers':
            # Firing frequency is runtime-dependent, so action durations cannot
            # be added to the scheduled sequence as fixed work.
            seconds = sum(self.trigger_action_estimate(child)[0] for child in children)
            return f'≥ {duration_text(seconds)} per activation each' if seconds else 'Variable'
        data = dict(node.data)
        data['Triggers'] = []
        temporary = SequenceNode(node.key, node.name, node.role, data, node.parents, children)
        # The temporary node has no object lookup, so effective state was
        # explicitly checked above. Its real children retain their identity.
        return self.timing(temporary)

    def includes_camera_ramp(self, node):
        if not self.state(node) or node.role == 'Trigger':
            return False
        return (camera_ramp_seconds(node.data) is not None or
                any(self.includes_camera_ramp(child) for child in node.children))

    @property
    def projection(self):
        return self.estimate(self.root.data)

    @property
    def active_rows(self):
        return [row for row in self.rows if row['Enabled'] == 'Yes']

    def sections(self, node):
        """Return actual sequence entries, without JSON.NET collection wrappers."""
        return {
            'Conditions': [child for child in node.children if child.key.startswith(node.key + '/conditions/')],
            'Items': [child for child in node.children if child.key.startswith(node.key + '/items/')],
            'Triggers': [child for child in node.children if child.key.startswith(node.key + '/triggers/')],
        }


HIDDEN_FIELDS = {
    'Name', 'Text', 'Parent', 'Strategy', 'IsExpanded', 'Status', 'IsEnabled', 'Enabled',
    'Disabled', 'IsDisabled', 'Items', 'Conditions', 'Triggers', 'TriggerRunner',
    'CompletedIterations', 'ExposureCount', 'ExposureInfoList', 'ExposureInfoListExpanded',
    'ErrorBehavior', 'Attempts', 'Inherited', 'Issues', 'Target', 'Coordinates', 'InputCoordinates',
}
FIELD_LABELS = {
    'Temperature': 'Target temperature', 'Duration': 'Ramp duration', 'Time': 'Wait duration',
    'ExposureTime': 'Exposure time', 'ImageType': 'Frame type', 'Iterations': 'Repetitions',
    'AfterExposures': 'Every', 'SampleSize': 'Sample size', 'PositionAngle': 'Rotation',
    'ForceCalibration': 'Force guiding calibration', 'KeepPanelClosed': 'Keep panel closed',
}
CONDITION_NAMES = {
    'LoopCondition': 'Repeat', 'TimeCondition': 'Loop until time',
    'TimeSpanCondition': 'Loop for duration', 'SafetyMonitorCondition': 'Loop while safe',
    'LoopWhileUnsafe': 'Loop while unsafe', 'SunAltitudeCondition': 'Sun altitude limit',
    'AltitudeCondition': 'Target altitude limit', 'AboveHorizonCondition': 'Target above horizon',
    'MoonAltitudeCondition': 'Moon altitude limit', 'MoonIlluminationCondition': 'Moon illumination limit',
}


def readable_title(node):
    kind = class_name(node.data)
    text = node.data.get('Text')
    if kind in {'MessageBox', 'Annotation'} and text:
        lines = str(text).strip().splitlines()
        if not lines:
            return node.name
        first_line = lines[0]
        if len(first_line) > 90:
            first_line = first_line[:87] + '…'
        return ('Message: ' if kind == 'MessageBox' else 'Note: ') + first_line
    if node.role == 'Condition':
        if kind == 'LoopCondition':
            value = node.data.get('IterationsExpression', node.data.get('Iterations'))
            if isinstance(value, dict):
                value = value.get('Definition')
            return f'Repeat {value} times' if value is not None else 'Repeat'
        return CONDITION_NAMES.get(kind, node.name)
    if kind == 'CoolCamera':
        seconds = camera_ramp_seconds(node.data)
        temperature = node.data.get('Temperature')
        if seconds is not None and isinstance(temperature, (int, float)):
            return f'{node.name} → {temperature:g}°C over {duration_text(seconds)}'
    return node.name


def instruction_details(node, resolve=lambda value: value):
    """Readable settings that explain execution, excluding IDs and saved UI state."""
    details = []
    data = node.data
    kind = class_name(data)
    target = resolve(data.get('Target'))
    if isinstance(target, dict):
        if target.get('TargetName'):
            details.append(('Target', str(target['TargetName'])))
        angle = target.get('PositionAngle', target.get('Rotation'))
        if angle is not None:
            details.append(('Rotation', f'{angle:g}°' if isinstance(angle, (int, float)) else str(angle)))
    for raw_key, raw_value in data.items():
        key = raw_key.removesuffix('Expression')
        if key in HIDDEN_FIELDS or key.startswith('$') or key.endswith('Expanded'):
            continue
        if raw_key == key and key + 'Expression' in data:
            continue
        value = resolve(raw_value)
        label = FIELD_LABELS.get(key, re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', key))
        if isinstance(value, dict):
            if 'Definition' in value:
                value = value['Definition']
            elif key == 'Filter':
                value = value.get('Name', value.get('_name'))
            elif key == 'Binning' and 'X' in value and 'Y' in value:
                value = f'{value["X"]} × {value["Y"]}'
            else:
                continue
        if value is None or isinstance(value, (list, dict)):
            continue
        if isinstance(value, bool):
            value = 'Yes' if value else 'No'
        elif isinstance(value, (int, float)):
            value = f'{value:g}'
        else:
            value = str(value)
        if key in {'Gain', 'Offset'} and value == '-1':
            value = 'Camera default'
        elif key == 'Duration' and kind in {'CoolCamera', 'WarmCamera'}:
            value += ' min'
        elif key in {'ExposureTime', 'Time'}:
            value += ' s'
        elif key == 'Temperature':
            value += '°C'
        elif key in {'PositionAngle', 'Rotation'}:
            value += '°'
        elif key == 'AfterExposures':
            value += ' images'
        details.append((label, value))
    attempts = data.get('Attempts', 1)
    if attempts != 1:
        details.append(('Maximum attempts', str(attempts)))
    error = data.get('ErrorBehavior', 0)
    if error not in (0, '0', 'ContinueOnError'):
        behaviours = {
            '1': 'Skip this instruction set', 'SkipInstructionSetOnError': 'Skip this instruction set',
            '2': 'Abort the sequence', 'AbortOnError': 'Abort the sequence',
            '3': 'Skip to sequence end instructions', 'SkipToSequenceEndInstructions': 'Skip to sequence end instructions',
        }
        details.append(('On failure', behaviours.get(str(error), str(error))))
    return details


def sequence_key(content):
    return hashlib.sha256(content).hexdigest()


def load_choices(sequence_id):
    path = SETTINGS_DIR / f'{sequence_id}.json'
    if not path.exists():
        return set()
    document = json.loads(path.read_text())
    if not isinstance(document, dict) or document.get('version') != 1:
        raise ValueError('Saved sequence choices have an unsupported format.')
    disabled = document.get('disabled')
    if not isinstance(disabled, list) or any(not isinstance(key, str) for key in disabled):
        raise ValueError('Saved sequence choices are invalid.')
    return set(disabled)


def save_choices(sequence_id, disabled):
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = SETTINGS_DIR / f'{sequence_id}.json'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=SETTINGS_DIR, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({'version': 1, 'disabled': sorted(disabled)}, stream)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def render_page():
    import streamlit as st
    from sequence_insights import (format_timing, heading, projected_finish,
                                   render_insights, session_start_controls)

    st.title('Sequence analyser')
    hide_empty = st.sidebar.checkbox('Hide empty containers', value=True,
                                     key='sequence_hide_empty_containers')
    st.write('Open a NINA sequence to review its groups, instructions and triggers.')
    upload = st.file_uploader('Browse for a NINA sequence', type=['json'], key='nina_sequence_upload')
    if upload is None:
        st.info('Choose a sequence JSON file to begin.')
        return
    content = upload.getvalue()
    sequence_id = sequence_key(content)
    state_key = f'sequence_choices_{sequence_id}'
    error_key = f'sequence_save_error_{sequence_id}'
    try:
        if state_key not in st.session_state:
            st.session_state[state_key] = load_choices(sequence_id)
        plan = SequencePlan(content, st.session_state[state_key])
    except (OSError, ValueError, RecursionError) as exc:
        st.error(f'Cannot load this sequence: {exc}')
        return
    if not plan.rows:
        st.warning('This sequence contains no instructions or triggers.')
        return

    def update_choice(node_key, widget_key):
        choices = set(st.session_state[state_key])
        if st.session_state[widget_key]:
            choices.add(node_key)
        else:
            choices.discard(node_key)
        st.session_state[state_key] = choices
        try:
            save_choices(sequence_id, choices)
            st.session_state.pop(error_key, None)
        except OSError as exc:
            st.session_state[error_key] = f'Choices apply in this session but could not be saved: {exc}'

    def disable_control(node, label='Disable', label_visibility='visible'):
        inherited = plan.inherited_disabled(node)
        saved_disabled = enabled(node.data) is False
        locked = inherited or saved_disabled
        key = f'sequence_disable_{sequence_id}_{node.key}' + ('_inherited' if locked else '')
        st.checkbox('Disabled by parent' if inherited else label,
                    value=True if locked else node.key in plan.disabled,
                    disabled=locked, key=key, label_visibility=label_visibility,
                    on_change=update_choice, args=(node.key, key))

    def render_node(node, depth=0):
        active = plan.state(node)
        title = readable_title(node)
        timing = plan.timing(node)
        label = heading(title, active, timing)
        with st.expander(label, expanded=depth == 0):
            disable_control(node, 'Disable entire sequence' if node.key == 'root' else f'Disable {node.name}')
            if not active:
                st.caption('This branch and all its children are excluded from calculations.')
            kind = class_name(node.data)
            message = node.data.get('Text')
            if kind in {'MessageBox', 'Annotation'} and message:
                # Plain text preserves multiline messages and does not interpret
                # their content as Markdown, HTML or app instructions.
                st.text(str(message).replace('\r\n', '\n').replace('\r', '\n'))
            elif node.role == 'Condition':
                st.caption('Controls whether or how often this group runs; adds no time of its own.')
            elif node.role != 'Group':
                st.caption(instruction_note(node.data))
            strategy = plan.resolve(node.data.get('Strategy', {}))
            if isinstance(strategy, dict) and 'Parallel' in class_name(strategy):
                st.caption('Items run in parallel.')
            for label, value in instruction_details(node, plan.resolve):
                setting, detail = st.columns([1, 3])
                setting.text(label)
                detail.text(value)
            is_container = 'Items' in node.data or node.role == 'Group'
            sections = plan.sections(node)
            for label, children in sections.items():
                if not children and (hide_empty or not is_container):
                    continue
                section_active = active and (not children or any(plan.state(child) for child in children))
                with st.expander(heading(f'{label} ({len(children)})', section_active, plan.section_timing(node, label)),
                                 expanded=depth == 0 and label == 'Items'):
                    if not children:
                        st.caption(f'No {label.lower()}.')
                    for child in children:
                        render_node(child, depth + 1)
            for child in node.children:
                if child.key == node.key + '/runner':
                    render_node(child, depth + 1)

    start = session_start_controls()
    active = plan.active_rows
    instructions, triggers, duration, finish = st.columns(4)
    instructions.metric('Active instructions', sum(row['Type'] == 'Instruction' for row in active))
    triggers.metric('Active triggers', sum(row['Type'] == 'Trigger' for row in active))
    duration.metric('Expected sequence time', format_timing(plan.timing(plan.root)))
    end, variable = projected_finish(plan, start)
    finish_value = '--:-- variable' if end is None else end.strftime('%H:%M')
    if end is not None:
        finish_value += ' variable' if variable else ' estimated' if plan.includes_camera_ramp(plan.root) else ''
    finish.metric('Projected finish', finish_value,
                  help=('No duration is available.' if end is None else end.strftime('%a %d %b %Y %H:%M %Z')))
    if variable:
        st.caption('Projected finish covers known durations and configured camera ramps; unestimated actions, '
                   'operator waits and trigger activity can extend the session.')
    elif end is not None:
        st.caption('Projected finish: ' + end.strftime('%a %d %b %Y %H:%M %Z'))
    render_insights(plan)
    st.caption('Disable choices are saved for this sequence in this app. A checked box excludes the step '
               'and all its children. Re-enabling a parent preserves individual child choices. '
               'Items without a saved NINA state start enabled for analysis.')
    st.caption('Durations use HH:MM, with seconds added for short actions. “variable” marks unestimated work; '
               '“estimated” marks camera ramp allowances. Fixed loops are included; parallel groups use their '
               'longest branch. Trigger action times are per activation. Capture summaries exclude download overhead.')
    if error_key in st.session_state:
        st.error(st.session_state[error_key])
    render_node(plan.root)
