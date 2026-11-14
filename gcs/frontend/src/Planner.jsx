import React from 'react';
import RunBuilder from './RunBuilder';
import Configuration from './Configuration';
import MapReview from './MapReview';
import {DiagnosticList} from './Feedback';
import {reviewBlocks} from './readiness';
import {friendly} from './workflow';
export default function Planner(props) {
    const {workspace,draft,edit,mode,setMode,save,notify,load,step,setStep,selected,setSelected,onImport,loadCompetition,validation,action,busy,run,stale,status,dirty,operations,results,routeVisible,onFocusFailure}=props;
    const objects=[...(workspace.map?.buoys||[]),...(workspace.map?.obstacles||[])];
    const approved=routeVisible&&!!workspace.approval&&!dirty&&!workspace.run_consumed;
    const mission=workspace.approval?.envelope.mission.mission_id||(workspace.execution?.generation_identity===draft.generation_identity?workspace.execution?.mission_id:null);
    const uploaded=approved&&status?.mission_id===mission&&status?.state==='uploaded';
    const pending=operations.map(id=>results[id]).filter(r=>r&&r.mission_id===mission&&['pending','running'].includes(r.state)).at(-1);
    const blocks=reviewBlocks({draft,routeVisible,dirty,validation,approved,uploaded,stale,status,busy,pending,mission});
    const manual=false,competition=true;
    return <>
      <fieldset className={"step-content"+(step===3?" build-step":step===2?" configuration-step":step===1?" map-step":"")} disabled={busy}>
      {step===1&&<>
        {!workspace.map?<div className="map-entry-header"><span className="eyebrow">MAP PREPARATION</span><h2>Import your observations</h2><p>Load a survey, then check its objects before finding the course.</p><div className="button-row"><button onClick={loadCompetition}>Load full competition map</button><label className="button quiet">Import JSON / CSV<input aria-label="Import object map" type="file" accept=".json,.csv" onChange={onImport} hidden/></label></div></div>:<>
          <div className="map-entry-header compact-map-source"><strong>{objects.length} objects · {workspace.map.name||'Imported survey'}</strong><details><summary>Change map / source details</summary><div className="button-row"><button onClick={loadCompetition}>Load full competition map</button><label className="button quiet">Import JSON / CSV<input aria-label="Import object map" type="file" accept=".json,.csv" onChange={onImport} hidden/></label></div><p className="hint">Survey captured: {workspace.map.survey_time_source==='source'?(workspace.map.captured_at||'unknown'):'unknown / unverified'}. Imported: {workspace.map.imported_at||'unknown'}. {workspace.map.schema_version===3?'GPS map · unverified':'Simulator map'}.</p></details></div>
          <MapReview {...props}/>
        </>}
      </>}
      {step===2&&<Configuration {...props}/>}
      {step===3&&<RunBuilder {...props} selectedCard={props.selectedCard} onSelect={props.onTaskSelected}/>}
      {step===4&&<>
        <h2>{draft.planning_mode==='return'?'Review return to starting area':'Review & execute'}</h2>
        <p>Planning never moves the boat. Validate, Approve, Upload/readback and Start are separate actions.</p>
        {draft.planning_mode==='return'&&<p className="callout">Return target: {draft.return_target.latitude.toFixed(7)}, {draft.return_target.longitude.toFixed(7)} · 1 m stopping area. Select Loiter for armed replacement upload, or disarm outside Auto. Finish at ≤0.20 m/s for 5 seconds, then Loiter.</p>}
        {draft.planning_mode==='run'&&<div className="callout"><p>{draft.steps?.map((s,i)=>`${i+1}. ${friendly(s.type)} (${s.id.slice(0,8)})`).join(' → ')}</p><p>{draft.route_length_m?.toFixed(1)} m · nominal {Math.ceil(draft.nominal_travel_s||0)} s · suggested budget {draft.suggested_budget_s} s · budget {draft.execution_budget_s} s</p>{draft.blocks?.map(b=><p key={b.instance_id}>{b.instances.map(id=>id.slice(0,8)).join(' + ')} · waypoints {b.waypoint_start+1}–{b.waypoint_end} · {b.stopped_finish?'final stopped finish':'transit'}</p>)}<details><summary>Task and connector sections</summary>{draft.route_sections?.map((s,i)=><p key={i}>{s.instance_id.slice(0,8)} · {s.kind} · leg {s.leg+1}</p>)}</details><p>Estimated instance: {mission&&status?.mission_id===mission?(draft.blocks?.find(b=>(status?.current_item??0)>b.waypoint_start&&(status?.current_item??0)<=b.waypoint_end)?.instance_id?.slice(0,8)||'initial connector'):'not executing this draft'} · actual waypoint {status?.current_item??'unknown'} / {draft.waypoints.length}. {status?.detail}</p></div>}
        <div className="route-summary"><strong>{draft.waypoints.length} {draft.waypoints.length===1?'waypoint':'waypoints'}{draft.partial_attempt?' · Partial attempt':''}</strong><span title={draft.attempt?.captured_at}>{draft.attempt?.captured_at?`Start captured ${new Date(draft.attempt.captured_at).toLocaleTimeString()} · ${draft.attempt.start_source==='live'?'Live boat':'Manual start'}`:''}</span><span>{draft.speed_m_s} m/s · {draft.clearance_m} m required buffer</span><span>{dirty?'Edited draft · needs validation':approved?'Approved route':validation?.valid?'Validation passed':'Draft · needs validation'}</span></div>
        {!draft.waypoints.length&&<p className="callout">Use Edit on map to add waypoints, or generate a task route in Task setup.</p>}
        <button onClick={()=>{setStep(3);setMode('inspect');}}>Edit run cards</button>
        {draft.planning_notice&&<p className="callout warning">{draft.planning_notice}</p>}<DiagnosticList errors={validation?.errors||[]} onFocus={onFocusFailure}/>
        {(validation?.tower_shortfalls?.length>0||validation?.preferred_shortfalls?.length>0)&&<details className="preference-notes"><summary>Preferred clearance · {(validation?.tower_shortfalls?.length||0)+(validation?.preferred_shortfalls?.length||0)} notes</summary><p className="hint">Soft preferences may yield. These notes do not block approval when all mandatory checks pass.</p>{validation?.tower_shortfalls?.map(s=><p className="callout warning" key={`${s.leg}-${s.object_id}`}>Leg {s.leg+1}: {friendly(s.object_id)} · {s.clearance_m.toFixed(2)} m from the object point, inside its {s.preferred_m} m soft zone. Hard exclusion remains satisfied.</p>)}{validation?.preferred_shortfalls?.map(s=><p className="callout warning" key={s.leg}>Section {s.leg+1}: {s.clearance_m.toFixed(2)} m achieved clearance, below preferred.</p>)}</details>}
        <div className="review-actions"><div><button className="primary" disabled={!!blocks.validate} aria-describedby="validate-reason" onClick={()=>action('validate')}>1. Validate route</button>{blocks.validate&&<p className="action-reason" id="validate-reason">{blocks.validate}</p>}</div><div><button disabled={!!blocks.approve} aria-describedby="approve-reason" onClick={()=>action('approve')}>{approved?'2. Approved ✓':'2. Approve route'}</button>{blocks.approve&&<p className="action-reason" id="approve-reason">{blocks.approve}</p>}</div></div>
        <div className="vehicle-card"><div><strong>{stale?'Boat offline':'Boat connected'}</strong><span>{stale?'You can still plan and save. Connect the boat to upload.':status?.detail}</span></div><div className="review-actions"><div><button disabled={!!blocks.upload} aria-describedby="upload-reason" onClick={()=>action('upload')}>3. Upload to boat</button>{blocks.upload&&<p className="action-reason" id="upload-reason">{blocks.upload}</p>}</div><div><button className="start-button" disabled={!!blocks.start} aria-describedby="start-reason" onClick={()=>action('start')}>{manual?'4. Go':'4. Start mission'}</button>{blocks.start&&<p className="action-reason" id="start-reason">{blocks.start}</p>}</div></div></div>
        <details id="command-results"><summary>Command results</summary>{operations.slice(-8).reverse().map(id=><p className="operation" key={id}>{friendly(results[id]?.command||'Request')} · {results[id]?.state||'Waiting'} · {results[id]?.detail||id}</p>)}</details>
      </>}
      </fieldset>
    </>;
}

export function WorkflowNav({step,setStep,setMode,busy,workspace,routeVisible}) {
    return <nav className="workflow-nav" aria-label="Planning views">{[[1,'Map','Review the course'],[2,'Configure','Shared distances & limits'],[3,'Build run','Tasks & assignments'],[4,'Review & execute','Route & boat commands']].map(([n,label,description])=><button key={n} aria-current={step===n?'page':undefined} disabled={busy||(!workspace.map&&n!==1)||(n===4&&!routeVisible)} onClick={()=>{setStep(n);setMode('inspect');}}><b>{String(n).padStart(2,'0')}</b><span><strong>{label}</strong><small>{description}</small></span></button>)}</nav>;
}
