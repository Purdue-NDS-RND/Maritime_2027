import React,{useEffect,useRef,useState} from 'react';

export const linkLabel = value => ({connecting:'Connecting',waiting:'Waiting for vehicle',live:'Live',stale:'Stale',error:'Connection error',disconnected:'Connection error'}[value]||'Connecting');
export default function ConnectionsDialog({connections,onClose,onUpdate,load,status,vehicleStale,telemetry,telemetryStale}){
    const [profile,setProfile]=useState(connections.selected_profile);
    const [settings,setSettings]=useState(()=>structuredClone(connections.profiles[connections.selected_profile]||{boat_url:'',telemetry:{connection:'',baud:57600,system_id:1,component_id:1}}));
    const [revision,setRevision]=useState(connections.revision),[busy,setBusy]=useState(false),[error,setError]=useState(''),[note,setNote]=useState(''),[test,setTest]=useState(null),[devices,setDevices]=useState(null),[ack,setAck]=useState(false);
    const dialog=useRef();
    useEffect(()=>{dialog.current.showModal();return()=>dialog.current?.close();},[]);
    const serial=settings.telemetry.connection.startsWith('/dev/');
    const apiState=status?.connection_error?'Connection error':!status?'Connecting':!status.position||status.heartbeat_age_s==null?'Waiting for vehicle':vehicleStale?'Stale':'Live';
    const active=JSON.stringify(settings)===JSON.stringify(connections.effective);
    const edited=JSON.stringify(settings)!==JSON.stringify(connections.profiles[profile]);
    const conflict=revision!==connections.revision;
    function select(name){setProfile(name);setSettings(structuredClone(connections.profiles[name]||{boat_url:'',telemetry:{connection:'',baud:57600,system_id:1,component_id:1}}));setTest(null);setAck(false);setError('');setNote('');}
    function edit(key,value){setSettings(s=>({...s,[key]:value}));setTest(null);setAck(false);setNote('');}
    function radio(key,value){edit('telemetry',{...settings.telemetry,[key]:value});}
    async function work(fn){setBusy(true);setError('');try{await fn();}catch(e){setError(e.message);}finally{setBusy(false);}}
    async function refreshDevices(){const value=await load('connections/serial?revision='+revision+'&configured='+encodeURIComponent(settings.telemetry.connection));setDevices(value);}
    async function save(apply){await work(async()=>{
        const value=await load('connections/'+(apply?'apply':'save'),'POST',{revision,profile,settings,acknowledge_unknown:ack});
        setRevision(value.revision);onUpdate(value);setNote(apply?'Settings applied. Waiting for fresh link status.':'Profile saved. Active connections are unchanged.');setAck(false);setTest(null);
    });}
    return <dialog ref={dialog} className="connections-dialog" aria-labelledby="connections-title" onCancel={e=>{e.preventDefault();if(!busy)onClose();}}>
        <div className="connections-title"><h2 id="connections-title">Connections</h2><button disabled={busy} onClick={onClose}>Cancel</button></div>
        <p>One active configuration is shared by every browser tab. Selecting or editing a profile does not reconnect.</p>
        {connections.error&&<p className="callout error">{connections.error}</p>}
        {conflict&&<p className="callout error">Connections changed in another tab. Your edits are retained. <button onClick={()=>{setRevision(connections.revision);select(profile);}}>Reload saved profile</button></p>}
        <label>Profile <select value={profile} disabled={busy} onChange={e=>select(e.target.value)}><option>Simulator</option><option>Field</option></select></label>
        <p role="status">{edited?'Unsaved edits':active?'Active settings':'Saved profile · not active'} · Active profile: {connections.active_profile||'none'}</p>
        <div className="connections-sections">
            <section><h3>Mission API</h3>
                <label>Jetson HTTP(S) address <input value={settings.boat_url} disabled={busy} placeholder="http://192.168.50.2:8091" onChange={e=>edit('boat_url',e.target.value)}/></label>
                <button disabled={busy||!settings.boat_url} onClick={()=>work(async()=>setTest(await load('connections/test','POST',{boat_url:settings.boat_url,revision})))}>Test API</button>
                {test&&<p className={!test.reachable?'callout error':''}>Test only: {test.reachable?`${test.fresh?'Live':'Stale / waiting for vehicle'} · Vehicle ${test.status.system_id??'?'} / ${test.status.component_id??'?'} · ${test.status.state||'unknown state'}`:test.error}. Active target unchanged.</p>}
                <p>Active API: <code>{connections.effective?.boat_url||'Unconfigured'}</code><br/>{apiState} · Last reported vehicle {status?.system_id??'?'} / {status?.component_id??'?'}<br/>Heartbeat age: {status?.connection_lost?'unknown':status?.heartbeat_age_s?.toFixed(1)??'—'} s · Position age: {status?.connection_lost?'unknown':status?.position_age_s?.toFixed(1)??'—'} s</p>
                {status?.connection_error&&<p className="callout error">{status.connection_error}</p>}
                <p>Changing this address clears maps, run reviews, approvals, upload authority and return targets in every tab. The current boat must be disarmed, stopped and outside AUTO.</p>
                <label><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>I acknowledge that the old boat’s state may be unknown. Switch without sending Stop or Disarm.</label>
            </section>
            <section><h3>Map telemetry</h3>
                <label>Transport <select value={serial?'serial':'udp'} disabled={busy} onChange={e=>radio('connection',e.target.value==='serial'?'/dev/gcs-radio':'udpin:127.0.0.1:14550')}><option value="udp">UDP</option><option value="serial">Serial / RFD</option></select></label>
                {serial?<>
                    <label>Accessible serial device <input list="connection-devices" value={settings.telemetry.connection} disabled={busy} onChange={e=>radio('connection',e.target.value)}/><datalist id="connection-devices">{devices?.devices.map(d=><option key={d.device} value={d.device}>{d.present?(d.accessible?'Accessible':'Permission denied'):'Missing'}</option>)}</datalist></label>
                    <button disabled={busy} onClick={()=>work(refreshDevices)}>Refresh devices</button>
                    {devices&&<><ul>{devices.devices.map(d=><li key={d.device}><code>{d.device}</code> · {d.present?(d.accessible?'Accessible':'Permission denied'):'Missing'}</li>)}</ul><p>{devices.help}</p></>}
                    <label>Baud <input type="number" disabled={busy} value={settings.telemetry.baud} onChange={e=>radio('baud',Number(e.target.value))}/></label>
                </>:<label>UDP listening address and port <input value={settings.telemetry.connection} placeholder="udpin:127.0.0.1:14550" disabled={busy} onChange={e=>radio('connection',e.target.value)}/></label>}
                <div className="connection-ids">{[['system_id','Expected vehicle ID'],['component_id','Expected component ID']].map(([key,label])=><label key={key}>{label}<input type="number" disabled={busy} min="1" max="255" value={settings.telemetry[key]} onChange={e=>radio(key,Number(e.target.value))}/></label>)}</div>
                <p>Active feed: <code>{connections.effective?.telemetry?.connection||'Unconfigured'}</code><br/>{linkLabel(telemetryStale&&telemetry?.connection_state==='live'?'stale':telemetry?.connection_state)} · Heartbeat age: {telemetry?.heartbeat_age_s?.toFixed(1)??'—'} s · Position age: {telemetry?.position_age_s?.toFixed(1)??'—'} s</p>
                {telemetry?.error&&<p className="callout error">{telemetry.error}. Check the UDP port is free, or USB Docker mapping and device permissions, then retry this endpoint.</p>}
                <p>Passive only: no heartbeat, rate requests or commands. Telemetry changes retain your reviewed mission.</p>
            </section>
        </div>
        {connections.identity_mismatch&&<p className="callout error">Vehicle identity mismatch. Correct the API target or expected telemetry IDs. Upload and Start are blocked while both links report different vehicles.</p>}
        {!!connections.unresolved?.length&&<div className="callout error"><p>Unresolved vehicle commands block Apply. Inspect status and operation results before reconciling unknown outcomes.</p><ul>{connections.unresolved.map(o=><li key={o.operation_id}>{o.command||o.operation_id} · {o.state} · {o.detail}</li>)}</ul><label><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>I reviewed the current boat’s state and want to resolve unknown outcomes when it is freshly disarmed and stopped outside AUTO.</label><button disabled={busy} onClick={()=>work(async()=>{const value=await load('connections/reconcile','POST',{revision,acknowledge_unknown:ack});onUpdate(value);})}>Reconcile status / operations</button></div>}
        {error&&<p role="alert" className="callout error">{error}</p>}{note&&<p role="status">{note}</p>}
        <footer><button disabled={busy} onClick={()=>{setProfile('Simulator');setSettings(structuredClone(connections.simulator_defaults));setTest(null);setAck(false);}}>Use built-in Simulator defaults</button><button disabled={busy||conflict} onClick={()=>save(false)}>Save profile</button><button disabled={busy||conflict} onClick={()=>save(true)}>{busy?'Connecting / checking…':'Apply & connect'}</button></footer>
    </dialog>;
}
