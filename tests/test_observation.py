"""Execute the actual browser calculation code with Node, without a DOM."""
from pathlib import Path
import shutil
import subprocess
import pytest


def test_browser_interval_calculations():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node is required for the browser calculation test.')
    module = Path(__file__).resolve().parents[1]/'observation.js'
    script = r'''
const assert=require('node:assert/strict');
const p=require(process.argv[1]);
const start=Date.parse('2026-10-24T23:00:00Z');
const end=start+12*3600000;
let points=p.select([],start,start,end);
assert.equal(p.summary(points,180),null);
points=p.select(points,start+3600000,start,end);
assert.deepEqual(p.summary(points,180),{seconds:3600,images:20});
assert.deepEqual(p.summary(points,240),{seconds:3600,images:15});
assert.deepEqual(p.summary([...points].reverse(),180),{seconds:3600,images:20});
assert.deepEqual(p.summary([start,start],180),{seconds:0,images:0});
assert.deepEqual(p.summary([start,start+179000],180),{seconds:179,images:0});
assert.deepEqual(p.summary([start,start+181000],180),{seconds:181,images:1});
// UTC elapsed time stays correct over midnight and the autumn clock change.
assert.equal(p.summary([start,start+4*3600000],180).seconds,14400);
assert.equal(p.duration(14461),'04:01:01');
assert.equal(p.duration(25*3600),'25:00:00');
assert.deepEqual(p.select(points,start+1000,start,end),[start+1000]);
assert.deepEqual(p.select(points,end+1,start,end),points);
assert.deepEqual(p.restore(JSON.stringify(points),start,end),points);
assert.deepEqual(p.restore('bad',start,end),[]);
assert.deepEqual(p.restore(JSON.stringify([end+1]),start,end),[]);
assert.deepEqual(p.summary([start],300,start+11100000),{seconds:11100,images:37});
assert.deepEqual(p.summary([start],300,start+600000),{seconds:600,images:2});
assert.deepEqual(p.summary([start,start+3600000],300,start+7200000),{seconds:3600,images:12});
assert.deepEqual(p.summary([],300,start+600000),null);
assert.throws(()=>p.summary(points,0));
assert.throws(()=>p.summary(points,NaN));
'''
    subprocess.run([node,'-e',script,str(module)],check=True,capture_output=True,text=True)
