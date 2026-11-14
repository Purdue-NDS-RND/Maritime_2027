import React,{useEffect,useState} from 'react';
import {friendly} from './workflow';
import {isPoint,isNavigation,untypedNavigation,sameRoles,roleName} from './mapReviewState';
import BoundaryControls from './BoundaryControls';
import {boundaryProblem} from './planningBoundary';

export const COURSE_ROLES=[...['entrance.red','entrance.green','turn.1','turn.2','turn.3','turn.4','exit.red','exit.green'].map(r=>'slalom.'+r),...Array.from({length:3},(_,i)=>['red','green'].map(c=>`channel.${c}.${i+1}`)).flat()];
const typeNames={unknown:'Unknown object',buoy:'Navigation buoy',detector:'Lidar / detector tower',obstacle:'Other obstacle',dock:'Dock / obstacle'};
export function editObjects(map,ids,changes){return {...map,...Object.fromEntries(['buoys','obstacles'].map(key=>[key,(map[key]||[]).map(o=>ids.includes(o.id)?{...o,...changes}:o)]))};}
export function removeObject(map,id){return {...map,...Object.fromEntries(['buoys','obstacles'].map(key=>[key,(map[key]||[]).filter(o=>o.id!==id)]))};}
export function addedObject(position,id){return {id,type:'point',object_type:'unknown',category:'unknown',centre:position};}

export function AssignmentReview({candidate,assignments={},publish}){
    return <div className="assignment-review guided-tasks">{['gate','slalom','channel'].map(task=>{
        const saved=assignments[task],roles=candidate?.tasks[task]||saved?.roles;
        const matches=sameRoles(saved?.roles,roles),confirmed=matches&&saved?.status==='accepted';
        const available=!!candidate?.tasks[task];
        const detail=candidate?.details[task];
        const confirmButton=roles&&<button disabled={confirmed} onClick={()=>publish('course/select','POST',{task,...(available?{candidate_id:candidate.id}:{})},`${friendly(task)} confirmed. Continue reviewing the other tasks.`)}>{confirmed?`${friendly(task)} confirmed`:`Confirm ${friendly(task)}`}</button>;
        const description={gate:'Starting gate · separate task',slalom:'Four turns → exit gate · can run on its own',channel:'Three red and three green boundary buoys'}[task];
        return <article key={task} className={confirmed?'assignment-confirmed':''}>
          <div className="task-choice-heading"><div><h3>{friendly(task)}</h3><p>{description}</p></div><div className="task-choice-action">{!confirmed&&<span className="task-choice-status">{roles?'Review on map':'Not found'}</span>}{confirmButton}</div></div>
          {roles?<>
            {saved&&!matches&&<p className="hint">A different assignment is currently confirmed. Clear it below before choosing conflicting objects.</p>}
            <details><summary>Objects & corrections</summary>{Object.entries(roles).filter(([role])=>task!=='slalom'||!role.startsWith('slalom.entrance.')).map(([role,id])=><p key={role}>{roleName(role)} → {friendly(id)}</p>)}{saved&&<button className="quiet" onClick={()=>publish('course/select','POST',{task,clear:true},`${friendly(task)} assignment cleared.`)}>Clear {friendly(task)} assignment</button>}<p className="hint">You can also correct these objects in the task editor when building your run.</p></details>
            {detail?.measurements.some(m=>m.unusual)&&<p className="unusual-measurement">Some spacing is unusual. Check measurements below before confirming.</p>}
          </>:<p className="hint">Continue with other tasks, or assign this task manually later.</p>}
        </article>;
    })}</div>;
}

export default function MapReview(props){
    const {workspace,draft,selected,setSelected,save,load,run,notify,changeWorkspace,invalidateRoute,setMode,mode,originalOverlay,setOriginalOverlay,candidateId,setCandidateId,setStep}=props;
    const objects=[...(workspace.map.buoys||[]),...(workspace.map.obstacles||[])];
    const object=objects.find(o=>o.id===selected),result=workspace.compilation;
    const assignments=workspace.course_assignments||{};
    const hasReview=!!result?.candidates.length||Object.keys(assignments).length>0;
    const [phase,setPhase]=useState(()=>hasReview&&draft.sizes_confirmed?'review':'cleanup');
    const [objectEdit,setObjectEdit]=useState(null),[bulk,setBulk]=useState([]),[hintRole,setHintRole]=useState(COURSE_ROLES[0]);
    useEffect(()=>setObjectEdit(object?structuredClone(object):null),[object]);
    useEffect(()=>setBulk(ids=>ids.filter(id=>objects.some(o=>o.id===id))),[workspace.map]);
    useEffect(()=>{if(phase==='review'&&!hasReview)setPhase('cleanup');},[hasReview,phase]);
    const candidate=result?.candidates.find(c=>c.id===candidateId)||result?.candidates[0];
    const untyped=untypedNavigation(objects),navigation=objects.filter(isNavigation);
    const accepted=Object.values(assignments).filter(a=>a.status==='accepted').length;
    const boundaryError=boundaryProblem(draft.planning_area,workspace.map.geographic_reference);
    async function publish(path,method,body,message,nextPhase){await run(async()=>{
        const current=await save();
        try{
            const value=await load(path,method,{...body,revision:current.revision});
            changeWorkspace(value,false,false);invalidateRoute();notify(message);
            if(path==='course/compile')setPhase(value.compilation?.candidates.length?'review':'find');
            else if(nextPhase)setPhase(nextPhase);
        }catch(error){changeWorkspace(await load('workspace'),false,false);invalidateRoute();throw error;}
    });}
    async function mapEdit(map,message){await run(async()=>{await save({...workspace,map},true);invalidateRoute();setPhase('cleanup');notify(message);});}
    async function confirmMap(manual=false){await run(async()=>{
        if(boundaryError)throw new Error(boundaryError);
        await save({...workspace,run_draft:{...draft,sizes_confirmed:true}});
        setMode('inspect');
        if(manual){setStep(2);notify('Map checked. Configure navigation, then assign your tasks manually.');}
        else {setPhase('find');notify('Map checked. Find the course, or review saved assignments.');}
    });}
    async function continuePlanning(){await run(async()=>{await save();setStep(2);setMode('inspect');notify('Map and boundary ready. Choose shared clearance and a start, then build your run.');});}
    async function applyObject(){
        const corrected={...objectEdit};
        if(corrected.footprint&&object){const dy=corrected.centre.latitude-object.centre.latitude,dx=corrected.centre.longitude-object.centre.longitude;corrected.footprint=corrected.footprint.map(p=>({latitude:p.latitude+dy,longitude:p.longitude+dx}));}
        await mapEdit({...workspace.map,...Object.fromEntries(['buoys','obstacles'].map(key=>[key,(workspace.map[key]||[]).map(o=>o.id===selected?corrected:o)]))},'Object saved. Check the updated map before finding the course again.');
    }
    const setObject=(key,value)=>setObjectEdit(o=>({...o,[key]:value}));
    function chooseColors(colours){setBulk(objects.filter(o=>colours.includes(o.category)&&isPoint(o)).map(o=>o.id));}
    async function download(){await run(async()=>{
        await save();const file=await load('course/file');const url=URL.createObjectURL(new Blob([JSON.stringify(file,null,2)],{type:'application/json'}));
        const a=document.createElement('a');a.href=url;a.download='reviewed-course.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
        notify('Course saved. Import the JSON to review it again later.');
    });}
    const hints=<details className="guided-hints"><summary>Wrong objects? Add a hint</summary><p className="hint">Select an object on the map and pin it to the correct role. Then find the course again.</p><label>Course role<select value={hintRole} onChange={e=>setHintRole(e.target.value)}>{COURSE_ROLES.map(r=><option key={r} value={r}>{roleName(r)}</option>)}</select></label><p>{object?`Selected: ${friendly(object.id)}`:'Click an object on the map first.'}</p><button disabled={!object} onClick={()=>publish('course/hints','PUT',{hints:{...workspace.compiler_hints,[hintRole]:selected}},'Hint saved. Find the course again.','find')}>Pin selected object to role</button><button disabled={!Object.keys(workspace.compiler_hints||{}).length} onClick={()=>publish('course/hints','PUT',{hints:{}},'Hints cleared. Find the course again.','find')}>Clear hints</button>{Object.entries(workspace.compiler_hints||{}).map(([r,id])=><p key={r}>{roleName(r)} → {friendly(id)} <button className="quiet" onClick={()=>publish('course/hints','PUT',{hints:Object.fromEntries(Object.entries(workspace.compiler_hints).filter(([k])=>k!==r))},'Hint removed. Find the course again.','find')}>Unpin</button></p>)}</details>;
    return <section className="map-review guided-map-review" aria-label="Map cleanup and compilation">
      <nav className="map-stage-nav" aria-label="Map preparation">{[['cleanup','1','Clean up'],['find','2','Find course'],['review','3','Review tasks']].map(([id,n,label])=><button key={id} aria-current={phase===id?'step':undefined} disabled={id==='review'&&!hasReview} onClick={()=>{setPhase(id);setMode('inspect');}}><b>{n}</b>{label}</button>)}</nav>
      <div className="map-review-body" data-phase={phase}>
      {phase==='cleanup'&&<>
        <div className="map-phase-heading"><h2>Check the detections</h2><p>Correct anything misplaced or mislabeled, then continue.</p></div>
        <p className="object-type-summary"><strong>{navigation.length}</strong> navigation buoys · <strong>{objects.filter(o=>o.object_type==='detector').length}</strong> towers · <strong>{objects.filter(o=>!isNavigation(o)&&o.object_type!=='detector').length}</strong> other / unknown</p>
        <BoundaryControls {...props}/>
        {!!untyped.length&&<div className="map-next-action"><strong>{untyped.length} red/green detections need a type</strong><p>Are these navigation buoys? Confirm them together, or edit them individually below.</p><button className="primary" onClick={()=>mapEdit(editObjects(workspace.map,untyped.map(o=>o.id),{object_type:'buoy'}),'Red/green detections marked as navigation buoys. Check their positions, then continue.')}>Mark {untyped.length} red/green detections as buoys</button></div>}
        <div className="cleanup-toolbar button-row"><button aria-pressed={mode==='add-object'} onClick={()=>setMode('add-object')}>Add object on map</button><button className="quiet" disabled={!workspace.map_history?.undo.length} onClick={()=>publish('map/history','POST',{direction:'undo'},'Map edit undone. Check the map again.','cleanup')}>Undo map edit</button><button className="quiet" disabled={!workspace.map_history?.redo.length} onClick={()=>publish('map/history','POST',{direction:'redo'},'Map edit redone. Check the map again.','cleanup')}>Redo map edit</button></div>
        <details open={!!object}><summary>{object?`Edit ${friendly(object.id)}`:'Edit an individual object'}</summary><select aria-label="Object to inspect" value={object?.id||''} onChange={e=>setSelected(e.target.value)}><option value="">Select an object or click it on the map</option>{objects.map(o=><option key={o.id} value={o.id}>{friendly(o.id)} · {typeNames[o.object_type]||o.object_type}</option>)}</select>
          {objectEdit&&<div className="object-editor"><div className="fields"><label>Color<select value={objectEdit.category||'unknown'} onChange={e=>setObject('category',e.target.value)}>{[...new Set(['unknown','red','green','purple','blue','orange','yellow','white','black','zebra','brown','cyan',objectEdit.category].filter(Boolean))].map(c=><option key={c}>{c}</option>)}</select></label><label>Object type<select value={objectEdit.object_type||'unknown'} onChange={e=>setObject('object_type',e.target.value)}>{Object.entries(typeNames).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label></div>
          <details><summary>Position & original observation</summary><div className="fields">{['latitude','longitude'].map(key=><label key={key}>{friendly(key)}<input type="number" step="0.0000001" value={objectEdit.centre[key]} onChange={e=>setObject('centre',{...objectEdit.centre,[key]:Number(e.target.value)})}/></label>)}</div>{['radius_m','height_m'].filter(k=>k in objectEdit).map(key=><label key={key}>{friendly(key)}<input type="number" step="0.05" value={objectEdit[key]} onChange={e=>setObject(key,Number(e.target.value))}/></label>)}{objectEdit.footprint&&<label>Polygon vertices<textarea key={selected} defaultValue={JSON.stringify(objectEdit.footprint)} onBlur={e=>{try{setObject('footprint',JSON.parse(e.target.value));}catch{notify('Polygon vertices must be a GPS point list.');}}}/></label>}<pre>{JSON.stringify([...(workspace.original_map?.buoys||[]),...(workspace.original_map?.obstacles||[])].find(o=>o.id===selected)||'Added during cleanup',null,2)}</pre></details>
          <div className="button-row"><button onClick={applyObject}>Apply object correction</button><button onClick={()=>mapEdit(removeObject(workspace.map,selected),'Detection removed. The original observation is retained.')}>Remove detection</button></div></div>}
        </details>
        <details><summary>Choose detections by color</summary><div className="button-row"><button onClick={()=>chooseColors(['red'])}>Select red</button><button onClick={()=>chooseColors(['green'])}>Select green</button><button onClick={()=>chooseColors(['red','green'])}>Select red + green</button><button className="quiet" onClick={()=>setBulk([])}>Clear selection</button></div><div className="bulk-objects">{objects.filter(isPoint).map(o=><label key={o.id} className="inline-check"><input type="checkbox" checked={bulk.includes(o.id)} onChange={e=>setBulk(ids=>e.target.checked?[...ids,o.id]:ids.filter(id=>id!==o.id))}/>{o.category||'unknown'} · {friendly(o.id)}</label>)}</div><button disabled={!bulk.length} onClick={()=>mapEdit(editObjects(workspace.map,bulk,{object_type:'buoy'}),'Selected detections marked as navigation buoys.')}>Mark selected as navigation buoys ({bulk.length})</button></details>
        <details><summary>Compare with the original map</summary><label className="inline-check"><input type="checkbox" checked={!!originalOverlay} onChange={e=>setOriginalOverlay(e.target.checked)}/>Show original observations</label><p className="hint">Cleanup never changes the original import. Other and unknown objects still block routes.</p></details>
      </>}
      {phase==='find'&&<>
        <div className="map-phase-heading"><h2>Find the course</h2><p>Match the navigation buoys to Gate, Slalom and Channel. You’ll check the result on the map next.</p></div>
        {!draft.sizes_confirmed?<p className="map-next-action">The map changed. Return to Clean up and check it again.</p>:navigation.length<2?<div className="map-next-action"><strong>Navigation buoys need labels first</strong><p>Return to Clean up and mark the red/green detections as navigation buoys.</p></div>:<p className="map-ready-note">Ready: {navigation.length} navigation buoys. Their GPS positions will stay unchanged.</p>}
        {hasReview&&<button onClick={()=>setPhase('review')}>Review existing assignments →</button>}
        {result&&!result.candidates.length&&<p className="callout warning">No course found. Check the colors and types, add a hint, or assign tasks manually.</p>}
        {hints}
        <p className="hint">You can continue with only the tasks that are recognized. Finding a course never creates a boat route.</p>
      </>}
      {phase==='review'&&<>
        <div className="map-phase-heading"><h2>Check the tasks on the map</h2><p>Confirm the highlighted tasks you want to use.</p></div>
        {!!result?.candidates.length&&<>
          <div className="course-options"><span>Course options</span><div className="button-row" aria-label="Ranked course options">{result.candidates.map((c,i)=><button key={c.id} aria-pressed={candidate?.id===c.id} onClick={()=>setCandidateId(c.id)}>Option {i+1}</button>)}</div></div>
          {result.search_exhausted&&<p className="hint compact-search-note">More interpretations may exist. Check the map before confirming.</p>}
        </>}
        <AssignmentReview candidate={candidate} assignments={assignments} publish={publish}/>
        {hints}
        {result&&<details className="compilation-details"><summary>Measurements & search details</summary><p>Reference profile v{result.profile?.version||1}. Costs compare geometry; they are not probabilities.</p><p>{result.expanded_states.toLocaleString()} states · {result.elapsed_s.toFixed(2)} s · {result.search_exhausted?'Search truncated':'Search completed'}. {result.limits.join(', ')}</p>{candidate&&<><p>Total cost: {candidate.score.toFixed(3)}. The starting gate is recognized as a reference pair; its crossing belongs only to a separate Gate task.</p>{Object.entries(candidate.details).filter(([,detail])=>detail.measurements).map(([task,detail])=><div key={task}><h4>{friendly(task)}</h4><p>{Object.entries(detail.score_components).map(([key,value])=>`${key}: ${value.toFixed(3)}`).join(' · ')}</p>{detail.measurements.map((m,i)=><p className={m.unusual?'unusual-measurement':''} key={i}>{m.unusual?'Unusual: ':''}{m.label}: {m.actual_m.toFixed(2)} m{m.nominal_m?` (nominal ${m.nominal_m.toFixed(2)} m; residual ${m.normalized_residual.toFixed(2)})`:''}</p>)}</div>)}{candidate.details.connection&&<p>Connection gap: {candidate.details.connection.actual_m.toFixed(2)} m; cost {candidate.details.connection.cost.toFixed(3)}.</p>}</>}<details><summary>Incomplete assignments</summary>{Object.entries(result.partials).map(([task,roles])=><p key={task}>{friendly(task)}: {Object.entries(roles).map(([r,id])=>`${roleName(r)} → ${friendly(id)}`).join('; ')||'None'}</p>)}</details></details>}
        <p className="hint">Configure navigation next, then choose your run order.</p><button className="text-button" onClick={()=>draft.sizes_confirmed?continuePlanning():setPhase('cleanup')}>Skip recognition — assign tasks manually</button>
      </>}
      </div>
      <footer className="map-review-footer">
        {phase==='cleanup'&&<>{navigation.length<2&&<p className="action-reason">Mark the navigation buoys above, or assign tasks manually.</p>}<p className="hint">Continuing confirms the objects and displayed planning boundary.</p><button className="primary wide" disabled={navigation.length<2||!!boundaryError} onClick={()=>confirmMap()}>I reviewed the map — continue →</button><button className="text-button" disabled={!!boundaryError} onClick={()=>confirmMap(true)}>Map checked — assign tasks manually</button></>}
        {phase==='find'&&<><button className="primary wide" disabled={!draft.sizes_confirmed||navigation.length<2} onClick={()=>publish('course/compile','POST',{},'Course found. Check and confirm the highlighted tasks.')}>Compile course →</button><button className="text-button" onClick={()=>setPhase('cleanup')}>← Back to cleanup</button></>}
        {phase==='review'&&<><span className="hint">{accepted?`${accepted} of 3 tasks confirmed · remaining tasks can be assigned later`:'Confirm at least one task, or choose manual assignment.'}</span><button className="primary wide" disabled={!draft.sizes_confirmed||!accepted} onClick={continuePlanning}>Continue to Configure →</button>{!draft.sizes_confirmed&&<button className="text-button" onClick={()=>setPhase('cleanup')}>Check the map first →</button>}</>}
        <details><summary>Save course</summary><button onClick={download}>Download course JSON</button><p className="hint">Saves observations and assignments. Import the file from Change map to review it later.</p></details>
      </footer>
    </section>;
}
