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
