import React,{useEffect,useState} from 'react';
import CourseSettings from './CourseSettings';
import {RunConfiguration} from './RunBuilder';
import {settingsError} from './settings';
import {boundaryProblem} from './planningBoundary';

export default function Configuration(props) {
    const {workspace,draft,selected,saveSettings}=props;
    const [category,setCategory]=useState('clearance');
    useEffect(()=>{
        const objects=[...(workspace.map?.buoys||[]),...(workspace.map?.obstacles||[])];
        if(objects.some(o=>o.id===selected&&o.object_type==='detector'))setCategory('towers');
    },[selected,workspace.map]);
    const error=settingsError(workspace.game_settings)||boundaryProblem(draft.planning_area,workspace.map.geographic_reference);
    const budgetValid=Number.isFinite(draft.execution_budget_s)&&draft.execution_budget_s>=10&&draft.execution_budget_s<=7200;
    return <section className="configuration-workspace" aria-label="Shared configuration" data-category={category}>
        <div className="configuration-heading"><h2>Shared configuration</h2><span>Applies to every task</span></div>
        <div className="configuration-body">
            <nav className="configuration-categories" aria-label="Setting categories">{[['clearance','Speed & clearance'],['towers','LiDAR towers'],['navigation','Start & limits']].map(([id,label])=><button key={id} aria-pressed={category===id} onClick={()=>setCategory(id)}>{label}</button>)}</nav>
            <div className="configuration-panels"><CourseSettings {...props}/><RunConfiguration {...props}/></div>
        </div>
        <div className="configuration-footer"><p>{error||(!budgetValid?'Execution budget must be within 10–7200 seconds.':'Settings stay in this page session. Changes require a new route review.')}</p><button className="primary" disabled={!!error||!budgetValid} onClick={saveSettings}>Continue to Build run →</button></div>
    </section>;
}
