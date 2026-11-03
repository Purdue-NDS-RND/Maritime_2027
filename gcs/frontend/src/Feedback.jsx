import React from 'react';
import {explainFailure} from './readiness';

export function DiagnosticList({errors=[],onFocus}) {
    return <div className="diagnostic-list">{errors.map((error,i)=>{
        const info=explainFailure(error.reason);
        return <article className="diagnostic" key={i}><strong>{info.title}</strong><p>{error.reason}</p>{error.objects?.length>0&&<p className="conflict-objects">Objects: {error.objects.map(id=>id.replaceAll('_',' ')).join(', ')}</p>}<p className="hint">{info.next}</p>{error.location&&<button className="quiet" onClick={()=>onFocus?.(error)}>Locate on map</button>}</article>;
    })}</div>;
}
export function Readiness({checks,onResolve,busy,failed=false}) {
    const remaining=checks.filter(check=>!check.ready);
    return <section className={`readiness ${remaining.length||failed?'':'ready'}`} aria-label="Generation readiness">
        <div className="readiness-heading"><strong>{remaining.length?`${remaining.length} ${remaining.length===1?'step':'steps'} before Generate`:failed?'Last generation failed':'Ready to generate'}</strong><span>{checks.length-remaining.length}/{checks.length}</span></div>
        {remaining.length?<ul>{remaining.map(check=><li key={check.id}><span className="readiness-marker" aria-hidden="true">○</span><div><strong>{check.label}</strong><p>{check.detail}</p><button className="text-button" disabled={busy} onClick={()=>onResolve(check)}>{check.step===1?'Review map':check.step===2?'Open Configure':check.action==='geometry'?'Review geometry':check.action==='start'?'Choose start source':check.action==='remaining'?'Review partial selection':check.action==='confirm'?'Go to confirmation':'Review assignments'}</button></div></li>)}</ul>:<p>{failed?'Review the reported conflict, then retry. Generate captures and checks the start again.':'Setup checks passed. The captured start and route are checked during generation; review the result before approving.'}</p>}
    </section>;
}
export default function Feedback({notice,busy,label,elapsed,onDismiss,onReview,onFocus}) {
    if(!notice&&!busy)return null;
    const error=notice?.kind==='error';
    const info=error?{...explainFailure(notice),...(notice.title?{title:notice.title}:{}),...(notice.next?{next:notice.next}:{}),...(notice.step?{step:notice.step}:{})}:null;
    return <section className={`workspace-notice ${error?'notice-error':''} ${busy?'notice-busy':''}`} role={error?'alert':'status'} aria-label="Workspace feedback">
        <span className={busy?'activity-spinner':'notice-symbol'} aria-hidden="true">{busy?'':error?'!':'✓'}</span>
        <div><strong>{busy?label||'Working…':info?.title||'Workspace update'}</strong><p>{busy?`${elapsed}s elapsed${label==='Generating route'?' · Search and validation share a 60-second limit.':''}`:info?.text||notice?.text}</p>{error&&!busy&&<><p className="hint">{info.next}</p><div className="button-row"><button className="quiet" onClick={()=>onReview(info.step)}>{notice.reviewLabel||'Review setup'}</button>{notice.errors?.some(e=>e.location)&&<button className="quiet" onClick={()=>onFocus(notice.errors.find(e=>e.location))}>Locate on map</button>}</div></>}</div>
        {!busy&&<button className="dismiss-notice" aria-label="Dismiss feedback" onClick={onDismiss}>×</button>}
    </section>;
}
