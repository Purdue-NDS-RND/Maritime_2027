import {errorText} from './readiness.js';

export async function api(path, method='GET', body, {generationTimeoutMs=75000}={}) {
    const controller=path==='generate'?new AbortController():null;
    const timer=controller?setTimeout(()=>controller.abort(),generationTimeoutMs):null;
    try {
        const response=await fetch('/api/'+path, {
            method, headers:{'Content-Type':'application/json'},
            body:body===undefined?undefined:JSON.stringify(body),
            ...(controller?{signal:controller.signal}:{})
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
        return value;
    } catch(error) {
        if(controller?.signal.aborted)throw new Error('Planning request time limit reached; no route was received. Check the GCS connection before generating again.');
        throw error;
    } finally {
        if(timer!==null)clearTimeout(timer);
    }
}
