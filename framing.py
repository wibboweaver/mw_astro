"""Tangent-plane sensor framing over north-up DSS cutouts."""
import base64
import math
from pathlib import Path


def field_of_view(focal_length_mm, sensor_width_mm, sensor_height_mm):
    values = (focal_length_mm, sensor_width_mm, sensor_height_mm)
    if not all(isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) and v > 0 for v in values):
        raise ValueError('Focal length and sensor dimensions must be positive finite numbers.')
    return tuple(math.degrees(2 * math.atan(size / (2 * focal_length_mm)))
                 for size in (sensor_width_mm, sensor_height_mm))


def fit_preview_field(target_field, focal_length_mm, sensor_width_mm, sensor_height_mm):
    field_of_view(focal_length_mm, sensor_width_mm, sensor_height_mm)
    # Include the entire sensor diagonal at any rotation with 15% margin.
    diagonal = math.hypot(sensor_width_mm, sensor_height_mm)
    field = math.degrees(2 * math.atan(1.15 * diagonal / (2 * focal_length_mm)))
    return max(0.1, min(10.0, max(target_field, field)))


def sensor_pixels(focal_length_mm, sensor_width_mm, sensor_height_mm, image_field_deg):
    field_of_view(focal_length_mm, sensor_width_mm, sensor_height_mm)
    if not math.isfinite(image_field_deg) or not 0.1 <= image_field_deg <= 10:
        raise ValueError('Image field must be between 0.1 and 10 degrees.')
    # HiPS2FITS TAN cutouts: linear distances scale with tan(angular radius).
    scale = 600 / (2 * focal_length_mm * math.tan(math.radians(image_field_deg / 2)))
    return sensor_width_mm * scale, sensor_height_mm * scale


def framing_data(image_bytes, focal_length_mm, sensor_width_mm, sensor_height_mm,
                 image_field_deg, rotation_deg, camera_width_px=6248, camera_height_px=4176, view_key=""):
    width, height = sensor_pixels(focal_length_mm, sensor_width_mm, sensor_height_mm, image_field_deg)
    fov_width, fov_height = field_of_view(focal_length_mm, sensor_width_mm, sensor_height_mm)
    if not math.isfinite(rotation_deg) or not 0 <= rotation_deg <= 360:
        raise ValueError('Rotation must be between 0 and 360 degrees.')
    if any(type(value) is not int or not 1 <= value <= 100000
           for value in (camera_width_px, camera_height_px)):
        raise ValueError('Camera dimensions must be integers from 1 to 100000 pixels.')
    return dict(image='data:image/jpeg;base64,' + base64.b64encode(image_bytes).decode('ascii'),
                width=width, height=height, fov_width=fov_width, fov_height=fov_height,
                image_field=image_field_deg, rotation=rotation_deg,
                camera_width_px=camera_width_px, camera_height_px=camera_height_px, view_key=view_key)


def render_framing(data, on_rotation_change):
    return framing_component()(data=data, key='camera_framing',
        default={'rotation': data['rotation']}, on_rotation_change=on_rotation_change)


# Register once per Python process, so ordinary Streamlit reruns reuse the component.
from functools import lru_cache
@lru_cache(maxsize=1)
def framing_component():
    from streamlit.components.v2 import component
    return component('camera_frame_pan',
        html='''<section aria-label="Camera framing preview">
          <svg role="img" id="canvas" aria-label="Drag the DSS2 image to position the object inside the camera frame" viewBox="0 0 600 600">
            <defs><clipPath id="image-clip"><rect width="600" height="600"/></clipPath></defs>
            <g clip-path="url(#image-clip)"><image id="survey" width="600" height="600"/>
              <rect id="frame" fill="#ffcf3320" stroke="#ffcf33" stroke-width="2.5" vector-effect="non-scaling-stroke"/>
              <path d="M294 300h12 M300 294v12" stroke="#ffcf33" stroke-width="1" vector-effect="non-scaling-stroke"/>
            </g>
          </svg>
          <p id="dimensions"></p>
          <label>Camera rotation: <output id="angle-value"></output>°
            <input id="angle" aria-label="Camera rotation (degrees)" type="range" min="0" max="360" step="1"/>
          </label>
          <button id="centre" type="button">Centre image</button>
          <small>Drag the image to position the object inside the frame.</small>
        </section>''',
        css='''section {font-family:var(--st-font, sans-serif);color:var(--st-text-color, #31333f)}
        svg {display:block;width:100%;aspect-ratio:1;background:#111;border-radius:8px;cursor:grab;touch-action:none;user-select:none}
        svg.dragging {cursor:grabbing}
        p {margin:8px 0;font-size:14px} label {display:block;margin:12px 0 0;font-size:14px}
        input {display:block;width:100%;accent-color:#ff4b4b;margin:8px 0}
        small {display:block;font-size:12px;opacity:.75;line-height:1.4;margin-top:8px}
        button {background:transparent;color:inherit;border:1px solid #8887;border-radius:6px;padding:5px 10px;cursor:pointer}''',
        js=Path(__file__).with_name('framing.js').read_text())

_loaded_source_stamp = (Path(__file__).stat().st_mtime_ns, Path(__file__).with_name("framing.js").stat().st_mtime_ns)
