import {errorText} from './readiness.js';

let pageSession=null, requestRevision=0, connectionGeneration=null;
export function setConnectionGeneration(value){if(value!==connectionGeneration){connectionGeneration=value;pageSession=null;++requestRevision;}}
export async function newSession(){
    const revision=++requestRevision;pageSession=null;
    const response=await fetch('/api/session',{method:'POST'});
    if(!response.ok)throw new Error('Could not create a fresh planner session');
    const value=await response.json();if(revision!==requestRevision)throw new Error('Superseded session discarded');connectionGeneration=value.generation??connectionGeneration;pageSession=value.session_id;return value;
}

export async function api(path, method='GET', body, {generationTimeoutMs=75000,signal}={}) {
    const session=pageSession, generation=connectionGeneration;
    const connectionRequest=path.startsWith('connections');
    const revision=method!=='GET'&&!connectionRequest?++requestRevision:requestRevision;
    const controller=['generate','return/prepare','course/compile'].includes(path)?new AbortController():null;
    const timer=controller?setTimeout(()=>controller.abort(),path==='course/compile'?10000:path==='return/prepare'?generationTimeoutMs+20000:generationTimeoutMs):null;
    try {
        const response=await fetch('/api/'+path, {
            method, headers:{'Content-Type':'application/json',...(session?{'X-Planner-Session':session}:{}),...(generation!==null&&!connectionRequest?{'X-Connection-Generation':String(generation)}:{})},
            body:body===undefined?undefined:JSON.stringify(body),
            ...((controller?.signal||signal)?{signal:controller?.signal||signal}:{})
        });
        let value;
        try {value=await response.json();}
        catch(error) {
            if(controller?.signal.aborted)throw error;
            throw new Error(`GCS returned HTTP ${response.status} without a readable response. Check the connection before retrying.`);
        }
        if(!response.ok) {
            const error=new Error(errorText(value.detail));
            error.detail=value.detail;error.errors=value.detail?.errors;throw error;
        }
        if(!connectionRequest&&(session!==pageSession||generation!==connectionGeneration||(method!=='GET'&&revision!==requestRevision)))throw new Error('Superseded response discarded; review current inputs.');
        return value;
    } catch(error) {
        if(controller?.signal.aborted)throw new Error('Planning request time limit reached; no route was received. Check the GCS connection before generating again.');
        throw error;
    } finally {
        if(timer!==null)clearTimeout(timer);
    }
}
