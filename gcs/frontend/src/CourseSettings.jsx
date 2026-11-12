import React from 'react';
import {friendly} from './workflow';
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
      {error&&<div className="configuration-error" role="alert"><strong>Configuration needs attention</strong><p>{error}</p><small>Correct this value before continuing to Build run.</small></div>}
      <div className="config-section clearance-section settings-table"><div className="section-title"><span className="config-dot blue"/><h3>Boat & obstacle clearance</h3></div>
        <label>Target speed (m/s)<input aria-label="Course target speed" type="number" min="0.1" step="0.1" value={settings.speed_m_s??''} onChange={e=>update({speed_m_s:e.target.value===''?null:Number(e.target.value)})}/></label>
        <div className="fields"><label>Required clearance (m)<input aria-label="Course required clearance" type="number" min="0" step="0.1" value={settings.clearance_m??''} onChange={e=>update({clearance_m:e.target.value===''?null:Number(e.target.value)})}/></label><label>Preferred room (m)<input aria-label="Course preferred room" type="number" min="0" step="0.1" value={settings.preferred_buffer_m??''} onChange={e=>update({preferred_buffer_m:e.target.value===''?null:Number(e.target.value)})}/></label></div>
        <p className="hint">Required clearance is mandatory; preferred room may yield.</p><details className="setting-help"><summary>How clearance is measured</summary><p>Distances are measured from each object’s GPS point. Include object size, hull size and positioning error in required clearance; no object radius is added. Towers use their own distances.</p></details>
      </div>
      <div className="config-section tower-section settings-table"><div className="section-title"><span className="config-dot purple"/><h3>LiDAR tower avoidance</h3><span className="count-badge">{towers.length} towers</span></div>
        <DistanceFields value={policy} onChange={value=>update({tower_avoidance:value})} prefix="All towers "/>
        <label>Avoidance strength<select aria-label="Tower avoidance strength" value={policy.strength} onChange={e=>updatePolicy({strength:Number(e.target.value)})}>{[[4,'Moderate'],[10,'Strong'],[25,'Very strong'],...(![4,10,25].includes(policy.strength)?[[policy.strength,`Custom (${policy.strength})`]]:[])].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
        <label>Configure a tower<select aria-label="Tower to configure" value={tower?.id||''} onChange={e=>setSelected(e.target.value)}><option value="">All towers · shared defaults</option>{towers.map(o=><option key={o.id} value={o.id}>{friendly(o.id)}{policy.overrides?.[o.id]?' · override':''}</option>)}</select></label>
        {tower&&<div className="tower-override"><strong>{friendly(tower.id)}</strong><label className="inline-check"><input type="checkbox" checked={!!policy.overrides?.[tower.id]} onChange={e=>{const overrides={...policy.overrides};if(e.target.checked)overrides[tower.id]={hard_m:policy.hard_m,soft_m:policy.soft_m};else delete overrides[tower.id];updatePolicy({overrides});}}/>Use individual distances</label>
          {policy.overrides?.[tower.id]?<DistanceFields value={towerZones(tower,settings)} prefix="Selected tower " onChange={value=>updatePolicy({overrides:{...policy.overrides,[tower.id]:value}})}/>:<p className="hint">Using shared distances: {policy.hard_m} m hard / {policy.soft_m} m soft.</p>}
          <button className="text-button" disabled={!Object.keys(policy.overrides||{}).length} onClick={()=>updatePolicy({overrides:{}})}>Reset all towers to shared defaults</button>
        </div>}
        <details className="setting-help"><summary>Tower zone help</summary><p>Hard exclusion is mandatory. Soft avoidance prefers more distance but may yield. Defaults apply to towers without individual overrides. Zones are planning assumptions, not measured detector coverage.</p></details>
      </div>
      {error&&<p className="action-reason error-text">Configuration needs attention: {error}</p>}

    </fieldset>;
}
