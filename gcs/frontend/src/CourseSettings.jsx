import React from 'react';
import {friendly,TASKS} from './workflow';
import {defaultSettings,settingsError,towerZones} from './settings';

function DistanceFields({value,onChange,prefix=''}) {
    return <div className="fields"><label>Hard exclusion (m)<input aria-label={`${prefix}Hard exclusion`} type="number" min="0" step="0.1" value={value.hard_m??''} onChange={e=>onChange({...value,hard_m:e.target.value===''?null:Number(e.target.value)})}/></label><label>Soft avoidance (m)<input aria-label={`${prefix}Soft avoidance`} type="number" min="0" step="0.5" value={value.soft_m??''} onChange={e=>onChange({...value,soft_m:e.target.value===''?null:Number(e.target.value)})}/></label></div>;
}
export default function CourseSettings({workspace,selected,setSelected,updateSettings,saveSettings,busy}) {
    const settings=workspace.game_settings||defaultSettings(workspace.draft);
    const policy=settings.tower_avoidance;
    const towers=[...(workspace.map?.buoys||[]),...(workspace.map?.obstacles||[])].filter(o=>o.object_type==='detector');
    const tower=towers.find(o=>o.id===selected);
    const update=changes=>updateSettings({...settings,...changes});
    const updatePolicy=changes=>update({tower_avoidance:{...policy,...changes}});
    const error=settingsError(settings);
    return <fieldset disabled={busy} className="configuration-fields">
      <div className="step-heading"><span className="eyebrow">STEP 2 OF 4</span><h2>Configure the course</h2><p>Set your preferences once. Every task uses these settings unless you choose an override.</p></div>
      {error&&<div className="configuration-error" role="alert"><strong>Configuration needs attention</strong><p>{error}</p><small>Correct this value to enable Save configuration. The existing saved settings have not changed.</small></div>}
      <div className="config-section"><div className="section-title"><span className="config-dot blue"/><h3>Boat & obstacle clearance</h3></div>
        <label>Target speed (m/s)<input aria-label="Course target speed" type="number" min="0.1" step="0.1" value={settings.speed_m_s??''} onChange={e=>update({speed_m_s:e.target.value===''?null:Number(e.target.value)})}/></label>
        <div className="fields"><label>Required clearance (m)<input aria-label="Course required clearance" type="number" min="0" step="0.1" value={settings.clearance_m??''} onChange={e=>update({clearance_m:e.target.value===''?null:Number(e.target.value)})}/></label><label>Preferred room (m)<input aria-label="Course preferred room" type="number" min="0" step="0.1" value={settings.preferred_buffer_m??''} onChange={e=>update({preferred_buffer_m:e.target.value===''?null:Number(e.target.value)})}/></label></div>
        <p className="hint">Required clearance is mandatory. Preferred room may yield locally. Distances are measured directly from each object’s GPS point. Include object size, boat size and positioning error in the hard distance; no object radius is added. Towers use their own distances below.</p>
      </div>
      <div className="config-section tower-section"><div className="section-title"><span className="config-dot purple"/><h3>LiDAR tower avoidance</h3><span className="count-badge">{towers.length} towers</span></div>
        <p className="hint">Solid inner zone: never enter. Fading outer zone: strongly prefer more distance, while allowing a tighter route if needed.</p>
        <DistanceFields value={policy} onChange={value=>update({tower_avoidance:value})} prefix="All towers "/>
        <label>Avoidance strength<select aria-label="Tower avoidance strength" value={policy.strength} onChange={e=>updatePolicy({strength:Number(e.target.value)})}>{[[4,'Moderate'],[10,'Strong'],[25,'Very strong'],...(![4,10,25].includes(policy.strength)?[[policy.strength,`Custom (${policy.strength})`]]:[])].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
        <p className="hint">Shared defaults apply to every tower without an override. These zones express your planning assumptions; they are not measured detector coverage.</p>
        <label>Configure a tower<select aria-label="Tower to configure" value={tower?.id||''} onChange={e=>setSelected(e.target.value)}><option value="">All towers · shared defaults</option>{towers.map(o=><option key={o.id} value={o.id}>{friendly(o.id)}{policy.overrides?.[o.id]?' · override':''}</option>)}</select></label>
        {tower&&<div className="tower-override"><strong>{friendly(tower.id)}</strong><label className="check-card"><input type="checkbox" checked={!!policy.overrides?.[tower.id]} onChange={e=>{const overrides={...policy.overrides};if(e.target.checked)overrides[tower.id]={hard_m:policy.hard_m,soft_m:policy.soft_m};else delete overrides[tower.id];updatePolicy({overrides});}}/>Use individual distances</label>
          {policy.overrides?.[tower.id]?<DistanceFields value={towerZones(tower,settings)} prefix="Selected tower " onChange={value=>updatePolicy({overrides:{...policy.overrides,[tower.id]:value}})}/>:<p className="hint">Using shared distances: {policy.hard_m} m hard / {policy.soft_m} m soft.</p>}
          <button className="text-button" disabled={!Object.keys(policy.overrides||{}).length} onClick={()=>updatePolicy({overrides:{}})}>Reset all towers to shared defaults</button>
        </div>}
      </div>
      <details open={error.includes('override')||undefined}><summary>Optional task overrides</summary><p className="hint">Leave tasks on shared settings unless you need a different speed or avoidance configuration. Review task boundaries in the next step.</p>{TASKS.filter(t=>t.id!=='manual').map(t=>{
        const override=settings.task_overrides?.[t.id];
        const change=value=>update({task_overrides:{...settings.task_overrides,[t.id]:{...override,...value}}});
        return <div key={t.id} className="task-override"><label><input type="checkbox" checked={!!override} onChange={e=>{const overrides={...settings.task_overrides};if(e.target.checked)overrides[t.id]={speed_m_s:settings.speed_m_s,clearance_m:settings.clearance_m,preferred_buffer_m:settings.preferred_buffer_m,tower_avoidance:structuredClone(policy)};else delete overrides[t.id];update({task_overrides:overrides});}}/>{t.title} · {override?'custom settings':'shared settings'}</label>
          {override&&<><label>Target speed (m/s)<input aria-label={`${t.title} speed`} type="number" step="0.1" value={override.speed_m_s??settings.speed_m_s} onChange={e=>change({speed_m_s:Number(e.target.value)})}/></label><div className="fields">{[['clearance_m','Required clearance'],['preferred_buffer_m','Preferred room']].map(([key,label])=><label key={key}>{label} (m)<input type="number" step="0.1" value={override[key]??settings[key]} onChange={e=>change({[key]:Number(e.target.value)})}/></label>)}</div><DistanceFields prefix={`${t.title} towers `} value={override.tower_avoidance||policy} onChange={value=>change({tower_avoidance:value})}/></>}
        </div>;
      })}</details>
      {error&&<p className="action-reason error-text">Save is unavailable: {error}</p>}
      <p className="hint">The map previews changes immediately. Saving changes revokes route approval; generate and review a new route.</p>
      <button className="primary wide" disabled={busy||!!error} onClick={saveSettings}>Save configuration & choose task →</button>
    </fieldset>;
}
