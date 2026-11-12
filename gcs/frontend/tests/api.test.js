import test from 'node:test';
import assert from 'node:assert/strict';
import {api} from '../src/api.js';

test('stalled generation requests fail visibly and can be retried explicitly',async t=>{
    let calls=0;
    t.mock.method(globalThis,'fetch',async(_url,{signal})=>{
        calls++;
        return new Promise((_resolve,reject)=>signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError'))));
    });
    await assert.rejects(api('generate','POST',undefined,{generationTimeoutMs:10}),/Planning request time limit.*no route was received/);
    assert.equal(calls,1);
    t.mock.method(globalThis,'fetch',async()=>({ok:true,json:async()=>({success:true})}));
    assert.deepEqual(await api('generate','POST'),{success:true});
});

test('generation timeout also covers a stalled response body',async t=>{
    t.mock.method(globalThis,'fetch',async(_url,{signal})=>({ok:true,json:()=>new Promise((_resolve,reject)=>{
        signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')));
    })}));
    await assert.rejects(api('generate','POST',undefined,{generationTimeoutMs:10}),/Planning request time limit/);
});

test('structured errors and mission command outcome handling are preserved',async t=>{
    const detail={errors:[{reason:'unsafe finish area',location:[1,2]}]};
    t.mock.method(globalThis,'fetch',async(_url,options)=>{
        assert.equal(options.signal,undefined);
        return {ok:false,json:async()=>({detail})};
    });
    await assert.rejects(api('start','POST'),error=>{
        assert.equal(error.message,'unsafe finish area');
        assert.deepEqual(error.errors,detail.errors);
        return true;
    });
});

test('late generation is discarded after a newer reset and page-session headers stay in memory',async t=>{
    const {newSession}=await import('../src/api.js');
    let release;
    t.mock.method(globalThis,'fetch',async(url,options)=>{
        if(url==='/api/session')return {ok:true,json:async()=>({session_id:'page-only'})};
        assert.equal(options.headers['X-Planner-Session'],'page-only');
        if(url==='/api/generate')return new Promise(resolve=>release=()=>resolve({ok:true,json:async()=>({draft:'old'})}));
        return {ok:true,json:async()=>({map:null})};
    });
    await newSession();const pending=api('generate','POST');await api('reset','POST');release();
    await assert.rejects(pending,/Superseded response discarded/);
});

test('connection revisions discard old status and planner responses while profile tests retain planning requests',async t=>{
    const {newSession,setConnectionGeneration}=await import('../src/api.js');
    let release;
    t.mock.method(globalThis,'fetch',async(url,options)=>{
        if(url==='/api/session')return {ok:true,json:async()=>({session_id:'generation-test',generation:2})};
        if(url==='/api/status'){
            assert.equal(options.headers['X-Connection-Generation'],'2');
            return new Promise(resolve=>release=()=>resolve({ok:true,json:async()=>({state:'old'})}));
        }
        assert.equal(options.headers['X-Connection-Generation'],undefined);
        return {ok:true,json:async()=>({reachable:true})};
    });
    await newSession();const old=api('status');
    await api('connections/test','POST',{revision:0,boat_url:'http://candidate'});
    setConnectionGeneration(3);release();
    await assert.rejects(old,/Superseded response discarded/);
});

test('operation reads forward cancellation to fetch', async t => {
    const controller = new AbortController();
    t.mock.method(globalThis, 'fetch', async (_url, {signal}) => {
        assert.equal(signal, controller.signal);
        return new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))));
    });
    const pending = api('operations/example', 'GET', undefined, {signal: controller.signal});
    controller.abort();
    await assert.rejects(pending, {name: 'AbortError'});
});
