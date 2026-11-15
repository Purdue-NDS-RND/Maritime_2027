import test from 'node:test';
import assert from 'node:assert/strict';
import {isNavigation,untypedNavigation,sameRoles,displayColour} from '../src/mapReviewState.js';

test('classification shortcut includes only untyped red/green points',()=>{
    const objects=[
        {id:'r',type:'point',category:'red',object_type:'unknown'},
        {id:'g',type:'cylinder',category:'green'},
        {id:'tower',type:'point',category:'red',object_type:'detector'},
        {id:'obstacle',type:'point',category:'green',object_type:'obstacle'},
        {id:'blue',type:'point',category:'blue',object_type:'unknown'},
        {id:'polygon',type:'polygon',category:'red',object_type:'unknown'},
        {id:'typed',type:'point',category:'red',object_type:'buoy'}
    ];
    assert.deepEqual(untypedNavigation(objects).map(o=>o.id),['r','g']);
    assert.deepEqual(objects.filter(isNavigation).map(o=>o.id),['typed']);
});

test('confirmation belongs to exact roles, independent of property order',()=>{
    assert.ok(sameRoles({red:'a',green:'b'},{green:'b',red:'a'}));
    assert.ok(!sameRoles({red:'a',green:'b'},{red:'c',green:'b'}));
    assert.ok(!sameRoles({red:'a'},{red:'a',green:'b'}));
    assert.ok(!sameRoles(undefined,undefined));
});

test('unknown type overrides observed color without changing classification',()=>{
    for(const category of ['red','green','zebra','purple']) {
        const object={object_type:'unknown',category};
        assert.equal(displayColour(object,'#e74b50'),'#999');
        assert.equal(object.category,category);
    }
    assert.equal(displayColour({category:'red'},'#e74b50'),'#999');
    assert.equal(displayColour({object_type:'buoy',category:'red'},'#e74b50'),'#e74b50');
    assert.equal(displayColour({object_type:'detector'},'#bd79e4'),'#bd79e4');
});

test('quick buoy edits preserve identities and original observations',async()=>{
    const {canQuickEdit,moveMapObject,labelMapBuoy,BUOY_COLOURS}=await import('../src/mapReviewState.js');
    const original={id:'survey-1',type:'point',object_type:'unknown',category:'unknown',centre:{latitude:1,longitude:2},confidence:0.8};
    const map={buoys:[original],obstacles:[{id:'tower',type:'point',object_type:'detector',centre:{latitude:3,longitude:4}}]};
    const moved=moveMapObject(map,original.id,{latitude:5,longitude:6});
    const labeled=labelMapBuoy(moved,original.id,'green');
    assert.deepEqual(labeled.buoys[0],{...original,centre:{latitude:5,longitude:6},object_type:'buoy',category:'green'});
    assert.deepEqual(map.buoys[0],original);
    assert.deepEqual(map.buoys[0].centre,{latitude:1,longitude:2});
    assert.deepEqual(labelMapBuoy(map,'tower','red').obstacles,map.obstacles);
    assert.ok(canQuickEdit(original));
    assert.ok(canQuickEdit({...original,type:'cylinder',object_type:'buoy'}));
    assert.ok(!canQuickEdit({...original,type:'polygon'}));
    assert.ok(!canQuickEdit(map.obstacles[0]));
    assert.deepEqual(BUOY_COLOURS.slice(0,2),['red','green']);
});

test('moving docks and towers preserves shape, dimensions, labels and original map',async()=>{
    const {moveMapObject}=await import('../src/mapReviewState.js');
    const dock={id:'dock',type:'polygon',object_type:'dock',category:'brown',centre:{latitude:10,longitude:20},footprint:[{latitude:9,longitude:19},{latitude:11,longitude:19},{latitude:11,longitude:21}]};
    const tower={id:'tower',type:'cylinder',object_type:'detector',centre:{latitude:12,longitude:22},radius_m:2};
    const map={buoys:[],obstacles:[dock,tower]};
    const moved=moveMapObject(map,'dock',{latitude:12,longitude:23});
    assert.deepEqual(moved.obstacles[0].footprint,[{latitude:11,longitude:22},{latitude:13,longitude:22},{latitude:13,longitude:24}]);
    assert.equal(moved.obstacles[0].object_type,'dock');
    assert.deepEqual(dock.footprint[0],{latitude:9,longitude:19});
    assert.deepEqual(moveMapObject(map,'tower',{latitude:15,longitude:26}).obstacles[1],{...tower,centre:{latitude:15,longitude:26}});
    assert.deepEqual(moved.obstacles[1],tower);
});
