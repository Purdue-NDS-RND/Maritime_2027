import React from 'react';
import {boundaryInputs,boundaryProblem,outsideBoundary,DEFAULT_BOUNDARY_PADDING_M} from './planningBoundary';

export default function BoundaryControls({workspace,draft,mode,setMode,boundaryPadding=DEFAULT_BOUNDARY_PADDING_M,setBoundaryPadding,onRegenerateBoundary,onBoundaryChange,knownBoundaryStart=null}){
    const points=draft.planning_area||[],problem=boundaryProblem(points,workspace.map.geographic_reference);
    const invalidPadding=!Number.isFinite(boundaryPadding)||boundaryPadding<=0;
    const outside=outsideBoundary([...boundaryInputs(workspace.map,knownBoundaryStart),...(draft.steps||[]).flatMap(s=>s.type==='manual'?(s.setup.waypoints||[]):[s.setup.finish].filter(Boolean))],points,workspace.map.geographic_reference);
    return <section className="planning-boundary-controls" aria-label="Planning boundary">
      <div className="boundary-heading"><strong>Planning boundary</strong><span>{points.length} corners</span></div>
      <p className="hint">An outline around the whole map, rotated to fit the course. Check that it follows permitted water.</p>
      <div className="boundary-padding"><label>Extra room (m)<input aria-label="Boundary extra room" type="number" min="0.1" step="1" value={boundaryPadding??''} onChange={e=>setBoundaryPadding(e.target.value===''?null:Number(e.target.value))}/></label><button disabled={invalidPadding} onClick={onRegenerateBoundary}>Regenerate</button></div>
      {invalidPadding&&<p className="action-reason" role="alert">Extra room must be greater than zero.</p>}
      <div className="button-row"><button disabled={points.length<3} aria-pressed={mode==='boundary-corners'} onClick={()=>setMode('boundary-corners')}>Edit corners</button><button onClick={()=>{onBoundaryChange([]);setMode('planning_area');}}>Draw manually</button><button className="quiet" disabled={!points.length} onClick={()=>onBoundaryChange(points.slice(0,-1))}>Undo corner</button></div>
      {problem&&<p className="action-reason" role="alert">{problem}</p>}
      {outside&&<p className="action-reason">Some map positions, task endpoints or the known start are outside this boundary. Check the map and edit or regenerate the outline if needed.</p>}
      <details><summary>Boundary help</summary><p className="hint">Extra room applies when you regenerate. This suggestion cannot identify shorelines. The boundary stays fixed as the boat moves; channel limits and required clearance still apply.</p></details>
    </section>;
}
