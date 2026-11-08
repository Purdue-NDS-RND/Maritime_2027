import React from 'react';

export default function BoatControls({status,stale,action,returnTarget,onReturn,operations=[],results={}}) {
    const armed=!stale&&status?.armed===true;
    const hold=!stale&&status?.mode===4;
    const stopped=Number.isFinite(status?.speed_m_s)&&status.speed_m_s<=0.2;
    const latest=operations.map(id=>results[id]).filter(r=>r&&['stop','disarm'].includes(r.command)).at(-1);
    const pending=latest&&['pending','running'].includes(latest.state);
    const canDisarm=armed&&hold&&stopped&&!pending;
    const mode=stale?'Unknown':({0:'Manual',4:'Hold',10:'Auto',15:'Guided'}[status?.mode]??`Mode ${status?.mode??'unknown'}`);
    let guidance='Go / Start arms automatically after checking the uploaded route.';
    if(stale)guidance='Waiting for fresh boat status. Controls require a live connection.';
    else if(armed&&!hold)guidance='To upload another route: Hold / Stop, wait for the boat to settle, then Disarm.';
    else if(armed&&!stopped)guidance='Wait for reported speed to fall to 0.20 m/s or less, then Disarm.';
    else if(armed)guidance='Ready to Disarm before uploading your next route. Go / Start will arm automatically.';
    return <section className="boat-controls" aria-label="Boat controls">
        <div className="boat-controls-main">
            <div className="boat-controls-title"><span className="eyebrow">VEHICLE</span><h2>Boat controls</h2><span className={`arm-state ${stale?'unknown':armed?'armed':'disarmed'}`}><span aria-hidden="true">●</span> {stale?'Status unavailable':armed?'Armed':'Disarmed'}</span></div>
            <dl className="boat-metrics"><div><dt>Mode</dt><dd>{mode}</dd></div><div><dt>Speed</dt><dd>{stale||!Number.isFinite(status?.speed_m_s)?'—':`${status.speed_m_s.toFixed(2)} m/s`}</dd></div><div><dt>GPS fix</dt><dd>{stale?'—':status?.gps_fix??'—'}</dd></div></dl>
            <div className="boat-control-actions"><button className="quiet" disabled={stale} onClick={()=>action('stop')}>Hold / Stop</button><button disabled={!returnTarget} onClick={onReturn} title={returnTarget?"Stop and prepare a reviewed return to the frozen run start":"Start a run successfully in this page session to establish a target"}>Return now</button><button className="disarm-button" disabled={!canDisarm&&!(returnTarget&&!stale&&status?.armed===false&&hold&&stopped)} onClick={()=>action('disarm')}>{!stale&&status?.armed===false?'Disarmed ✓':'Disarm'}</button><details className="boat-help"><summary>Help</summary><div><p>{guidance}</p><p>Upload requires a disarmed boat outside Auto. Disarm requires Hold and reported speed ≤ 0.20 m/s. Start checks the mission, selects Auto and requests arming. A completed route ends in Hold and may remain armed.</p></div></details></div>
        </div>

        {latest&&<p className={`boat-command ${latest.state==='failed'?'command-failed':''}`} role="status">Previous command result: {latest.command==='stop'?'Hold / Stop':'Disarm'} · {latest.state}{latest.detail?` · ${latest.detail}`:''}</p>}
    </section>;
}
