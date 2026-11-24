"""Execute chart initialization and clicks before the first ResizeObserver callback."""
from pathlib import Path
import shutil
import subprocess
import pandas as pd
import pytest
from interactive_chart import chart_html


def test_click_markers_exist_before_resize_and_survive_redraw(tmp_path):
    node=shutil.which('node')
    if not node:pytest.skip('Node required')
    frame=pd.DataFrame({'Time':pd.to_datetime(['2026-11-18T18:00Z','2026-11-19T06:00Z']),'Altitude (°)':[50,60],'Azimuth (°)':[90,100]})
    first=frame.Time[0].timestamp()*1000
    segments=[dict(start=first+i*14400000,end=first+(i+1)*14400000,percent=value) for i,value in enumerate([0,50,100])]
    content=chart_html(frame,40,'Europe/London',cloud_forecast=dict(segments=segments,precipitation_segments=segments), suggested_interval=dict(points=[first+3600000,first+7200000],message='Suggested interval selected.'))
    script=content.split('<script>')[1].split('</script>')[0]
    source=tmp_path/'chart.js';source.write_text(script)
    harness=r'''
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
class Element {
 constructor(){this.children=[];this.attrs={};this.handlers={};this.style={};this.checked=true;this.textContent='';}
 setAttribute(k,v){this.attrs[k]=v;}
 append(e){this.children.push(e);}
 replaceChildren(){this.children=[];}
 getBoundingClientRect(){return {left:0,top:0,width:900,height:335};}
 addEventListener(k,fn){this.handlers[k]=fn;}
}
const elements={};const get=id=>elements[id]??(elements[id]=new Element());
let resize;const events=[];
const ctx={Intl,console,document:{getElementById:get,createElement:()=>new Element(),createElementNS:()=>new Element()},sessionStorage:{getItem:()=>null,setItem:()=>{}},window:{parent:{postMessage:e=>events.push(e)}},ResizeObserver:class{constructor(cb){resize=cb;}observe(){}}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
const plot=get('plot');
const group=()=>plot.children.find(e=>e.attrs.id==='interval-lines');
const markers=()=>group().children.filter(e=>'data-boundary' in e.attrs);
assert.ok(group(),'marker layer must be created synchronously');
const clouds=()=>plot.children.filter(e=>'data-cloud-cover' in e.attrs);
const rain=()=>plot.children.filter(e=>'data-precip-probability' in e.attrs);
assert.equal(clouds().length,3);assert.equal(rain().length,3);
assert.equal(rain()[0].attrs.y-(clouds()[0].attrs.y+clouds()[0].attrs.height),4);
assert.deepEqual(clouds().map(e=>e.attrs.fill),['rgb(34,197,94)','rgb(251,191,36)','rgb(239,68,68)']);
assert.deepEqual(rain().map(e=>e.attrs.fill),clouds().map(e=>e.attrs.fill));
assert.ok(plot.children.some(a=>a.attrs.href==='https://open-meteo.com/en/docs'&&a.attrs.target==='_blank'&&a.children.some(e=>e.textContent==='Cloud'&&e.attrs.x<clouds()[0].attrs.x)));
assert.ok(plot.children.some(a=>a.attrs.href==='https://open-meteo.com/en/docs'&&a.attrs.rel==='noopener noreferrer'&&a.children.some(e=>e.textContent==='Precip.'&&e.attrs.x<rain()[0].attrs.x)));
plot.handlers.pointermove({clientX:200,clientY:320});
assert.match(get('tip').textContent,/Precipitation probability 0%/);
plot.handlers.pointermove({clientX:200,clientY:301});
assert.match(get('tip').textContent,/Cloud cover 0%/);
plot.handlers.pointermove({clientX:200,clientY:312});
assert.equal(get('tip').style.display,'none');
get('show-precip').checked=false;get('show-precip').onchange();
assert.equal(rain().length,0);assert.equal(clouds().length,3);
get('show-precip').checked=true;get('show-precip').onchange();
plot.handlers.click({clientX:200,clientY:100});
assert.equal(markers().length,1);
plot.handlers.pointermove({clientX:400,clientY:100});
assert.notEqual(get('duration').textContent,'—');
plot.handlers.click({clientX:600,clientY:100});
assert.equal(markers().length,2);
const duration=get('duration').textContent;
resize();assert.equal(markers().length,2);
plot.handlers.pointermove({clientX:700,clientY:100});
assert.equal(get('duration').textContent,duration);
assert.equal(events.at(-1).points.length,2);
assert.equal(get('choose-intervals').disabled,false);
get('choose-intervals').handlers.click();
assert.deepEqual(Array.from(events.at(-1).points),[Date.parse('2026-11-18T19:00Z'),Date.parse('2026-11-18T20:00Z')]);
assert.equal(markers().length,2);
get('clear-interval').handlers.click();
assert.equal(markers().length,0);
assert.equal(events.at(-1).points.length,0);
'''
    subprocess.run([node,'-e',harness,str(source)],check=True,capture_output=True,text=True)


def test_bridge_preserves_iframe_and_deduplicates_events():
    node=shutil.which('node')
    if not node:pytest.skip('Node required')
    source=Path(__file__).resolve().parents[1]/'chart_bridge.js'
    harness=r'''
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
let reloads=0;const child={};const listeners=new Set();const updates=[];
const frame={contentWindow:child,set srcdoc(value){reloads++;}};
const root={querySelector:()=>frame};
const ctx={window:{addEventListener:(_,fn)=>listeners.add(fn),removeEventListener:(_,fn)=>listeners.delete(fn)}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8').replace('export default function','function render'),ctx);
const triggers=[];
const component={parentElement:root,data:{html:'same chart'},setStateValue:(key,value)=>updates.push(value),setTriggerValue:(key,value)=>triggers.push({key,value})};
ctx.render(component);ctx.render(component);
assert.equal(reloads,1);assert.equal(listeners.size,1);
const receive=[...listeners][0];const event={source:child,data:{type:'mw-astro-interval',points:[1,2]}};
receive(event);receive(event);assert.equal(updates.length,1);
receive({source:{},data:{type:'mw-astro-clear-objects'}});assert.equal(triggers.length,0);
receive({source:child,data:{type:'mw-astro-clear-objects'}});
assert.deepEqual(triggers,[{key:'clear_objects',value:true}]);
component.data.html='changed chart';const cleanup=ctx.render(component);
assert.equal(reloads,2);cleanup();assert.equal(listeners.size,0);
'''
    subprocess.run([node,'-e',harness,str(source)],check=True,capture_output=True,text=True)


def test_comparison_path_keeps_primary_readout_and_interval_on_redraw(tmp_path):
    node=shutil.which('node')
    if not node:pytest.skip('Node required')
    frame=pd.DataFrame({'Time':pd.to_datetime(['2026-11-18T18:00Z','2026-11-19T06:00Z']),'Altitude (°)':[50,60],'Azimuth (°)':[90,100]})
    comparison=frame.assign(**{'Altitude (°)':[20,30]})
    content=chart_html(frame,40,'Europe/London',primary_name='A',comparison_frame=comparison,comparison_name='B')
    source=tmp_path/'comparison.js';source.write_text(content.split('<script>')[1].split('</script>')[0])
    harness=r'''
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
class Element {
 constructor(){this.children=[];this.attrs={};this.handlers={};this.style={};this.checked=true;this.textContent='';}
 setAttribute(k,v){this.attrs[k]=v;}
 append(e){this.children.push(e);}
 replaceChildren(){this.children=[];}
 getBoundingClientRect(){return {left:0,top:0,width:900,height:335};}
 addEventListener(k,fn){this.handlers[k]=fn;}
}
const elements={};const get=id=>elements[id]??(elements[id]=new Element());let resize;const events=[];
const saved=new Map();
const storage={get length(){return saved.size;},key:i=>Array.from(saved.keys())[i],getItem:key=>saved.get(key)??null,setItem:(key,value)=>saved.set(key,value),removeItem:key=>saved.delete(key)};
const ctx={Intl,console,document:{getElementById:get,createElement:()=>new Element(),createElementNS:()=>new Element()},sessionStorage:storage,window:{parent:{postMessage:e=>events.push(e)}},ResizeObserver:class{constructor(cb){resize=cb;}observe(){}}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
const plot=get('plot');
const secondary=()=>plot.children.filter(e=>e.attrs['data-secondary-target']==='B');
assert.equal(secondary().length,1);
assert.equal(secondary()[0].attrs.stroke,'#19b38c');
assert.equal(secondary()[0].attrs['stroke-dasharray'],'6 3');
assert.equal(get('comparison-legend').children[0].textContent,'A (Primary)');
assert.match(get('comparison-legend').children[1].textContent,/B/);
assert.match(get('alt').textContent,/50/);
plot.handlers.click({clientX:200,clientY:100});plot.handlers.click({clientX:400,clientY:100});
const interval=JSON.stringify(events.at(-1).points);resize();assert.equal(secondary().length,1);
assert.equal(JSON.stringify(events.at(-1).points),interval);
const duration=get('duration').textContent,images=get('images').textContent;
plot.handlers.click({clientX:600,clientY:100});
assert.equal(events.at(-1).points.length,3);
assert.equal(JSON.stringify(events.at(-1).points.slice(0,2)),interval);
assert.equal(get('duration').textContent,duration);assert.equal(get('images').textContent,images);
const markers=()=>plot.children.find(e=>e.attrs.id==='interval-lines').children.filter(e=>'data-boundary' in e.attrs);
assert.equal(markers().length,3);resize();assert.equal(markers().length,3);
get('show-object').checked=false;get('show-object').onchange();assert.equal(secondary().length,0);
get('show-object').checked=true;get('show-object').onchange();assert.equal(secondary().length,1);
// A rerun preserves all three markers, including the extra visual reference.
const script=fs.readFileSync(process.argv[1],'utf8');
vm.runInContext(script,vm.createContext({...ctx}));assert.equal(markers().length,3);
// Deselecting a target changes the revision and removes every saved interval.
saved.set('mw-astro-interval:0:another-target:1:2','[1,2]');
vm.runInContext(script.replace('"interval_revision": 0','"interval_revision": 1'),vm.createContext({...ctx}));
assert.equal(markers().length,0);
assert.ok(!Array.from(saved.keys()).some(key=>key.startsWith('mw-astro-interval:0:')));
plot.handlers.click({clientX:200,clientY:100});assert.equal(markers().length,1);
get('clear-objects').handlers.click();
assert.equal(markers().length,0);
assert.equal(events.at(-1).type,'mw-astro-clear-objects');
assert.ok(!Array.from(saved.keys()).some(key=>key.startsWith('mw-astro-interval:')));
'''
    result = subprocess.run([node,'-e',harness,str(source)],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
