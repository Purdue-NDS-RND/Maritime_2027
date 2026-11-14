import React,{useState} from 'react';
import {settingsError} from './settings';
import {TASKS,friendly,heading} from './workflow';
export default function Competition({workspace,draft,edit,load,save,run,notify,busy,stale,setMode,onGenerated,changeWorkspace,setStep,invalidateRoute=()=>{}}) {
    const [relationship,setRelationship]=useState(null);
    function update(changes){
        invalidateRoute();setRelationship(null);
        const next={...draft,review_geometry:null,...changes,waypoints:[],generation_identity:null};
        const final=next.task_setup?.[next.selected_tasks?.at(-1)];
        if(final){next.finish=final.finish;next.finish_radius_m=final.finish_radius_m;}
        edit(next);
    }
    const tasks=draft.selected_tasks||[];
    const settings=draft.settings||{};
    const overrides=settings.tower_avoidance?.overrides||{};
    const error=settingsError({version:1,...settings,task_overrides:{}}).replace('(Shared course settings)','(Competition run)')||(!Number.isFinite(draft.execution_budget_s)||draft.execution_budget_s<10||draft.execution_budget_s>7200?'Execution budget must be within 10–7200 seconds.':'');
    const ready=tasks.length>0&&tasks.every(t=>draft.task_setup?.[t]?.course_confirmed&&draft.task_setup?.[t]?.sizes_confirmed);
    return <section aria-label="Competition run setup">
      <h3>Complete tasks in standard order</h3>
      <p>Generate one route, upload once, and stop at the final finish. Interrupted runs require a newly generated and approved full run.</p>
      {TASKS.filter(t=>t.id!=='manual').map(t=><label className="check-card" key={t.id}><input type="checkbox" checked={tasks.includes(t.id)} onChange={e=>update({selected_tasks:TASKS.filter(x=>x.id!=='manual'&&(x.id===t.id?e.target.checked:tasks.includes(x.id))).map(x=>x.id),share_gate:false})}/>{t.title}</label>)}
      <p>Run settings start from shared course settings. Individual task overrides apply only to separate missions.</p>
      {[['speed_m_s','Run speed (m/s)'],['clearance_m','Hard point buffer (m)'],['preferred_buffer_m','Preferred point buffer (m)']].map(([key,label])=><label key={key}>{label}<input type="number" step="0.1" value={settings[key]??''} onChange={e=>update({settings:{...settings,[key]:Number(e.target.value)}})}/></label>)}
      {['hard_m','soft_m','strength'].map(key=><label key={key}>Towers · {friendly(key)}<input type="number" step="0.1" value={settings.tower_avoidance?.[key]??''} onChange={e=>update({settings:{...settings,tower_avoidance:{...settings.tower_avoidance,[key]:Number(e.target.value)}}})}/></label>)}
      {Object.keys(overrides).length>0&&<details><summary>Individual tower zones for this run · {Object.keys(overrides).length}</summary><p>These shared tower zones were copied into the run and take precedence over its common tower distances.</p>{Object.entries(overrides).map(([id,zones])=><div key={id}><strong>{friendly(id)}</strong>{['hard_m','soft_m'].map(key=><label key={key}>{friendly(key)}<input type="number" step="0.1" value={zones[key]} onChange={e=>update({settings:{...settings,tower_avoidance:{...settings.tower_avoidance,overrides:{...overrides,[id]:{...zones,[key]:Number(e.target.value)}}}}})}/></label>)}<button onClick={()=>{const next={...overrides};delete next[id];update({settings:{...settings,tower_avoidance:{...settings.tower_avoidance,overrides:next}}});}}>Use common run distances</button></div>)}</details>}
      <label>Start source<select value={draft.attempt?.start_source||'live'} onChange={e=>update({attempt:{mode:'full',start_source:e.target.value}})}><option value="live">Live boat</option><option value="manual">Manual start (offline)</option></select></label>
      {draft.attempt?.start_source==='manual'&&<button onClick={()=>setMode('start')}>Choose manual start on map</button>}
      <p className="hint">{stale?'Live position unavailable or stale.':'A fresh boat position is captured at Generate.'} Position and heartbeat must both be at most 3 seconds old.</p>
      <h3>Common planning boundary · {draft.planning_area?.length||0} corners</h3>
      <div className="button-row"><button onClick={()=>setMode('planning_area')}>Add boundary corners</button><button onClick={()=>update({planning_area:[]})}>Clear boundary</button></div>
      <button onClick={()=>update({task_setup:structuredClone(workspace.course||{}),share_gate:false})}>Refresh from reviewed single-task setups</button>
      <button disabled={!tasks.length} onClick={()=>run(async()=>{await save();const geometry=await load('run/geometry','POST',draft);update({review_geometry:geometry});notify('Review each task’s local arrows, channel sections and transit/final finish on the map.');})}>Review run geometry on map</button>
      {tasks.map(task=>{const setup=draft.task_setup?.[task];return <details key={task} open={!setup?.course_confirmed}><summary>Review {friendly(task)} assignments {setup?.course_confirmed?'✓':''}</summary>{!setup?<p className="callout">Set up this task in Single task mode first. Reviewed assignments are required; saved waypoints are never used.</p>:<>
        <p>Travel: {heading(setup.direction)}. Local passage directions follow the reviewed progression and overrides.</p>
        <p>{setup.passages?.map(p=>`${p.id}: ${p.red||p.buoy} ${p.green||p.side||''}`).join(' → ')}</p>
        {setup.channel_chains&&<p>Left: {setup.channel_chains.left.join(' → ')}<br/>Right: {setup.channel_chains.right.join(' → ')}</p>}
        <p>{task==='gate'&&draft.share_gate?'Shared with Slalom; no separate Gate finish waypoint.':<>Finish: {setup.finish?.latitude}, {setup.finish?.longitude}. {task===tasks.at(-1)?'Stopped final finish.':'Transit endpoint; no HOLD or settling command.'}</>}</p>
        <p className="hint">To correct assignments or a finish, choose Single task mode and review that task. Return here and refresh the reviewed setups.</p>
        <label><input type="checkbox" checked={!!setup.course_confirmed} onChange={e=>update({task_setup:{...draft.task_setup,[task]:{...setup,course_confirmed:e.target.checked,sizes_confirmed:true}}})}/>I reviewed this complete task’s local directions, order, sides, channel and finish</label>
      </>}</details>;})}
      {tasks.includes('gate')&&tasks.includes('slalom')&&<div className="callout"><button disabled={!ready} onClick={()=>run(async()=>{await save();const r=await load('run/relationship','POST',draft);setRelationship(r);})}>Review shared entrance gate</button>{relationship&&<p>{relationship.reason}. {relationship.scoring}.</p>}<label><input type="checkbox" checked={!!draft.share_gate} disabled={!draft.share_gate&&!relationship?.compatible} onChange={e=>update({share_gate:e.target.checked})}/>I confirm one shared forward crossing, followed by the full Slalom progression</label><p>Without confirmation, both tasks retain their crossing requirements. Review any return approach in the generated route.</p></div>}
      <label>Execution budget (seconds, boat limits 10–7200)<input type="number" min="10" max="7200" value={draft.execution_budget_s??300} onChange={e=>update({execution_budget_s:Number(e.target.value)})}/></label>
      {error&&<p className="action-reason">{error}</p>}
      <button className="primary wide" disabled={busy||!!error||!ready||(draft.planning_area?.length||0)<3||(draft.attempt?.start_source!=='manual'&&stale)} onClick={()=>run(async()=>{invalidateRoute();await save();const r=await load('generate','POST');if(!r.success){changeWorkspace(await load('workspace'),false,false);notify(r.diagnostics.join('; '),'error',r.errors);return;}changeWorkspace(r.workspace,false,false);onGenerated('competition');setStep(4);setMode('inspect');notify('Complete run generated. Review task and connector sections, then Validate and Approve.');})}>Generate competition run →</button>
    </section>;
}
