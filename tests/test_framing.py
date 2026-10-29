import math
from pathlib import Path
import shutil
import subprocess

import pytest
from framing import field_of_view, fit_preview_field, sensor_pixels, framing_data
from configuration import Settings, save_settings_changes, load_settings


def test_camera_fov_and_tangent_plane_scale():
    width, height = field_of_view(550, 23.5, 15.7)
    assert width == pytest.approx(2.4477, abs=0.001)
    assert height == pytest.approx(1.6354, abs=0.001)
    pixels = sensor_pixels(550, 23.5, 15.7, width)
    assert pixels[0] == pytest.approx(600)
    assert pixels[1] / pixels[0] == pytest.approx(15.7 / 23.5)
    # Doubling focal length halves physical coverage in the same TAN image.
    assert sensor_pixels(1100, 23.5, 15.7, width)[0] == pytest.approx(300)


def test_initial_view_fits_all_rotations_and_respects_service_limit():
    field = fit_preview_field(0.25, 550, 23.5, 15.7)
    width, height = sensor_pixels(550, 23.5, 15.7, field)
    for degrees in range(361):
        angle = math.radians(degrees)
        assert abs(width*math.cos(angle)) + abs(height*math.sin(angle)) < 600
        assert abs(width*math.sin(angle)) + abs(height*math.cos(angle)) < 600
    assert fit_preview_field(5, 550, 23.5, 15.7) == 5
    assert fit_preview_field(1, 20, 100, 100) == 10


@pytest.mark.parametrize('args', [(0,23.5,15.7), (550,-1,15.7), (550,23.5,float('nan'))])
def test_invalid_equipment(args):
    with pytest.raises(ValueError):
        field_of_view(*args)


def test_equipment_and_view_round_trip(tmp_path):
    path = tmp_path/'config.toml'
    path.write_text('[chart]\nstart_hour=22\n')
    save_settings_changes(path, focal_length_mm=400, sensor_width_mm=20, sensor_height_mm=10,
                          frame_rotation_deg=135, camera_width_px=6000, camera_height_px=4000)
    settings = load_settings(path)
    assert (settings.focal_length_mm, settings.sensor_width_mm, settings.sensor_height_mm) == (400,20,10)
    assert settings.frame_rotation_deg == 135 and settings.camera_width_px == 6000 and settings.camera_height_px == 4000
    assert settings.start_hour == 22
    for kwargs in ({'focal_length_mm':0}, {'sensor_width_mm':float('nan')}, {'sensor_height_mm':0},
                   {'frame_rotation_deg':361}, {'camera_width_px':0}, {'camera_height_px':2.5}, {'camera_width_px':True}):
        with pytest.raises(ValueError):
            Settings(**kwargs)


def test_overlay_payload_contains_image_geometry_and_saved_controls():
    data = framing_data(b'JPEG',550,23.5,15.7,4.5,135,6248,4176,view_key='target')
    assert data['image'] == 'data:image/jpeg;base64,SlBFRw=='
    assert data['rotation'] == 135 and data['camera_width_px'] == 6248 and data['camera_height_px'] == 4176
    assert 'zoom' not in data and data['view_key'] == 'target'
    assert data['width'] / data['height'] == pytest.approx(23.5/15.7)



def test_live_drag_rotation_reset_and_target_isolation():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed for browser interaction logic test')
    source = Path(__file__).resolve().parents[1].joinpath('framing.js').read_text()
    script = '''
const elements = new Map(), stored = new Map(), events=[];
global.sessionStorage={getItem:k=>stored.get(k)||null, setItem:(k,v)=>stored.set(k,v)};
global.DOMPoint=class {constructor(x,y){this.x=x;this.y=y} matrixTransform(m){return {x:this.x*m.a,y:this.y*m.d}}};
const captured=new Set();
const element=id=>{if(!elements.has(id)) elements.set(id, {value:0, attrs:{}, classList:{add(){},remove(){}},
 setAttribute(k,v){this.attrs[k]=v}, getScreenCTM(){return {inverse:()=>({a:2.5,d:2.5})}},
 setPointerCapture(id){captured.add(id)},hasPointerCapture(id){return captured.has(id)},releasePointerCapture(id){captured.delete(id)}}); return elements.get(id)};
const root={querySelector:selector=>element(selector.slice(1))};
const data={image:'data:image/jpeg;base64,abc',width:300,height:200,fov_width:2.4,fov_height:1.6,image_field:4.5,rotation:20,camera_width_px:6248,camera_height_px:4176,view_key:'A'};
const component={parentElement:root,data,setStateValue:(k,v)=>events.push([k,v])};
const event=(x,y,id=1,button=0)=>({clientX:x,clientY:y,pointerId:id,button,preventDefault(){}});
''' + source.replace('export default function(component)', 'function render(component)') + '''
let cleanup=render(component), canvas=element('canvas');
if(!element('dimensions').textContent.includes('6248 × 4176 pixels')) throw Error('Missing pixel dimensions');
const original=element('frame').attrs.transform;
canvas.onpointerdown(event(100,100)); canvas.onpointermove(event(120,110));
if(element('survey').attrs.transform!=='translate(50 25)') throw Error('Drag does not account for responsive scaling');
if(element('frame').attrs.transform!==original || element('frame').attrs.width!==300) throw Error('Drag moved or resized frame');
if(events.length) throw Error('Server called during pan');
canvas.onpointerup(event(120,110));
if(captured.size) throw Error('Pointer not released');
element('angle').value=135; element('angle').oninput();
if(element('frame').attrs.transform!=='rotate(-135 300 300)') throw Error('Rotation not immediate');
if(element('survey').attrs.transform!=='translate(50 25)') throw Error('Rotation changed pan');
if(events.length) throw Error('Server called during slider input');
element('angle').onchange();
if(JSON.stringify(events)!==JSON.stringify([['rotation',135]])) throw Error('Commit incorrect');
cleanup(); cleanup=render(component);
if(element('survey').attrs.transform!=='translate(50 25)') throw Error('Pan lost on rerender');
canvas.onpointerdown(event(100,100)); canvas.onpointermove(event(1000,-1000)); canvas.onpointercancel(event(1000,-1000));
if(element('survey').attrs.transform!=='translate(300 -300)') throw Error('Unbounded pan');
element('centre').onclick();
if(element('survey').attrs.transform!=='translate(0 0)') throw Error('Centre failed');
canvas.onpointerdown(event(100,100)); canvas.onpointermove(event(120,110)); canvas.onpointerup(event(120,110));
cleanup(); component.data={...data, view_key:'B'}; cleanup=render(component);
if(element('survey').attrs.transform!=='translate(0 0)') throw Error('Offset leaked to another target');
cleanup(); component.data={...data,image_field:5}; cleanup=render(component);
if(element('survey').attrs.transform!=='translate(0 0)') throw Error('Offset leaked to another cutout size');
cleanup(); component.data=data; cleanup=render(component);
if(element('survey').attrs.transform!=='translate(50 25)') throw Error('Original target offset not restored');
cleanup();
'''
    subprocess.run([node, '-e', script], check=True, capture_output=True, text=True)


def test_obsolete_zoom_config_is_ignored(tmp_path):
    path = tmp_path/'config.toml'
    path.write_text('[equipment]\nframe_zoom=5\n')
    settings = load_settings(path)
    assert not hasattr(settings, 'frame_zoom')
    assert settings.camera_width_px == 6248 and settings.camera_height_px == 4176
