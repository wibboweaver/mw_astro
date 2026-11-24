"""Persistent ESA DSS2-colour tile viewer with a camera framing overlay."""
from pathlib import Path
from functools import lru_cache
import math
from framing import framing_data

ESA_SURVEY='https://skies.esac.esa.int/DSSColor'
ALADIN_MODULE='https://cdn.jsdelivr.net/npm/aladin-lite@3.8.2/dist/aladin.js'


def esa_preview_data(ra,dec,focal_length,sensor_width,sensor_height,fov,rotation,camera_width,camera_height,view_key):
    if not math.isfinite(ra) or not 0<=ra<360 or not math.isfinite(dec) or not -90<=dec<=90:
        raise ValueError('Invalid sky coordinates.')
    data=framing_data(b'',focal_length,sensor_width,sensor_height,fov,rotation,camera_width,camera_height,view_key)
    data.pop('image')
    return dict(data,ra=ra,dec=dec,survey=ESA_SURVEY,module_url=ALADIN_MODULE,
                pixel_scale_width=math.degrees(sensor_width/focal_length/camera_width)*3600,
                pixel_scale_height=math.degrees(sensor_height/focal_length/camera_height)*3600)


@lru_cache(maxsize=1)
def esa_preview_component():
    from streamlit.components.v2 import component
    return component('esa_dss2_preview',html='''<section aria-label="ESA DSS2 colour camera framing preview">
    <div id="preview-home"><div class="sky-frame" id="sky-frame"><div id="sky" aria-label="DSS2 colour sky view"></div>
      <svg id="overlay" viewBox="0 0 600 600" aria-label="Camera field overlay"><g id="camera-frame"><rect id="frame" fill="#ffcf3312" stroke="#ffcf33" stroke-width="2.5" vector-effect="non-scaling-stroke"/><text id="dimensions"><tspan id="frame-fov"/><tspan id="frame-resolution" dy="15"/><tspan id="frame-scale" dy="15"/></text></g><path d="M294 300h12 M300 294v12" stroke="#ffcf33"/></svg>
    </div>
    </div>
    <p id="status" role="status">Loading ESA DSS2 colour survey…</p>
    <label for="crop">Crop preview — composition only</label>
    <select id="crop" aria-label="Crop preview — composition only">
      <option value="1">Full frame</option><option value="0.75">75% retained</option>
      <option value="0.5">50% retained</option><option value="0.33">33% retained</option>
    </select>
    <p id="crop-details" role="status"></p>
    <small>DSS imagery shows composition, not the detail or noise of your capture.</small>
    <label>Camera rotation: <output id="angle-value"></output>°<input id="angle" aria-label="Camera rotation (degrees)" type="range" min="0" max="360" step="1"/></label>
    <button id="enlarge" type="button">Enlarge image</button> <button id="centre" type="button">Centre image</button> <button id="retry" type="button" hidden>Retry image</button>
    <dialog id="large-view" aria-labelledby="large-title">
      <header><h3 id="large-title">Image preview</h3><button id="close-large" type="button" aria-label="Close enlarged image">Close</button></header>
      <div id="large-slot"></div>
      <p id="large-details"></p>
      <small>Drag to adjust framing. DSS survey detail is not a prediction of your captured resolution. Press Escape to close.</small>
    </dialog>
    </section>''',css='''section{font-family:var(--st-font,sans-serif);color:var(--st-text-color,#31333f)}
    .sky-frame{position:relative;width:100%;aspect-ratio:1;background:#111;border-radius:8px;overflow:hidden}
    .sky-frame.cropped{border:1px solid #ffcf33;box-sizing:border-box}
    select{font:inherit;font-size:14px;background:var(--st-secondary-background-color,#222);color:inherit;border:1px solid #8887;border-radius:6px;padding:6px 8px;width:100%}
    #sky,#overlay{position:absolute;inset:0;width:100%;height:100%}#overlay{pointer-events:none;z-index:2}
    dialog{background:var(--st-background-color,#111);color:inherit;border:1px solid #8887;border-radius:10px;padding:14px;width:94vw;max-width:94vw;max-height:94vh;box-sizing:border-box;overflow:auto}
    dialog::backdrop{background:#000c}dialog[open]{display:flex;flex-direction:column;gap:8px}
    header{display:flex;align-items:center;justify-content:space-between;gap:16px}h3{margin:0;font-size:18px}
    #large-slot{display:flex;justify-content:center;align-items:center;min-height:0}
    #large-slot .sky-frame{width:min(90vw,calc(74vh * var(--preview-aspect,1)));flex:none}
    #large-details{margin:0}dialog small{margin-top:0}
    #dimensions{font-size:12px;fill:#ffcf33;stroke:#000;stroke-width:2px;paint-order:stroke;stroke-linejoin:round}
    p{margin:8px 0;font-size:14px}#status:empty{display:none}label{display:block;font-size:14px;margin:12px 0}
    input{display:block;width:100%;accent-color:#ff4b4b;margin-top:8px}small{display:block;font-size:12px;opacity:.75;margin-top:8px;line-height:1.4}
    button{background:transparent;color:inherit;border:1px solid #8887;border-radius:6px;padding:5px 10px;cursor:pointer}''',js=Path(__file__).with_suffix('.js').read_text())


def render_esa_preview(data,on_rotation_change):
    return esa_preview_component()(data=data,key='esa_camera_framing',default={'rotation':data['rotation']},on_rotation_change=on_rotation_change,on_centre_change=lambda:None)

_loaded_source_stamp=(Path(__file__).stat().st_mtime_ns,Path(__file__).with_suffix('.js').stat().st_mtime_ns)
