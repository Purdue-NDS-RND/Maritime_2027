import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {local,gps} from '../src/buffers.js';
import {suggestBoundary,boundaryInputs,boundaryProblem,outsideBoundary} from '../src/planningBoundary.js';

const ref={latitude:51.566151,longitude:-4.034345};
const point=([x,y])=>{const [latitude,longitude]=gps([x,y],ref);return {latitude,longitude};};
const mapFrom=points=>({geographic_reference:ref,buoys:points.map((p,i)=>({id:String(i),type:'point',centre:point(p)}))});
const rotate=([x,y],a)=>[x*Math.cos(a)-y*Math.sin(a),x*Math.sin(a)+y*Math.cos(a)];
const projected=points=>points.map(p=>local(p,ref));
function insideWithRoom(p,corners,room){
    for(let i=0;i<corners.length;i++){
        const a=corners[i],b=corners[(i+1)%corners.length],dx=b[0]-a[0],dy=b[1]-a[1];
        assert.ok((dx*(p[1]-a[1])-dy*(p[0]-a[0]))/Math.hypot(dx,dy)>=room-1e-6,`point ${p} needs ${room} m at edge ${i}`);
    }
}
test('rectangle follows arbitrary course rotation and preserves padding on every side',()=>{
    for(const degrees of [0,17,43,89,121,217,312]){
        const angle=degrees*Math.PI/180;
        const points=[[0,0],[80,0],[80,12],[0,12],[22,8]].map(p=>rotate(p,angle));
        const map=mapFrom(points),corners=projected(suggestBoundary(map,7));
        for(const p of points)insideWithRoom(p,corners,7);
        const lengths=corners.map((p,i)=>Math.hypot(p[0]-corners[(i+1)%4][0],p[1]-corners[(i+1)%4][1])).sort((a,b)=>a-b);
        assert.ok(Math.abs(lengths[0]-26)<1e-6);
        assert.ok(Math.abs(lengths[3]-94)<1e-6);
        assert.equal(boundaryProblem(suggestBoundary(map,7),ref),'');
    }
});
test('full competition map stays enclosed after rotation, translation and outlying observations',()=>{
    const original=JSON.parse(fs.readFileSync('../examples/competition-gps-map.json'));
    for(const angle of [.23,.9,1.85,3.6]){
        const map=structuredClone(original);
        const transform=p=>{const [x,y]=rotate(local(p,ref),angle);return point([x+125,y-45]);};
        for(const obj of [...map.buoys,...map.obstacles]){
            obj.centre=transform(obj.centre);
            if(obj.footprint)obj.footprint=obj.footprint.map(transform);
        }
        map.stations=(map.stations||[]).map(s=>({...s,position:transform(s.position)}));
        if(map.start_pose)map.start_pose.position=transform(map.start_pose.position);
        map.buoys.push({id:'outlier',type:'point',centre:point([70,70])});
        const start=point([-90,-70]),before=JSON.stringify(map),corners=projected(suggestBoundary(map,10,start));
        for(const p of boundaryInputs(map,start))insideWithRoom(local(p,ref),corners,10);
        assert.equal(JSON.stringify(map),before,'suggesting never moves observations');
    }
});
test('physical footprints, circle surfaces, station annotations and known starts are enclosed',()=>{
    const map=mapFrom([[0,0]]);
    map.obstacles=[{type:'polygon',centre:point([10,0]),footprint:[[7,-8],[18,-8],[18,8],[7,8]].map(point)},{type:'cylinder',centre:point([-5,3]),radius_m:4}];
    map.stations=[{position:point([0,30])}];map.start_pose={position:point([-20,-10])};
    const start=point([30,-10]),corners=projected(suggestBoundary(map,3,start));
    for(const p of boundaryInputs(map,start))insideWithRoom(local(p,ref),corners,3);
    for(let i=0;i<360;i++)insideWithRoom([-5+4*Math.cos(i*Math.PI/180),3+4*Math.sin(i*Math.PI/180)],corners,3);
});
test('sparse and repeated observations still produce a real rectangle; invalid padding is rejected',()=>{
    for(const points of [[[0,0]],[[0,0],[0,0]],[[0,0],[12,4]],[[0,0],[6,2],[12,4]]]){
        const map=mapFrom(points),area=suggestBoundary(map,2);
        assert.equal(area.length,4);assert.equal(boundaryProblem(area,ref),'');
        for(const p of points)insideWithRoom(p,projected(area),2);
    }
    for(const padding of [null,NaN,Infinity,-1,0])assert.throws(()=>suggestBoundary(mapFrom([[0,0]]),padding),/greater than zero/);
});
test('manual boundary review detects crossings, overlapping corners and collapsed areas',()=>{
    for(const points of [[],[[0,0],[10,0]],[[0,0],[10,10],[0,10],[10,0]],[[0,0],[0,0],[10,10]],[[0,0],[10,0],[20,0]]])assert.ok(boundaryProblem(points.map(point),ref));
    assert.equal(boundaryProblem([[0,0],[10,0],[10,10],[5,5],[0,10]].map(point),ref),'');
});
test('later starts and corrected observations outside a fixed outline are identified without resizing it',()=>{
    const map=mapFrom([[0,0],[20,5]]),boundary=suggestBoundary(map,5),before=JSON.stringify(boundary);
    assert.equal(outsideBoundary(boundaryInputs(map,point([5,2])),boundary,ref),false);
    assert.equal(outsideBoundary([point([100,100])],boundary,ref),true);
    assert.equal(outsideBoundary(boundary,boundary,ref),false);
    assert.equal(JSON.stringify(boundary),before);
    const concave=[[0,0],[10,0],[10,10],[5,5],[0,10]].map(point);
    assert.equal(outsideBoundary([point([5,8])],concave,ref),true);
    assert.equal(outsideBoundary([point([5,2])],concave,ref),false);
});
