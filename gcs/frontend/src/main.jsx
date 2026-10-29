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
const blank = () => ({task:'gate_only',waypoints:[], start:{latitude:51.566151,longitude:-4.034345}, finish:{latitude:51.566151,longitude:-4.034345},speed_m_s:0.5,clearance_m:1.8,finish_radius_m:1,passages:[]});
const mapBounds = map => [latlng(map.start_pose?.position||map.geographic_reference),...map.buoys.map(b=>latlng(b.centre)),...(map.obstacles||[]).flatMap(o=>o.footprint?.map(latlng)||[latlng(o.centre)]),...(map.stations||[]).map(s=>latlng(s.position))];
const latlng = p => [p.latitude,p.longitude];
const point = p => ({latitude:p.lat,longitude:p.lng});
const icon = (text, colour) => L.divIcon({className:'map-label', html:`<span style="background:${colour}">${text}</span>`,iconAnchor:[12,12]});
function boatSymbol(heading, stale) {
    const known=Number.isFinite(heading);
    return L.divIcon({
        className:`boat-marker${stale?' boat-marker-stale':''}`,
        iconSize:[80,96], iconAnchor:[40,56],
        html:`<svg viewBox="0 0 80 96" aria-hidden="true">
            <circle class="boat-halo" cx="40" cy="56" r="24"/>
            ${known?`<g transform="rotate(${heading} 40 56)">
                <path class="boat-heading-outline" d="M40 29V7M33 15L40 7L47 15"/>
                <path class="boat-heading" d="M40 29V7M33 15L40 7L47 15"/>
                <path class="boat-hull-outline" d="M40 32Q54 42 54 55V74Q40 79 26 74V55Q26 42 40 32Z"/>
                <path class="boat-hull" d="M40 32Q54 42 54 55V74Q40 79 26 74V55Q26 42 40 32Z"/>
                <path class="boat-bow" d="M34 45L40 39L46 45"/>
                <rect class="boat-cabin" x="33" y="52" width="14" height="15" rx="3"/>
                <path class="boat-stern" d="M33 71H47"/>
            </g>`:'<circle class="boat-unknown" cx="40" cy="56" r="12"/><text class="boat-question" x="40" y="62">?</text>'}
        </svg>`
    });
}
function headingLabel(heading) {
    if(!Number.isFinite(heading))return 'Heading unknown';
    const compass=['N','NE','E','SE','S','SW','W','NW'][Math.round(heading/45)%8];
    return `${compass} ${String(Math.round(heading)%360).padStart(3,'0')}°`;
}
function App() {
    const [workspace,setWorkspace]=useState({map:null,draft:null,approval:null});
    const [status,setStatus]=useState(null), [received,setReceived]=useState(0);
    const [telemetry,setTelemetry]=useState(null), [telemetryReceived,setTelemetryReceived]=useState(0), [now,setNow]=useState(Date.now());
    const boatMarker=useRef();
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
        api('workspace').then(w=>{setWorkspace(w);setPassageText(JSON.stringify(w.draft?.passages||[],null,2));setPassageError('');if(w.migration_notice)setMessage(w.migration_notice);if(w.map)map.fitBounds(mapBounds(w.map),{padding:[60,60],maxZoom:22});}).catch(e=>setMessage(e.message));
        return ()=>map.remove();
    },[]);
    useEffect(()=>{
        let active=true;
        let timer, controller;
        async function poll(){controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),5500);try {const response=await fetch('/api/status',{signal:controller.signal});if(!response.ok)throw new Error();const value=await response.json();if(active){setStatus(value);setReceived(Date.now());}}catch {if(active)setStatus(s=>s?{...s,connection_lost:true}:null);}finally{clearTimeout(timeout);if(active)timer=setTimeout(poll,1000);}}
        poll();return()=>{active=false;clearTimeout(timer);controller?.abort();};
    },[]);
    useEffect(()=>{
        const stream=new EventSource('/api/telemetry/events');
        stream.onmessage=event=>{const value=JSON.parse(event.data);setTelemetry(value);setTelemetryReceived(Date.now());};
        stream.onerror=()=>setTelemetry(t=>t?{...t,stale:true,connection_state:'disconnected'}:null);
        const timer=setInterval(()=>setNow(Date.now()),250);
        return()=>{stream.close();clearInterval(timer);};
    },[]);
    const telemetryStale=!telemetry||telemetry.stale||now-telemetryReceived>1500;
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
            const colour={red:'#e74b50',green:'#35c78b',white:'#dfe7f2',blue:'#4e9feb',orange:'#fa8b24',purple:'#b15ce5',yellow:'#eed831',cyan:'#25d9df',black:'#151515',zebra:'#ffffff'}[b.category]||'#999';
            L.circle(latlng(b.centre),{radius:b.radius_m,color:colour,fillOpacity:0.7}).addTo(group).bindTooltip(document.createTextNode(b.id),{permanent:!['identify','reference'].includes(b.task),direction:'top',className:'buoy-tooltip'});
            if(b.category==='zebra')L.marker(latlng(b.centre),{interactive:false,icon:L.divIcon({className:'zebra-marker',iconSize:[16,16],iconAnchor:[8,8]})}).addTo(group);
            if(validation)L.circle(latlng(b.centre),{radius:b.radius_m+validation.swept_radius_m,color:'#e9ac53',weight:1,dashArray:'4 4',fillOpacity:0.04}).addTo(group);
        }
        if(map)for(const obj of map.obstacles||[]){
            const style={color:obj.task==='launch'?'#20252b':obj.task==='recover'?'#edcc35':obj.task==='evade'?'#bd79e4':'#99724d',fillOpacity:0.65,weight:2};
            const shape=obj.type==='polygon'?L.polygon(obj.footprint.map(latlng),style):L.circle(latlng(obj.centre),{...style,radius:obj.radius_m});
            shape.addTo(group).bindTooltip(document.createTextNode(obj.id),{permanent:true,direction:'top',className:'buoy-tooltip'});
            if(validation&&obj.type==='cylinder')L.circle(latlng(obj.centre),{radius:obj.radius_m+validation.swept_radius_m,color:'#e9ac53',dashArray:'4 4',fillOpacity:0.04}).addTo(group);
        }
        if(map)for(const station of map.stations||[]){
            if(station.radius_m)L.circle(latlng(station.position),{radius:station.radius_m,color:'#eee',weight:1,dashArray:'3 5',fillOpacity:0,interactive:false}).addTo(group);
            else L.marker(latlng(station.position),{interactive:false,icon:L.divIcon({className:'station-anchor',html:'',iconSize:[0,0]})}).addTo(group).bindTooltip(document.createTextNode(station.label),{permanent:true,direction:'center',className:'station-tooltip'});
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
        if(!ready||(!telemetry?.position&&!boatMarker.current))return;
        if(!boatMarker.current)boatMarker.current=L.marker(latlng(telemetry.position),{zIndexOffset:1000,title:'Boat position and heading'})
            .addTo(vehicleLayer.current).bindTooltip('Boat',{permanent:true,direction:'bottom',offset:[0,25],className:'boat-tooltip'});
        const heading=telemetry?.heading_deg??null;
        if(telemetry?.position)boatMarker.current.setLatLng(latlng(telemetry.position));
        boatMarker.current.setIcon(boatSymbol(heading,telemetryStale))
            .setTooltipContent(`${telemetryStale?'Last known':'Boat'} · ${headingLabel(heading)}`);
    },[telemetry,telemetryStale,ready]);
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
    async function importMap(event){const file=event.target.files[0];if(!file)return;try{const objectMap=JSON.parse(await file.text());const next={...blank(),task:objectMap.schema_version===2?'custom':'gate_only',start:objectMap.start_pose?.position||objectMap.geographic_reference,finish:objectMap.start_pose?.position||objectMap.geographic_reference};const value=await api('workspace','PUT',{map:objectMap,draft:next});setWorkspace(value);setPassageText('[]');setPassageError('');setDirty(false);setValidation(null);mapRef.current.fitBounds(mapBounds(objectMap),{padding:[60,60],maxZoom:22});setMessage('Map imported. Click the workspace to add waypoints.');}catch(e){setMessage(e.message);}}
    const stale=!status||status.connection_lost||status.heartbeat_age_s===null||status.heartbeat_age_s>3||status.position_age_s===null||status.position_age_s>3||now-received>3500;
    function updatePoint(index,key,value){edit({...draft,waypoints:draft.waypoints.map((p,i)=>i===index?{...p,[key]:Number(value)}:p)});}
    return <main>
      <header><div><span className="eyebrow">MARITIME / MILESTONE 1</span><h1>Course workspace</h1></div><span className={'state '+(telemetryStale?'warning':'')}>{telemetryStale?'Position stale / unavailable':'Live boat position'}</span></header>
      <div className="layout"><section className="map-panel"><div className="map-toolbar"><label className="button">Import object map<input aria-label="Import object map" type="file" accept=".json" onChange={importMap} hidden/></label><span>Click to add · drag to move</span><label><input type="checkbox" checked={tiles} onChange={e=>setTiles(e.target.checked)}/> OSM background</label></div><div id="course-map"/><div className="map-caption">{tileError?'Background unavailable. Course editing remains available.':workspace.map?`${workspace.map.buoys.length} buoys · ${workspace.map.obstacles?.length||0} props · captured ${workspace.map.captured_at}`:'Offline map · tiles optional'}</div></section>
      <aside><h2>Mission settings</h2><div className="fields">{[['speed_m_s','Target speed (m/s)',0.1],['clearance_m','Total clearance buffer (m)',0.05],['finish_radius_m','Finish radius (m)',0.1]].map(([key,label,step])=><label key={key}>{label}<input type="number" step={step} value={draft[key]??''} onChange={e=>edit({...draft,[key]:e.target.value===''?null:Number(e.target.value)})}/></label>)}</div><p className="note">Buffer is the total distance from the boat position to every obstacle surface. Include boat size and room for positioning and tracking error.</p>
      <h2>Route <small>{draft.waypoints.length} waypoints</small></h2><div className="waypoints">{draft.waypoints.map((p,i)=><div className="waypoint" key={i}><b>{i+1}</b><input aria-label={`Waypoint ${i+1} latitude`} type="number" step="0.0000001" value={p.latitude} onChange={e=>updatePoint(i,'latitude',e.target.value)}/><input aria-label={`Waypoint ${i+1} longitude`} type="number" step="0.0000001" value={p.longitude} onChange={e=>updatePoint(i,'longitude',e.target.value)}/><button aria-label={`Move waypoint ${i+1} up`} disabled={!i} onClick={()=>{const points=[...draft.waypoints];[points[i-1],points[i]]=[points[i],points[i-1]];edit({...draft,waypoints:points});}}>↑</button><button aria-label={`Delete waypoint ${i+1}`} onClick={()=>edit({...draft,waypoints:draft.waypoints.filter((_,n)=>n!==i)})}>×</button></div>)}</div><div className="secondary-actions"><button disabled={!draft.waypoints.length} onClick={()=>edit({...draft,finish:draft.waypoints.at(-1)})}>Use last waypoint as finish</button><button disabled={stale} onClick={()=>edit({...draft,start:status.position})}>Use boat as start</button><button onClick={async()=>{try{await save();setMessage('Draft saved.');}catch(e){setMessage(e.message);}}}>Save draft</button></div>
      <h2>Course order / sides</h2><label>Course task <select value={draft.task||'gate_only'} onChange={e=>edit({...draft,task:e.target.value})}><option value="gate_only">Entrance gate only</option><option value="slalom">Full slalom</option><option value="custom">Custom route (clearance only)</option></select></label><p className="note">Custom routes need no passage list. Gate/slalom regression routes require ordered passage roles as JSON. Gate: id, kind, red, green. Turn: id, kind, buoy, side (left/right of course direction).</p><textarea aria-label="Course passage order" value={passageText} onChange={e=>editPassages(e.target.value)}/>{passageError&&<p className="error" role="alert">{passageError}</p>}
      <h2>Operator actions</h2><div className="commands">{['validate','approve','upload','start','stop','disarm'].map(name=><button key={name} className={name==='stop'?'stop':''} disabled={(busy&&name!=='stop')||(passageError&&['validate','approve','upload','start'].includes(name))||(['upload','start'].includes(name)&&(!workspace.approval||dirty||stale))||(name==='disarm'&&stale)} onClick={()=>action(name)}>{name[0].toUpperCase()+name.slice(1)}</button>)}</div><p className="approval">{dirty?'Unsaved changes · approval revoked':workspace.approval?'Approved revision '+workspace.approval.envelope.revision_sha256.slice(0,12):'Draft · no current approval'}</p></aside></div>
      <section className="feedback" aria-live="polite"><p>{message}</p>{validation?.errors.map((e,i)=><p className="error" key={i}>{e.reason}</p>)}<div className="telemetry"><span>MAVLink {telemetry?.system_id??'—'} · {telemetry?.connection_state??'waiting'} · position age {telemetry?.position_age_s==null?'—':(telemetry.position_age_s+Math.max(0,now-telemetryReceived)/1000).toFixed(1)+' s'}</span><span>Speed {telemetry?.speed_m_s?.toFixed(2)??'—'} m/s · heading {telemetry?.heading_deg?.toFixed(1)??'—'}°</span><span>Boat mission API {stale?'stale / unavailable':status?.state}</span>{status&&<><span>Boat app mode {status.mode} · {status.armed?'ARMED':'disarmed'}</span><span>Item {status.current_item??'—'} / {status.route_waypoint_count}</span><span>{status.detail}</span></>}</div>{operations.map(id=><p className="operation" key={id}>{results[id]?.command||'Operation'} · {results[id]?.state||'outcome unknown'} · {results[id]?.detail||id}</p>)}{workspace.map&&<details><summary>Scene identity</summary><code>{workspace.map.scene_id}</code><p>Run {workspace.map.run_id}</p></details>}</section>
    </main>;
}
createRoot(document.getElementById('root')).render(<App/>);
