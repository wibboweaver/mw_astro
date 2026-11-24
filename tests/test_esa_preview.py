from pathlib import Path
import shutil
import subprocess

import pytest
from esa_preview import esa_preview_data


def test_payload_has_independent_survey_and_tangent_plane_geometry():
    data=esa_preview_data(10,40,1000,36,24,5,30,6000,4000,'target')
    assert data['survey']=='https://skies.esac.esa.int/DSSColor'
    assert 'aladin-lite@3.8.2/' in data['module_url']
    assert 'image' not in data
    assert data['width']/data['height']==pytest.approx(1.5)
    assert data['image_field']==5 and data['rotation']==30
    assert data['pixel_scale_width']==pytest.approx(1.23758884)
    assert data['pixel_scale_height']==pytest.approx(data['pixel_scale_width'])


def test_hidden_tab_waits_for_visibility_and_viewers_keep_separate_state(tmp_path):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for component interaction tests')
    source = Path(__file__).resolve().parents[1].joinpath('esa_preview.js').read_text()
    source = source.replace('export default function(component)', 'function render(component)')
    source = source.replace('await loadAladin(state.data.module_url)', 'await mockLoad()')
    harness = r'''
const assert=require('node:assert/strict');
const observers=[],viewers=[],storage=new Map();
const sessionStorage={getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
class ResizeObserver{
 constructor(callback){this.callback=callback;observers.push(this);}
 observe(element){this.element=element;}
 disconnect(){this.disconnected=true;}
}
function root(width){
 const elements=new Map(),box={width};
 box.find=id=>{
  if(!elements.has(id))elements.set(id,{attrs:{},style:{setProperty(){}},classList:{toggle(){}},
   setAttribute(k,v){this.attrs[k]=v},getBoundingClientRect:()=>({width:box.width,height:400}),
   addEventListener(){},appendChild(){},showModal(){this.open=true},close(){this.open=false;}});
  return elements.get(id);
 };
 box.querySelector=selector=>box.find(selector.slice(1));return box;
}
const A={imageHiPS:url=>url,aladin:(element,options)=>{
 const viewer={position:[],fields:[],gotoRaDec(...position){this.position=position},getRaDec(){return this.position},
  setFoV(value){this.fields.push(value)},setFoVRange(){},setRotation(){},on(){}};
 viewers.push(viewer);return viewer;
}};
const mockLoad=async()=>A,fetch=async()=>({ok:true});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
const data={ra:10,dec:40,survey:'survey',module_url:'module',pixel_scale_width:1,pixel_scale_height:1,
 image_field:5,width:300,height:200,fov_width:2,fov_height:1,rotation:0,camera_width_px:6000,camera_height_px:4000,view_key:'A'};
'''
    checks = r'''
(async()=>{
 const first=root(400),second=root(0),events=[[],[]];
 const primary={parentElement:first,data,setStateValue:(...value)=>events[0].push(value)};
 const comparison={parentElement:second,data:{...data,ra:20,dec:50,view_key:'B'},setStateValue:(...value)=>events[1].push(value)};
 const cleanupFirst=render(primary),cleanupSecond=render(comparison);await flush();
 assert.equal(viewers.length,1,'hidden preview must not initialise at zero width');
 assert.deepEqual(viewers[0].position,[10,40]);
 assert.equal(events[1].length,0);
 second.width=400;observers[1].callback();await flush();
 assert.equal(viewers.length,2);assert.deepEqual(viewers[1].position,[20,50]);
 assert.deepEqual(events[0].at(-1),['centre',{view_key:'A',ra:10,dec:40}]);
 assert.deepEqual(events[1].at(-1),['centre',{view_key:'B',ra:20,dec:50}]);
 events[0].length=0;events[1].length=0;
 second.find('angle').value=85;second.find('angle').oninput();second.find('angle').onchange();
 assert.deepEqual(events[1],[['rotation',85]]);assert.equal(events[0].length,0);
 assert.equal(first.find('camera-frame').attrs.transform,'rotate(0 300 300)');
 observers[1].callback();await flush();assert.equal(viewers.length,2);
 cleanupSecond();cleanupFirst();assert.ok(observers.every(observer=>observer.disconnected));
})().catch(error=>{console.error(error);process.exit(1)});
'''
    script = tmp_path / 'tabs.js'
    script.write_text(harness + source + checks)
    result = subprocess.run([node, str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('ra,dec',[(float('nan'),0),(360,0),(-1,0),(10,91),(10,float('inf'))])
def test_invalid_coordinates_are_rejected(ra,dec):
    with pytest.raises(ValueError):
        esa_preview_data(ra,dec,1000,36,24,5,0,6000,4000,'target')


def test_viewer_lifecycle_rotation_pan_and_retry():
    node=shutil.which('node')
    if not node:
        pytest.skip('Node is required for component interaction tests')
    source=Path(__file__).resolve().parents[1].joinpath('esa_preview.js').read_text()
    source=source.replace('export default function(component)','function render(component)')
    source=source.replace('await loadAladin(state.data.module_url)','await mockLoad()')
    harness='''
const assert=require('node:assert/strict');
const elements=new Map(), events=[], positions=[], storage=new Map();
const sessionStorage={getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
function element(id){if(!elements.has(id))elements.set(id,{attrs:{},style:{setProperty(k,v){this[k]=v}},classList:{toggle(){}},setAttribute(k,v){this.attrs[k]=v},getBoundingClientRect:()=>({height:400}),appendChild(child){child.parent=this},showModal(){this.open=true},close(){this.open=false;this.onclose?.()},addEventListener(){}});return elements.get(id);}
const root={querySelector:s=>element(s.slice(1))};
let creations=0, failLoad=true, providerOkay=true, resets=0, callbacks={},fields=[],rotations=[];
const viewer={gotoRaDec:(...p)=>positions.push(p),setFoV:v=>fields.push(v),setRotation:v=>rotations.push(v),setFoVRange(){},on:(k,cb)=>callbacks[k]=cb,getRaDec:()=>[12,45],setBaseImageLayer(){resets++}};
const A={imageHiPS:(url)=>url,aladin:(el,options)=>{creations++;assert.equal(options.projection,'TAN');assert.equal(options.survey,'https://skies.esac.esa.int/DSSColor');return viewer;}};
const mockLoad=async()=>{if(failLoad)throw Error('Library unavailable');return A;};
const fetch=async()=>({ok:providerOkay});
const data={ra:10,dec:40,survey:'https://skies.esac.esa.int/DSSColor',module_url:'module',pixel_scale_width:1.24,pixel_scale_height:1.24,image_field:5,width:300,height:200,fov_width:2,fov_height:1,rotation:0,camera_width_px:6000,camera_height_px:4000,view_key:'A'};
const component={parentElement:root,data,setStateValue:(...v)=>events.push(v)};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
console.error=()=>{};
'''
    checks='''
(async()=>{
let cleanup=render(component);await flush();
assert.equal(element('retry').hidden,false);
failLoad=false;await element('retry').onclick();
assert.equal(creations,1);assert.equal(element('status').textContent,'');
assert.deepEqual(positions.at(-1),[10,40]);
callbacks.positionChanged();
await new Promise(resolve=>setTimeout(resolve,300));
assert.deepEqual(events.at(-1),['centre',{view_key:'A',ra:12,dec:45}]);
events.length=0;
render(component);await flush();
assert.equal(creations,1);assert.equal(positions.length,1,'rerun must preserve pan');
element('angle').value=80;element('angle').oninput();
assert.equal(element('camera-frame').attrs.transform,'rotate(-80 300 300)');
assert.equal(element('dimensions').attrs.y,417);
assert.equal(element('frame-fov').attrs.x,150);
assert.equal(element('frame-resolution').textContent,'Resolution: 6000 × 4000 pixels');
assert.equal(element('frame-scale').textContent,'Scale: 1.24 arcsec/pixel');assert.equal(events.length,0);
element('angle').onchange();assert.deepEqual(events,[['rotation',80]]);
const panCount=positions.length;
for(const factor of [.75,.5,.33]){
 element('crop').value=String(factor);element('crop').onchange();
 const expected=2*Math.atan(Math.tan(data.fov_width*Math.PI/360)*factor)*180/Math.PI;
 assert.ok(Math.abs(fields.at(-1)-expected)<1e-10,'crop FOV must use tangent-plane scale');
 assert.equal(element('overlay').style.display,'none');
 assert.equal(element('sky-frame').style.aspectRatio,'300 / 200');
 assert.ok(element('crop-details').textContent.includes(`${Math.floor(6000*factor)} × ${Math.floor(4000*factor)} pixels`));
 assert.equal(rotations.at(-1),-80,'crop must align the sky with the camera orientation');
}
assert.equal(positions.length,panCount,'changing crop must preserve framing centre');
assert.equal(creations,1,'changing crop must reuse the existing viewer');
component.data={...data,rotation:80};render(component);await flush();
assert.equal(element('crop').value,'0.33','crop must survive an app rerun');
assert.equal(element('crop-details').textContent.includes('2.6 MP'),true);
element('crop').value='1';element('crop').onchange();
assert.equal(element('overlay').style.display,'');assert.equal(fields.at(-1),5);
assert.equal(rotations.at(-1),360,'return to north-up even when library ignores zero');
assert.equal(element('sky-frame').style.aspectRatio,'1');
assert.equal(positions.length,panCount);
element('crop').value='0.5';element('crop').onchange();
const cropField=fields.at(-1),createCount=creations;
element('enlarge').onclick();
assert.equal(element('large-view').open,true);
assert.equal(element('sky-frame').parent,element('large-slot'));
assert.equal(element('large-details').textContent,element('crop-details').textContent);
assert.equal(fields.at(-1),cropField);assert.equal(creations,createCount);
assert.equal(positions.length,panCount,'enlarging must preserve framing');
element('close-large').onclick();
assert.equal(element('large-view').open,false);
assert.equal(element('sky-frame').parent,element('preview-home'));
assert.equal(element('preview-home').style.height,'');
element('enlarge').onclick();element('large-view').close();
assert.equal(element('sky-frame').parent,element('preview-home'),'Escape/close must return the viewer');

component.data={...data,view_key:'B',ra:20};render(component);await flush();
assert.equal(creations,1);assert.deepEqual(positions.at(-1),[20,40]);
component.data=data;render(component);await flush();
assert.deepEqual(positions.at(-1),[12,45],'returning to target must restore pan');
element('centre').onclick();assert.deepEqual(positions.at(-1),[10,40]);
providerOkay=false;await element('retry').onclick();
assert.equal(element('retry').hidden,false);assert.match(element('status').textContent,/could not load/);
providerOkay=true;await element('retry').onclick();assert.equal(resets,1);assert.equal(element('retry').hidden,true);
cleanup();render(component);await flush();assert.equal(creations,2);
cleanup();
})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});
'''
    subprocess.run([node,'-e',harness+source+checks],check=True,capture_output=True,text=True)
