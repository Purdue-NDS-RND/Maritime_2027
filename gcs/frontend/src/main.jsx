import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './style.css';

async function api(path, method='GET', body) {
    const response = await fetch('/api/' + path, {method, headers: {'Content-Type':'application/json'}, body: body === undefined ? undefined : JSON.stringify(body)});
    const value = await response.json();
    if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : JSON.stringify(value.detail));
    return value;
}
const blank = () => ({task:'gate_only',start_heading_deg:90,waypoints:[], start:{latitude:51.566151,longitude:-4.034345}, finish:{latitude:51.566151,longitude:-4.034345},speed_m_s:0.5,clearance_m:0.25,finish_radius_m:1,navigation_profile_id:'',passages:[]});
const latlng = p => [p.latitude,p.longitude];
const point = p => ({latitude:p.lat,longitude:p.lng});
const icon = (text, colour) => L.divIcon({className:'map-label', html:`<span style="background:${colour}">${text}</span>`,iconAnchor:[12,12]});
function App() {
    const [workspace,setWorkspace]=useState({map:null,draft:null,approval:null});
    const [profiles,setProfiles]=useState([]), [status,setStatus]=useState(null), [received,setReceived]=useState(0);
    const [message,setMessage]=useState('Import a simulator object map to begin.'), [validation,setValidation]=useState(null);
    const [passageText,setPassageText]=useState('[]'), [passageError,setPassageError]=useState('');
    const [dirty,setDirty]=useState(false), [busy,setBusy]=useState(false), [tiles,setTiles]=useState(false), [tileError,setTileError]=useState(false);
    const [operations,setOperations]=useState(()=>JSON.parse(localStorage.getItem('maritime-operations')||'[]'));
    const [results,setResults]=useState({});
    const mapRef=useRef(), layers=useRef(), tileRef=useRef(), vehicleLayer=useRef(), current=useRef(), [ready,setReady]=useState(false);
    const draft=workspace.draft||blank();
    current.current={workspace,draft,edit};
    function edit(next) {
        setWorkspace(w=>({...w,draft:next,approval:null})); setDirty(true); setValidation(null);
    }
    function editPassages(text) {
        setPassageText(text);
        try {const roles=JSON.parse(text);if(!Array.isArray(roles))throw new Error();setPassageError('');edit({...draft,passages:roles});}
        catch {setPassageError('Passage roles must be a valid JSON list.');setWorkspace(w=>({...w,approval:null}));setDirty(true);setValidation(null);}
    }
    useEffect(()=>{
        const map=L.map('course-map',{attributionControl:true,maxZoom:24}).setView([51.566151,-4.034345],20);
        mapRef.current=map; layers.current=L.layerGroup().addTo(map); vehicleLayer.current=L.layerGroup().addTo(map);
        map.on('click',e=>{const {draft,edit}=current.current;edit({...draft,waypoints:[...draft.waypoints,point(e.latlng)]});});
        setReady(true);
        api('workspace').then(w=>{setWorkspace(w);setPassageText(JSON.stringify(w.draft?.passages||[],null,2));setPassageError('');if(w.map)map.fitBounds([latlng(w.map.geographic_reference),...w.map.buoys.map(b=>latlng(b.centre))],{padding:[60,60],maxZoom:22});}).catch(e=>setMessage(e.message));
        api('profiles').then(setProfiles).catch(e=>setMessage(e.message));
        return ()=>map.remove();
    },[]);
    useEffect(()=>{
        let active=true;
        async function poll(){try {const value=await api('status');if(active){setStatus(value);setReceived(Date.now());}}catch {if(active)setStatus(s=>s?{...s,connection_lost:true}:null);}}
        poll();const timer=setInterval(poll,1000);return()=>{active=false;clearInterval(timer);};
    },[]);
    useEffect(()=>{
        localStorage.setItem('maritime-operations',JSON.stringify(operations));
        let active=true;
        async function poll(){for(const id of operations){try {const value=await api('operations/'+encodeURIComponent(id));if(active)setResults(r=>({...r,[id]:value}));}catch{}}}
        poll();const timer=setInterval(poll,1000);return()=>{active=false;clearInterval(timer);};
    },[operations]);
    useEffect(()=>{
        if(!ready)return;
        if(tileRef.current){tileRef.current.remove();tileRef.current=null;}
        setTileError(false);
        if(tiles){const tile=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:24,maxNativeZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'});tile.on('tileerror',()=>setTileError(true));tile.addTo(mapRef.current);tileRef.current=tile;}
    },[tiles,ready]);
    useEffect(()=>{
        if(!ready)return; const group=layers.current;group.clearLayers();
        const {map}=workspace;
        if(map) for(const [i,b] of map.buoys.entries()){
            const colour={red:'#e74b50',green:'#35c78b',white:'#dfe7f2',blue:'#4e9feb'}[b.category]||'#999';
            L.circle(latlng(b.centre),{radius:b.radius_m,color:colour,fillOpacity:0.7}).addTo(group).bindTooltip(b.id,{permanent:true,direction:'top',className:'buoy-tooltip'});
            if(validation)L.circle(latlng(b.centre),{radius:b.radius_m+validation.swept_radius_m,color:'#e9ac53',weight:1,dashArray:'4 4',fillOpacity:0.04}).addTo(group);
        }
        if(draft.waypoints.length)L.polyline([latlng(draft.start),...draft.waypoints.map(latlng)],{color:'#6ea9ff',weight:3}).addTo(group);
        for(const [i,p]of draft.waypoints.entries()){
            const marker=L.marker(latlng(p),{draggable:true,icon:icon(i+1,'#487dce')}).addTo(group);
            marker.on('dragend',()=>{const {draft,edit}=current.current;edit({...draft,waypoints:draft.waypoints.map((v,n)=>n===i?point(marker.getLatLng()):v)});});
            marker.bindTooltip('Waypoint '+(i+1)+' · drag to edit');
        }
        L.marker(latlng(draft.start),{icon:icon('S','#596579')}).addTo(group).bindTooltip('Validated start');
        L.circle(latlng(draft.finish),{radius:draft.finish_radius_m,color:'#ab91f2',fillOpacity:0.1}).addTo(group).bindTooltip('Finish area');

        for(const failure of validation?.errors||[])if(failure.location&&map){const [x,y]=failure.location;const ref=map.geographic_reference;const lat=ref.latitude+y/111319.49079327357;const lon=ref.longitude+x/(111319.49079327357*Math.cos(lat*Math.PI/180));L.circleMarker([lat,lon],{radius:10,color:'#ff5d68'}).addTo(group).bindTooltip(failure.reason);}
    },[workspace,validation,ready]);
    useEffect(()=>{
        if(!ready)return; vehicleLayer.current.clearLayers();
        if(status?.position)L.marker(latlng(status.position),{icon:icon('▲','#ffbd69')}).addTo(vehicleLayer.current).bindTooltip(`Boat · ${status.heading_deg?.toFixed(1)??'?'}°`);
    },[status,ready]);
    async function save(){if(passageError)throw new Error(passageError);const value=await api('workspace','PUT',{draft});setWorkspace(value);setDirty(false);return value;}
    async function action(name){setBusy(true);try{
        if(['validate','approve'].includes(name)&&dirty)await save();
        if(['upload','start'].includes(name)&&dirty)throw new Error('Save, validate and approve the edited route first.');
        const value=await api(name,'POST');
        if(name==='validate')setValidation(value);
        if(name==='approve'){setWorkspace(w=>({...w,approval:value}));setValidation(value.validation);}
        if(value.operation_id)setOperations(ids=>[...new Set([...ids,value.operation_id])]);
        setMessage(value.operation_id?'Request received. Confirm the operation result below.':name==='validate'?(value.valid?'Route validation passed.':`${value.errors.length} validation failures.`):'Route approved. Upload and Start remain separate.');
    }catch(e){setMessage(e.message);}finally{setBusy(false);}}
    async function importMap(event){const file=event.target.files[0];if(!file)return;try{const objectMap=JSON.parse(await file.text());const next={...blank(),start:objectMap.geographic_reference,finish:objectMap.geographic_reference};const value=await api('workspace','PUT',{map:objectMap,draft:next});setWorkspace(value);setPassageText('[]');setPassageError('');setDirty(false);setValidation(null);mapRef.current.fitBounds([latlng(objectMap.geographic_reference),...objectMap.buoys.map(b=>latlng(b.centre))],{padding:[60,60],maxZoom:22});setMessage('Map imported. Click the workspace to add waypoints.');}catch(e){setMessage(e.message);}}
    const stale=!status||status.connection_lost||status.heartbeat_age_s===null||status.heartbeat_age_s>3||status.position_age_s===null||status.position_age_s>3||Date.now()-received>3500;
    function updatePoint(index,key,value){edit({...draft,waypoints:draft.waypoints.map((p,i)=>i===index?{...p,[key]:Number(value)}:p)});}
    return <main>
      <header><div><span className="eyebrow">MARITIME / MILESTONE 1</span><h1>Course workspace</h1></div><span className={'state '+(stale?'warning':'')}>{stale?'Telemetry stale / unavailable':status.state}</span></header>
      <div className="layout"><section className="map-panel"><div className="map-toolbar"><label className="button">Import object map<input aria-label="Import object map" type="file" accept=".json" onChange={importMap} hidden/></label><span>Click to add · drag to move</span><label><input type="checkbox" checked={tiles} onChange={e=>setTiles(e.target.checked)}/> OSM background</label></div><div id="course-map"/><div className="map-caption">{tileError?'Background unavailable. Course editing remains available.':workspace.map?`${workspace.map.buoys.length} buoys · captured ${workspace.map.captured_at}`:'Offline map · tiles optional'}</div></section>
      <aside><h2>Mission settings</h2><div className="fields">{[['speed_m_s','Target speed (m/s)',0.1],['clearance_m','Hull clearance (m)',0.05],['finish_radius_m','Finish radius (m)',0.1],['start_heading_deg','Start heading (degrees)',0.1]].map(([key,label,step])=><label key={key}>{label}<input type="number" step={step} value={draft[key]} onChange={e=>edit({...draft,[key]:Number(e.target.value)})}/></label>)}<label>Measured navigation profile<select aria-label="Navigation profile" value={draft.navigation_profile_id} onChange={e=>edit({...draft,navigation_profile_id:e.target.value})}><option value="">Select profile</option>{profiles.map(p=><option key={p.id} value={p.id}>{p.id} · {p.status}</option>)}</select></label></div>{!profiles.length&&<p className="note">No calibrated profile installed. Editing and saving are available; approval requires measured tracking evidence.</p>}
      <h2>Route <small>{draft.waypoints.length} waypoints</small></h2><div className="waypoints">{draft.waypoints.map((p,i)=><div className="waypoint" key={i}><b>{i+1}</b><input aria-label={`Waypoint ${i+1} latitude`} type="number" step="0.0000001" value={p.latitude} onChange={e=>updatePoint(i,'latitude',e.target.value)}/><input aria-label={`Waypoint ${i+1} longitude`} type="number" step="0.0000001" value={p.longitude} onChange={e=>updatePoint(i,'longitude',e.target.value)}/><button aria-label={`Move waypoint ${i+1} up`} disabled={!i} onClick={()=>{const points=[...draft.waypoints];[points[i-1],points[i]]=[points[i],points[i-1]];edit({...draft,waypoints:points});}}>↑</button><button aria-label={`Delete waypoint ${i+1}`} onClick={()=>edit({...draft,waypoints:draft.waypoints.filter((_,n)=>n!==i)})}>×</button></div>)}</div><div className="secondary-actions"><button disabled={!draft.waypoints.length} onClick={()=>edit({...draft,finish:draft.waypoints.at(-1)})}>Use last waypoint as finish</button><button disabled={stale} onClick={()=>edit({...draft,start:status.position,start_heading_deg:status.heading_deg})}>Use boat as start</button><button onClick={async()=>{try{await save();setMessage('Draft saved.');}catch(e){setMessage(e.message);}}}>Save draft</button></div>
      <h2>Course order / sides</h2><label>Course task <select value={draft.task||'gate_only'} onChange={e=>edit({...draft,task:e.target.value})}><option value="gate_only">Entrance gate only</option><option value="slalom">Full slalom</option></select></label><p className="note">Enter ordered passage roles as JSON. Gate: id, kind, red, green. Turn: id, kind, buoy, side (left/right of course direction).</p><textarea aria-label="Course passage order" value={passageText} onChange={e=>editPassages(e.target.value)}/>{passageError&&<p className="error" role="alert">{passageError}</p>}
      <h2>Operator actions</h2><div className="commands">{['validate','approve','upload','start','stop','disarm'].map(name=><button key={name} className={name==='stop'?'stop':''} disabled={(busy&&name!=='stop')||(passageError&&['validate','approve','upload','start'].includes(name))||(['upload','start'].includes(name)&&(!workspace.approval||dirty||stale))||(name==='disarm'&&stale)} onClick={()=>action(name)}>{name[0].toUpperCase()+name.slice(1)}</button>)}</div><p className="approval">{dirty?'Unsaved changes · approval revoked':workspace.approval?'Approved revision '+workspace.approval.envelope.revision_sha256.slice(0,12):'Draft · no current approval'}</p></aside></div>
      <section className="feedback" aria-live="polite"><p>{message}</p>{validation?.errors.map((e,i)=><p className="error" key={i}>{e.reason}</p>)}<div className="telemetry">{status&&<><span>Mode {status.mode} · {status.armed?'ARMED':'disarmed'}</span><span>Speed {status.speed_m_s?.toFixed(2)??'—'} m/s · heading {status.heading_deg?.toFixed(1)??'—'}°</span><span>Item {status.current_item??'—'} / {status.route_waypoint_count}</span><span>{status.detail}</span></>}</div>{operations.map(id=><p className="operation" key={id}>{results[id]?.command||'Operation'} · {results[id]?.state||'outcome unknown'} · {results[id]?.detail||id}</p>)}{workspace.map&&<details><summary>Scene identity</summary><code>{workspace.map.scene_id}</code><p>Run {workspace.map.run_id}</p></details>}</section>
    </main>;
}
createRoot(document.getElementById('root')).render(<App/>);
