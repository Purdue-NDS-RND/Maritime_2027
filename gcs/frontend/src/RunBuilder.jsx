import React,{useState} from 'react';
import {createPortal} from 'react-dom';
import TaskEditor from './TaskEditor';
import {settingsError} from './settings';
import BoundaryControls from './BoundaryControls';
import TaskReviewButton from './TaskReviewButton';

export function moveStep(steps,from,to){const next=[...steps];const [step]=next.splice(from,1);next.splice(to,0,step);return next;}
export function duplicateStep(step,id){return {id,type:step.type,setup:structuredClone(step.setup)};}
export default function RunBuilder({workspace,draft,edit,selectedCard,onSelect,setMode,load,save,run,notify,busy,stale,onGenerated,changeWorkspace,setStep,invalidateRoute,selected,setSelected,updateSettings,showMap,sequenceHost,onPassageSelected,focusedPassage}) {
    const [drag,setDrag]=useState(null);
    const card=valuesCard(draft,selectedCard);
    const cardIndex=(draft.steps||[]).findIndex(s=>s.id===selectedCard);
    const values=draft.steps||[];
    function update(changes){invalidateRoute();edit({...draft,...changes,shared_crossings:[],waypoints:[],generation_identity:null});}
    function updateCard(id,next){update({steps:values.map(s=>s.id===id?{...s,setup:next}:s)});}
    async function add(type){await run(async()=>{
        let setup={waypoints:[],course_confirmed:false,finish_radius_m:1};
        const boundary=draft.planning_area;
        if(type!=='manual'){
            const proposal=await load('course/prepare','POST',{task:type,settings:{...draft.settings,sizes_confirmed:draft.sizes_confirmed}});
            setup=proposal.draft;
            notify(proposal.ready?'Review the suggested assignments for this card.':proposal.diagnostics.join(' '));
        }
        const id=crypto.randomUUID();update({steps:[...values,{id,type,setup}],planning_area:boundary});onSelect(id);
    });}
    const error=settingsError({version:1,...draft.settings,task_overrides:{}})||(!Number.isFinite(draft.execution_budget_s)||draft.execution_budget_s<10||draft.execution_budget_s>7200?'Execution budget must be within 10–7200 seconds.':'');
    const ready=values.length>0&&values.every(s=>s.setup.course_confirmed&&(s.type!=='manual'||s.setup.waypoints?.length));
    const controls=<fieldset disabled={busy} className="builder-controls">
      <div className="builder-toolbar">
      <div className="task-palette" aria-label="Add a task">{Object.entries(TASK_STYLE).map(([type,style])=><button key={type} className="add-task" style={{'--task-color':style.color}} onClick={()=>add(type)}><strong>＋ {style.title}</strong></button>)}</div>
      <div className="selected-task-actions" aria-label="Selected task actions"><button aria-label={`Move ${card?cardName(values,cardIndex):'task'} up`} disabled={!card||cardIndex===0} onClick={()=>update({steps:moveStep(values,cardIndex,cardIndex-1)})}>↑</button><button aria-label={`Move ${card?cardName(values,cardIndex):'task'} down`} disabled={!card||cardIndex===values.length-1} onClick={()=>update({steps:moveStep(values,cardIndex,cardIndex+1)})}>↓</button><button disabled={!card} onClick={()=>{const copy=duplicateStep(card,crypto.randomUUID());update({steps:[...values.slice(0,cardIndex+1),copy,...values.slice(cardIndex+1)]});onSelect(copy.id);}}>Duplicate</button><button className="quiet" disabled={!card} onClick={()=>{update({steps:values.filter(s=>s.id!==card.id)});onSelect(values[cardIndex+1]?.id||values[cardIndex-1]?.id||null);}}>Remove</button><button className="quiet" onClick={()=>setStep(2)}>Shared settings ↗</button></div>
      </div>
      <section className="run-sequence" aria-label="Ordered tasks"><div className="section-title"><h3>Run sequence</h3><span className="sequence-count">{values.length} {values.length===1?'task':'tasks'}</span></div><p className="hint">Drag the grip to reorder, or use the arrow buttons.</p>
      {!values.length&&<div className="empty-state"><span aria-hidden="true">＋</span><h3>Your run is empty</h3><p>Choose Gate, Slalom, Channel or Manual above. Repeats are welcome.</p></div>}
      {values.map((item,i)=><article key={item.id} className={'run-card '+(selectedCard===item.id?'selected':'')} style={{'--task-color':TASK_STYLE[item.type].color}} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(busy)return;if(drag!==null)update({steps:moveStep(values,drag,i)});setDrag(null);}}>
        <div className="sequence-item"><span className="drag-grip" draggable={!busy} onDragStart={e=>{setDrag(i);e.dataTransfer.setData('text/plain',item.id);}} onDragEnd={()=>setDrag(null)} title="Drag to reorder" aria-hidden="true">⠿</span><span className="sequence-number">{i+1}</span><button className="select-task" aria-pressed={selectedCard===item.id} onClick={()=>{onSelect(item.id);setMode('inspect');}}><strong>{cardName(values,i)}</strong><small className={item.setup.course_confirmed?'task-reviewed':''}>{item.setup.course_confirmed?'✓ Reviewed':'○ Review'}</small></button></div>

      </article>)}
      </section>
    </fieldset>;
    return <section className="run-builder" aria-label="Run builder">
      {sequenceHost?createPortal(<>{controls}</>,sequenceHost):controls}
      <div className="run-workspace"><section className="task-editor-panel" aria-label="Selected task configuration" style={{'--task-color':TASK_STYLE[card?.type]?.color||'#a9bbd0'}}>
      {card?<><div className="editor-heading"><span className="task-symbol" aria-hidden="true">{TASK_STYLE[card.type].symbol}</span><div><span className="eyebrow">TASK {cardIndex+1} OF {values.length}</span><h2>{cardName(values,cardIndex)}</h2><p>{card.setup.course_confirmed?'Reviewed':'Review and confirm this task'}</p></div></div>
      {card.type==='manual'?<>
            <div className="manual-editor-content"><p>Exact ordered waypoints; connecting segments are validated. Click the map to append points or edit their coordinates below.</p><button onClick={()=>setMode('card:waypoint')}>Draw manual waypoints</button>
            {(card.setup.waypoints||[]).map((p,j)=><div key={j} className="fields">{['latitude','longitude'].map(k=><label key={k}>{j+1}. {k}<input type="number" step="0.0000001" value={p[k]} onChange={e=>updateCard(card.id,{...card.setup,course_confirmed:false,waypoints:card.setup.waypoints.map((v,n)=>n===j?{...v,[k]:Number(e.target.value)}:v)})}/></label>)}<button onClick={()=>updateCard(card.id,{...card.setup,course_confirmed:false,waypoints:card.setup.waypoints.filter((_,n)=>n!==j)})}>Remove waypoint</button></div>)}
            </div><div className="manual-review"><TaskReviewButton reviewed={!!card.setup.course_confirmed} disabled={!card.setup.waypoints?.length} onChange={confirmed=>updateCard(card.id,{...card.setup,course_confirmed:confirmed})}>I reviewed these ordered manual waypoints.</TaskReviewButton></div>
        </>:<TaskEditor key={card.id} {...{workspace,setMode,load,save,run,notify,showMap,onPassageSelected,focusedPassage}} instanceId={card.id} draft={{...card.setup,...draft.settings,planner_task:card.type,planning_area:draft.planning_area,sizes_confirmed:draft.sizes_confirmed}} edit={next=>updateCard(card.id,next)}/>}
      </>:<div className="empty-state"><span aria-hidden="true">⌖</span><h3>Select a task</h3><p>Select a task in your sequence to edit assignments, direction and endpoints here.</p></div>}
      </section></div>
      <section className="run-generation" aria-label="Generate complete run">
      <div className="generation-heading"><strong>Ready for route review?</strong><span>{values.filter(s=>s.setup.course_confirmed).length} of {values.length} tasks reviewed · {draft.settings.speed_m_s} m/s · {draft.settings.clearance_m} m required clearance</span></div>
      {error&&<p className="action-reason">{error}</p>}
      <p className="action-reason">{!draft.sizes_confirmed?'Review the object map. ':''}{!ready?'Add and confirm every complete card. ':''}{draft.planning_area?.length<3?'Draw the common planning boundary. ':''}{draft.attempt?.start_source!=='manual'&&stale?'Reconnect fresh telemetry or explicitly select Manual start.':''}</p>
      <button className="primary wide" disabled={busy||!!error||!ready||!draft.sizes_confirmed||draft.planning_area?.length<3||(draft.attempt?.start_source!=='manual'&&stale)} onClick={()=>run(async()=>{invalidateRoute();await save();const r=await load('generate','POST');changeWorkspace(r.workspace,false,false);if(!r.success){notify(r.diagnostics.join('; '),'error',r.errors);return;}onGenerated('run');setStep(4);setMode('inspect');notify('Complete run generated. Review the route and connectors, then Validate and Approve.');})}>Generate run →</button>
      </section>
    </section>;
}

export function RunConfiguration(props) {
    const {draft,edit,invalidateRoute,setMode,stale}=props;
    function update(changes){invalidateRoute();edit({...draft,...changes,shared_crossings:[],waypoints:[],generation_identity:null});}
    return <section className="config-section navigation-section settings-table"><div className="section-title"><span className="config-dot amber"/><h3>Start, boundary & execution</h3></div>
      <label>Start source<select value={draft.attempt?.start_source||'live'} onChange={e=>update({attempt:{mode:'full',start_source:e.target.value}})}><option value="live">Live boat</option><option value="manual">Manual start (offline)</option></select></label>
      {draft.attempt?.start_source==='manual'&&<button onClick={()=>setMode('start')}>Choose manual start on map</button>}
      <p className="hint">{draft.attempt?.start_source==='manual'?'Manual start is an explicit planning input.':stale?'Live start unavailable: connect the boat or select Manual.':'Live start is captured fresh when generating.'}</p>
      <label>Execution budget (seconds)<input type="number" min="10" max="7200" value={draft.execution_budget_s} onChange={e=>update({execution_budget_s:Number(e.target.value)})}/></label>
      <BoundaryControls {...props}/>
      <details className="setting-help"><summary>Start and execution help</summary><p>Every task uses this boundary and execution budget. Generate captures a new start; edits require fresh generation and approval.</p></details>
    </section>;
}
export const TASK_STYLE={gate:{title:'Gate',symbol:'⇥',description:'Complete gate passage',color:'#57d6b4'},slalom:{title:'Slalom',symbol:'〰',description:'Ordered turns and passing sides',color:'#efc16a'},channel:{title:'Channel',symbol:'≋',description:'Reviewed permitted water',color:'#68d5ed'},manual:{title:'Manual',symbol:'⌖',description:'Exact ordered waypoints',color:'#a9bbd0'}};
const valuesCard=(draft,id)=>(draft.steps||[]).find(s=>s.id===id);
export function cardName(steps,index){const card=steps[index];return `${TASK_STYLE[card.type].title} ${steps.slice(0,index+1).filter(s=>s.type===card.type).length}`;}
