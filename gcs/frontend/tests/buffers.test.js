import test from 'node:test';
import assert from 'node:assert/strict';
import {gps,local,insetBoundary,expandedFootprint,crossingWindow} from '../src/buffers.js';
const ref={latitude:51.5,longitude:-4};
const point=xy=>{const [latitude,longitude]=gps(xy,ref);return {latitude,longitude};};
const box=[[0,0],[10,0],[10,10],[0,10]].map(point);
test('boundary preview reserves required room in either winding and detects no remaining room',()=>{
    for(const points of [box,[...box].reverse()]){
        const result=insetBoundary(points,2,ref).map(([latitude,longitude])=>local({latitude,longitude},ref));
        assert.equal(result.length,4);
        for(const [x,y]of result)assert.ok(x>=2-1e-7&&x<=8+1e-7&&y>=2-1e-7&&y<=8+1e-7);
        assert.deepEqual(insetBoundary(points,6,ref),[]);
    }
    assert.equal(insetBoundary([[0,0],[10,0],[3,3],[0,10]].map(point),2,ref),null);
});
test('polygon buffer expands physical surfaces and entry is a finite lateral window',()=>{
    const expanded=expandedFootprint(box,2,ref).map(([latitude,longitude])=>local({latitude,longitude},ref));
    assert.ok(Math.min(...expanded.map(p=>p[0]))<=-2);
    assert.ok(Math.max(...expanded.map(p=>p[1]))>=12);
    const window=crossingWindow({entry:point([5,5]),direction:[0,-1],entry_radius_m:1},'entry',ref).map(([latitude,longitude])=>local({latitude,longitude},ref));
    assert.ok(Math.abs(window[0][0]-4)<1e-7&&Math.abs(window[1][0]-6)<1e-7);
    assert.ok(window.every(p=>Math.abs(p[1]-5)<1e-7));
});
