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
    content=chart_html(frame,40,'Europe/London')
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
const ctx={Intl,console,document:{getElementById:get,createElementNS:()=>new Element()},sessionStorage:{getItem:()=>null,setItem:()=>{}},window:{parent:{postMessage:e=>events.push(e)}},ResizeObserver:class{constructor(cb){resize=cb;}observe(){}}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
const plot=get('plot');
const group=()=>plot.children.find(e=>e.attrs.id==='interval-lines');
const markers=()=>group().children.filter(e=>'data-boundary' in e.attrs);
assert.ok(group(),'marker layer must be created synchronously');
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
const component={parentElement:root,data:{html:'same chart'},setStateValue:(key,value)=>updates.push(value)};
ctx.render(component);ctx.render(component);
assert.equal(reloads,1);assert.equal(listeners.size,1);
const receive=[...listeners][0];const event={source:child,data:{type:'mw-astro-interval',points:[1,2]}};
receive(event);receive(event);assert.equal(updates.length,1);
component.data.html='changed chart';const cleanup=ctx.render(component);
assert.equal(reloads,2);cleanup();assert.equal(listeners.size,0);
'''
    subprocess.run([node,'-e',harness,str(source)],check=True,capture_output=True,text=True)
