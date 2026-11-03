import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './style.css';
import Planner from './Planner';
import Feedback from './Feedback';
import {errorText,freshStatus,operationNotice} from './readiness';
import {defaultSettings,effectiveSettings,towerZones,routeIsVisible,settingsError} from './settings';
import BoatControls from './BoatControls';
import {configuration,heading,friendly} from './workflow';
import {boundaryBands,local,gps,expandedFootprint,insetBoundary,crossingWindow} from './buffers';

async function api(path, method='GET', body) {
    const response = await fetch('/api/' + path, {method, headers: {'Content-Type':'application/json'}, body: body === undefined ? undefined : JSON.stringify(body)});
    let value;
    try{value=await response.json();}catch{throw new Error(`GCS returned HTTP ${response.status} without a readable response. Check the connection before retrying.`);}
    if (!response.ok) {const error=new Error(errorText(value.detail));error.detail=value.detail;error.errors=value.detail?.errors;throw error;}
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
    const [step,setStep]=useState(1), [selected,setSelected]=useState('');
    const [mode,setMode]=useState('inspect'), [labels,setLabels]=useState(false), [stations,setStations]=useState(false), [overlays,setOverlays]=useState(true);
    const [buffers,setBuffers]=useState(false);
    const [activeTask,setActiveTask]=useState(null),[generatedTasks,setGeneratedTasks]=useState([]);
    const settingsChanged=useRef(false),serverSession=useRef(null);
    const mapChanged=useRef(false), pendingWork=useRef(0);
    const [workspace,setWorkspace]=useState({map:null,draft:null,approval:null});
    const [status,setStatus]=useState(null), [received,setReceived]=useState(0);
    const [telemetry,setTelemetry]=useState(null), [telemetryReceived,setTelemetryReceived]=useState(0), [now,setNow]=useState(Date.now());
    const boatMarker=useRef();
    const [focusedFailure,setFocusedFailure]=useState(null);
    const [message,updateMessage]=useState('Load the full competition map, review object sizes, then choose a task.'), [validation,setValidation]=useState(null);
    const [notice,setNotice]=useState(null),[workLabel,setWorkLabel]=useState('Working…'),[startedAt,setStartedAt]=useState(0);
    function setMessage(text,kind='info',errors=[]){updateMessage(text);setNotice({text,detail:text,kind,errors});}
    function reportError(error){updateMessage(error.message);setNotice({kind:'error',text:error.message,detail:error.detail||error.message,errors:error.errors||[]});}
    const [dirty,setDirty]=useState(false), [busy,setBusy]=useState(false), [tiles,setTiles]=useState(false), [tileError,setTileError]=useState(false);
    const [operations,setOperations]=useState(()=>JSON.parse(localStorage.getItem('maritime-operations')||'[]'));
    const [results,setResults]=useState({});
    const watchedOperations=useRef(new Set());
    const mapRef=useRef(), layers=useRef(), tileRef=useRef(), vehicleLayer=useRef(), current=useRef(), [ready,setReady]=useState(false);
    const draft=workspace.draft||blank();
    const routeVisible=routeIsVisible(draft.planner_task,generatedTasks,activeTask);
    const previewSettings=step===2?effectiveSettings(workspace.game_settings||defaultSettings(draft)):draft;
    function invalidateRoute(){setGeneratedTasks([]);}
    function updateSettings(settings){
        settingsChanged.current=true;invalidateRoute();
        setWorkspace(w=>({...w,game_settings:settings,approval:null}));setDirty(true);setValidation(null);
    }
    async function saveSettings(){await run(async()=>{
        const error=settingsError(workspace.game_settings||defaultSettings(draft));if(error)throw new Error(error);
        settingsChanged.current=true;await save();setStep(3);setMode('inspect');setActiveTask(null);
        setMessage('Configuration saved. Choose a task, review its assignments, then Generate.');
    });}
    function changeWorkspace(w,mapEdit=false,isDirty=true){
        if(mapEdit){invalidateRoute();mapChanged.current=true;for(const config of Object.values(w.course||{})){config.sizes_confirmed=false;config.course_confirmed=false;}if(w.draft){w.draft.sizes_confirmed=false;w.draft.course_confirmed=false;}}
        setWorkspace(w);setDirty(isDirty);setValidation(null);
    }
    current.current={workspace,draft,edit,mode,changeWorkspace,setMode,setSelected,busy};
    function edit(next) {
        setWorkspace(w=>{
            if(next.planner_task){
                const roles=configuration(next);const planner_task=next.planner_task;
                return {...w,draft:next,course:{...w.course,[planner_task]:roles},approval:null};
            }
            return {...w,draft:next,approval:null};
        }); setDirty(true); setValidation(null);
    }
    useEffect(()=>{
        const map=L.map('course-map',{attributionControl:true,maxZoom:24}).setView([51.566151,-4.034345],20);
        mapRef.current=map; layers.current=L.layerGroup().addTo(map); vehicleLayer.current=L.layerGroup().addTo(map);
        map.on('click',e=>{const {draft,edit,workspace,mode,changeWorkspace,setMode}=current.current;
            if(current.current.busy||mode==='inspect')return;
            if(mode==='waypoint'){edit({...draft,waypoints:[...draft.waypoints,point(e.latlng)],...(!draft.planner_task?{finish:point(e.latlng)}:{})});return;}
            const next={...draft,[mode]:['planning_area','channel'].includes(mode)?[...(draft[mode]||[]),point(e.latlng)]:point(e.latlng),course_confirmed:false};
            if(mode==='start'){next.attempt={...draft.attempt,start_source:'manual',selection_confirmed:false};edit(next);setMode('inspect');return;}
            const roles=configuration(next);const planner_task=next.planner_task;
            changeWorkspace({...workspace,draft:next,course:draft.planner_task?{...workspace.course,[draft.planner_task]:roles}:workspace.course,approval:null});
            if(!['planning_area','channel'].includes(mode))setMode('inspect');
        });
        setReady(true);
        api('workspace').then(w=>{setWorkspace(w);if(w.migration_notice)setMessage(w.migration_notice);else if(w.map)updateMessage('Map and settings restored. Course paths stay hidden until you generate them.');if(w.map)map.fitBounds(mapBounds(w.map),{padding:[60,60],maxZoom:22});}).catch(reportError);
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
        stream.onmessage=event=>{const value=JSON.parse(event.data);
            if(serverSession.current&&value.gcs_session_id&&serverSession.current!==value.gcs_session_id){
                setGeneratedTasks([]);setActiveTask(null);setValidation(null);setStep(1);setMode('inspect');
                setMessage('GCS restarted. Saved work is retained; generate task routes when ready.');
            }
            serverSession.current=value.gcs_session_id||serverSession.current;
            setTelemetry(value);setTelemetryReceived(Date.now());};
        stream.onerror=()=>setTelemetry(t=>t?{...t,stale:true,connection_state:'disconnected'}:null);
        const timer=setInterval(()=>setNow(Date.now()),250);
        return()=>{stream.close();clearInterval(timer);};
    },[]);
    const telemetryStale=!telemetry||telemetry.stale||now-telemetryReceived>1500;
    useEffect(()=>{
        localStorage.setItem('maritime-operations',JSON.stringify(operations));
        let active=true;
        async function poll(){for(const id of operations){try {const value=await api('operations/'+encodeURIComponent(id));if(active){setResults(r=>({...r,[id]:value}));if(watchedOperations.current.has(id)){const update=operationNotice(value);if(update){watchedOperations.current.delete(id);updateMessage(update.text);setNotice(update);}}}}catch{}}}
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
            L.circle(latlng(b.centre),{radius:b.radius_m,color:colour,fillOpacity:0.7}).addTo(group).on('click',e=>{L.DomEvent.stopPropagation(e);if(current.current.busy)return;current.current.setSelected(b.id);setStep(b.object_type==='detector'?2:1);if(b.object_type==='detector')setBuffers(true);}).bindTooltip(document.createTextNode(friendly(b.id)),{permanent:labels,direction:'top',className:'buoy-tooltip'});
            if(b.category==='zebra')L.marker(latlng(b.centre),{interactive:false,icon:L.divIcon({className:'zebra-marker',iconSize:[16,16],iconAnchor:[8,8]})}).addTo(group);

        }
        if(map)for(const obj of map.obstacles||[]){
            const style={color:obj.task==='launch'?'#20252b':obj.task==='recover'?'#edcc35':obj.task==='evade'?'#bd79e4':'#99724d',fillOpacity:0.65,weight:2};
            const shape=obj.type==='polygon'?L.polygon(obj.footprint.map(latlng),style):L.circle(latlng(obj.centre),{...style,radius:obj.radius_m});
            shape.addTo(group).on('click',e=>{L.DomEvent.stopPropagation(e);if(current.current.busy)return;current.current.setSelected(obj.id);setStep(obj.object_type==='detector'?2:1);if(obj.object_type==='detector')setBuffers(true);}).bindTooltip(document.createTextNode(friendly(obj.id)),{permanent:labels,direction:'top',className:'buoy-tooltip'});

        }
        if(map&&(buffers||step===2)&&Number.isFinite(previewSettings.clearance_m)&&previewSettings.clearance_m>=0){
            const ref=map.geographic_reference,required=previewSettings.clearance_m,preferred=previewSettings.preferred_buffer_m??required;
            const levels=[{radius:required,color:'#e9ac53',name:'Required'}];
            if(Number.isFinite(preferred)&&preferred>required)levels.unshift({radius:preferred,color:'#83baff',name:'Preferred'});
            for(const {radius,color,name} of levels){
                const style={color,weight:1.5,dashArray:name==='Required'?'5 4':'2 6',fillOpacity:.035,interactive:false};
                for(const obj of [...map.buoys,...(map.obstacles||[])]){
                    if(obj.object_type==='detector'&&previewSettings.tower_avoidance)continue;
                    if(obj.type==='polygon')L.polygon(expandedFootprint(obj.footprint,radius,ref),style).addTo(group);
                    else L.circle(latlng(obj.centre),{...style,radius:obj.radius_m+radius}).addTo(group);
                }
                for(const key of ['planning_area','channel'])if(draft[key]?.length>=3){
                    for(const band of boundaryBands(draft[key],radius,ref))L.polygon(band,{...style,stroke:false,fillOpacity:.08}).addTo(group);
                    for(const vertex of draft[key])L.circle(latlng(vertex),{...style,radius,stroke:false,fillOpacity:.04}).addTo(group);
                    const inset=insetBoundary(draft[key],radius,ref);
                    if(inset?.length)L.polygon(inset,{...style,fillOpacity:0}).addTo(group);
                }
                if(activeTask&&step>=3&&(routeVisible||draft.attempt?.start_source==='manual')&&draft.start)L.circle(latlng(draft.start),{...style,radius}).addTo(group);
                if(activeTask&&step>=3&&draft.finish)L.circle(latlng(draft.finish),{...style,radius:(draft.finish_radius_m||0)+radius}).addTo(group);
            }
        }
        if(map&&(buffers||step===2)&&previewSettings.tower_avoidance){
            for(const obj of [...map.buoys,...(map.obstacles||[])].filter(o=>o.object_type==='detector')){
                const {hard_m:hard,soft_m:soft}=towerZones(obj,previewSettings);
                if(!Number.isFinite(hard)||!Number.isFinite(soft)||hard<0||soft<hard)continue;
                const draw=(distance,style)=>obj.type==='polygon'?L.polygon(expandedFootprint(obj.footprint,distance,map.geographic_reference),style):L.circle(latlng(obj.centre),{...style,radius:obj.radius_m+distance});
                for(let band=6;band>=1;band--)draw(hard+(soft-hard)*band/6,{color:'#ba8aff',weight:band===6?1:0,dashArray:'3 6',fillColor:'#a77bea',fillOpacity:.025,interactive:false}).addTo(group);
                draw(hard,{color:selected===obj.id?'#ffcf83':'#df9afc',weight:selected===obj.id?3:2,fillColor:'#b85ce0',fillOpacity:.18,interactive:false}).addTo(group);
            }
        }
        if(map&&stations)for(const station of map.stations||[]){
            if(station.radius_m)L.circle(latlng(station.position),{radius:station.radius_m,color:'#eee',weight:1,dashArray:'3 5',fillOpacity:0,interactive:false}).addTo(group);
            else L.marker(latlng(station.position),{interactive:false,icon:L.divIcon({className:'station-anchor',html:'',iconSize:[0,0]})}).addTo(group).bindTooltip(document.createTextNode(station.label),{permanent:true,direction:'center',className:'station-tooltip'});
        }
        if(overlays&&map&&activeTask&&step>=3){
            for(const [passageIndex,p] of (draft.passages||[]).entries()){
                const objects=[...map.buoys,...(map.obstacles||[])];
                if(p.kind==='gate'){const a=objects.find(o=>o.id===p.red),b=objects.find(o=>o.id===p.green);if(a&&b)L.polyline([latlng(a.centre),latlng(b.centre)],{color:'#f7df78',dashArray:'3 4'}).addTo(group).bindTooltip(`Gate · ${friendly(p.red)} / ${friendly(p.green)}`);}
                else {const o=objects.find(o=>o.id===p.buoy);if(o)L.marker(latlng(o.centre),{icon:icon(`${passageIndex+1}${p.side==='left'?'L':p.side==='right'?'R':'?'}`,'#766044')}).addTo(group).bindTooltip(`Pass ${p.side||'?'} · ${friendly(p.buoy)} · relative to ${heading(draft.direction)} travel`);}
            }
            for(const [i,section] of (draft.derived_sections||[]).entries()){
                const excluded=draft.attempt?.mode==='remaining'&&i<(draft.attempt.first_section||0);
                if(section.a)L.polyline([latlng(section.a),latlng(section.b)],{color:excluded?'#777':'#f7df78',dashArray:'4 4'}).addTo(group).bindTooltip(`Section ${i+1}${excluded?' · excluded from partial attempt':''}`);
                L.marker(latlng(section.centre),{icon:icon(i+1,excluded?'#666':'#766044')}).addTo(group);
                if(section.direction){const [x,y]=local(section.centre,map.geographic_reference);const d=section.direction;L.polyline([gps([x-2*d[0],y-2*d[1]],map.geographic_reference),gps([x+2*d[0],y+2*d[1]],map.geographic_reference)],{color:'#f7df78'}).addTo(group).bindTooltip('Local travel →');const at=gps([x+3*d[0],y+3*d[1]],map.geographic_reference);L.marker(at,{interactive:false,icon:L.divIcon({className:'travel-arrow',html:`<span style="display:block;transform:rotate(${Math.atan2(d[0],d[1])*180/Math.PI}deg);font-size:26px;color:#f7df78">↑</span>`,iconSize:[24,28],iconAnchor:[12,14]})}).addTo(group);}
            }
            for(const key of ['planning_area','channel'])if(draft[key]?.length)L.polygon(draft[key].map(latlng),{color:key==='channel'?'#44ddb5':'#ffce70',fillOpacity:.03}).addTo(group);
            if(draft.geometry_version!==2&&draft.exit)L.circle(latlng(draft.exit),{radius:draft.exit_radius_m||1,color:'#fff'}).addTo(group).bindTooltip('Exit',{permanent:true,direction:'top',className:'setup-tooltip'});
            if(draft.connection_override){
                const window=crossingWindow({...draft,entry:draft.connection_override},'entry',map.geographic_reference);
                if(window.length)L.polyline(window,{color:'#fff',weight:5}).addTo(group).bindTooltip('Reviewed physical connection crossing',{permanent:true,direction:'top',className:'setup-tooltip'});
            }
            if(draft.geometry_version!==2&&draft.entry){
                const window=crossingWindow(draft,'entry',map.geographic_reference);
                if(window.length)L.polyline(window,{color:'#fff',weight:5}).addTo(group).bindTooltip('Entry · cross here to begin the task',{permanent:true,direction:'top',className:'setup-tooltip'});
            }
            for(const section of validation?.preferred_shortfalls||[]){const route=[draft.start,...draft.waypoints];L.polyline([latlng(route[section.leg]),latlng(route[section.leg+1])],{color:'#ff963f',weight:8}).addTo(group).bindTooltip(`Achieved clearance ${section.clearance_m.toFixed(3)} m`);}
        }
        if(routeVisible&&draft.route_sections?.length)for(const section of draft.route_sections){const route=[draft.start,...draft.waypoints];if(route[section.leg+1])L.polyline([latlng(section.start||route[section.leg]),latlng(section.end||route[section.leg+1])],{color:section.kind==='approach'?'#d9b470':'#6ea9ff',weight:5}).addTo(group).bindTooltip(section.kind==='approach'?'Approach to first included passage':'Task route');}
        if(routeVisible&&draft.waypoints.length&&!draft.route_sections?.length)L.polyline([latlng(draft.start),...draft.waypoints.map(latlng)],{color:'#6ea9ff',weight:3}).addTo(group);
        for(const [i,p]of (routeVisible?draft.waypoints:[]).entries()){
            const marker=L.marker(latlng(p),{draggable:mode==='waypoint'&&!busy,icon:icon(i+1,'#487dce')}).addTo(group);
            marker.on('dragend',()=>{if(current.current.busy)return;const {draft,edit}=current.current;const moved=point(marker.getLatLng());edit({...draft,waypoints:draft.waypoints.map((v,n)=>n===i?moved:v),...(i===draft.waypoints.length-1?{finish:moved}:{})});});
            marker.bindTooltip('Waypoint '+(i+1)+(mode==='waypoint'?' · drag to move':' · enable Edit on map to move'));
        }
        if(activeTask&&step>=3&&(routeVisible||draft.attempt?.start_source==='manual'||activeTask==='manual'))L.marker(latlng(draft.start),{icon:icon('S','#596579')}).addTo(group).bindTooltip('Planning start');
        if(activeTask&&step>=3)L.circle(latlng(draft.finish),{radius:draft.finish_radius_m,color:'#ab91f2',fillOpacity:0.1}).addTo(group).bindTooltip('Finish',{permanent:true,direction:'top',className:'setup-tooltip'});

        for(const failure of [...(validation?.errors||[]),...(draft.generation_errors||[]),...(focusedFailure?[focusedFailure]:[])])if(failure.location&&map){const [x,y]=failure.location;const ref=map.geographic_reference;const lat=ref.latitude+y/111319.49079327357;const lon=ref.longitude+x/(111319.49079327357*Math.cos(lat*Math.PI/180));L.circleMarker([lat,lon],{radius:10,color:'#ff5d68',failureReason:failure.reason}).addTo(group).bindTooltip(failure.reason,{permanent:failure===focusedFailure,direction:'top',className:'failure-tooltip'});}
    },[workspace,validation,ready,labels,stations,overlays,buffers,mode,step,activeTask,routeVisible,selected,focusedFailure,busy]);
    useEffect(()=>{
        if(!ready||(!telemetry?.position&&!boatMarker.current))return;
        if(!boatMarker.current)boatMarker.current=L.marker(latlng(telemetry.position),{zIndexOffset:1000,title:'Boat position and heading'})
            .addTo(vehicleLayer.current).bindTooltip('Boat',{permanent:true,direction:'bottom',offset:[0,25],className:'boat-tooltip'});
        const heading=telemetry?.heading_deg??null;
        if(telemetry?.position)boatMarker.current.setLatLng(latlng(telemetry.position));
        boatMarker.current.setIcon(boatSymbol(heading,telemetryStale))
            .setTooltipContent(`${telemetryStale?'Last known':'Boat'} · ${headingLabel(heading)}`);
    },[telemetry,telemetryStale,ready]);
    function beginWork(label='Working…'){if(!pendingWork.current){setStartedAt(Date.now());setWorkLabel(label);}pendingWork.current++;setBusy(true);}
    function endWork(){pendingWork.current=Math.max(0,pendingWork.current-1);setBusy(pendingWork.current>0);}
    async function run(work){beginWork();try{return await work();}catch(error){reportError(error);}finally{endWork();}}
    async function save(next=current.current.workspace,mapEdit=mapChanged.current){
        const value=await api('workspace','PUT',{draft:next.draft||blank(),course:next.course||{},...(settingsChanged.current?{game_settings:next.game_settings||defaultSettings(draft)}:{}),...(mapEdit?{map:next.map}:{})});
        mapChanged.current=false;settingsChanged.current=false;setWorkspace(value);setDirty(false);return value;
    }
    async function action(name){beginWork({validate:'Validating route',approve:'Approving route',upload:'Requesting upload',start:'Requesting start',stop:'Requesting Hold / Stop',disarm:'Requesting Disarm'}[name]);try{
        if(['validate','approve'].includes(name)&&dirty)await save();
        if(['upload','start'].includes(name)&&dirty)throw new Error('Save, validate and approve the edited route first.');
        const value=await api(name,'POST');
        if(name==='validate'){setValidation(value);if(!value.valid){setMessage(value.errors.map(e=>e.reason).join('; '),'error',value.errors);return;}}
        if(name==='approve'){setWorkspace(w=>({...w,approval:value}));setValidation(value.validation);}
        if(value.operation_id){watchedOperations.current.add(value.operation_id);setOperations(ids=>[...new Set([...ids,value.operation_id])]);}
        setMessage(value.operation_id?'Request received. Waiting for the boat to confirm the result; this is not execution confirmation.':name==='validate'?(value.valid?'Route validation passed.':`${value.errors.length} validation failures.`):'Route approved. Upload and Start remain separate.');
    }catch(e){reportError(e);}finally{endWork();}}
    async function importMap(event){const file=event.target.files[0];if(!file)return;await run(async()=>{
        const value=await api('import','POST',{content:await file.text(),format:file.name.endsWith('.csv')?'csv':'json'});
        await initializeMap(value);setMessage('Map imported. Review its object sizes before task setup.');
    });event.target.value='';}
    async function initializeMap(value){invalidateRoute();setActiveTask(null);
        const position=value.map.start_pose?.position||value.map.geographic_reference;
        const next={...blank(),task:'custom',start:position,finish:position,speed_m_s:draft.speed_m_s,clearance_m:draft.clearance_m,preferred_buffer_m:draft.preferred_buffer_m??draft.clearance_m};
        await save({...value,draft:next});setValidation(null);setStep(1);setSelected('');setMode('inspect');
        mapRef.current.fitBounds(mapBounds(value.map),{padding:[40,40],maxZoom:22});
    }
    async function loadCompetition(){await run(async()=>{
        const objectMap=await api('examples/competition');
        const value=await api('import','POST',{content:JSON.stringify(objectMap)});
        await initializeMap(value);setMessage('Full competition map loaded: 23 buoys and 6 props. Review sizes, then choose a task.');
    });}
    function fitMap(taskOnly=false){
        if(!workspace.map)return;
        const ids=new Set((draft.passages||[]).flatMap(p=>[p.red,p.green,p.buoy]).filter(Boolean));
        const points=taskOnly?[...workspace.map.buoys.filter(o=>ids.has(o.id)).map(o=>latlng(o.centre)),...[draft.entry,draft.exit,draft.finish].filter(Boolean).map(latlng),...(draft.channel||[]).map(latlng)]:mapBounds(workspace.map);
        if(points.length)mapRef.current.fitBounds(points,{padding:[60,60],maxZoom:22});
    }
    function focusFailure(failure){
        if(!failure?.location||!workspace.map)return;
        const centre=gps(failure.location,workspace.map.geographic_reference);
        mapRef.current.setView(centre,Math.max(mapRef.current.getZoom(),22));setBuffers(true);setFocusedFailure(failure);
    }
    async function load(path,...args){
        if(path==='generate')setWorkLabel('Generating route');
        else if(path==='course/geometry')setWorkLabel('Checking task geometry');
        return api(path,...args);
    }
    const stale=!freshStatus(status,now-received);
    return <main>
      <header><div><span className="eyebrow">MARITIME · MISSION PLANNER</span><h1>Course workspace</h1></div><div className="header-actions"><span className={'connection '+(stale?'offline':'')}>{stale?'Boat offline · planning available':'Boat connected'}</span><button className="stop" onClick={()=>action('stop')}>Stop boat</button></div></header>
      <BoatControls status={status} stale={stale} action={action} operations={operations} results={results}/>
      <div className="workspace-layout">
        <section className="map-panel" aria-label="Course map">
          <div className="map-toolbar"><div><strong>{workspace.map?.name||'Course map'}</strong><small>{workspace.map?`${workspace.map.buoys.length} buoys · ${workspace.map.obstacles?.length||0} props`:'Load a map to begin'}</small></div><div className="button-row"><button className={(buffers||step===2)?'buffer-toggle active-tool':'buffer-toggle quiet'} aria-pressed={buffers||step===2} title={step===2?'Buffers stay visible while configuring distances.':'Toggle buffer preview'} onClick={()=>{if(step===2)setMessage('Buffer preview stays visible while configuring distances.');else setBuffers(!buffers);}}>Show buffers</button><button className="quiet" onClick={()=>fitMap()}>Full course</button><button className="quiet" disabled={!draft.planner_task||!activeTask} onClick={()=>fitMap(true)}>Selected task</button><details className="map-options"><summary>Map layers</summary>{[['Object labels',labels,setLabels],['Station annotations',stations,setStations],['Planning overlays',overlays,setOverlays],['Street background',tiles,setTiles]].map(([name,value,set])=><label key={name}><input type="checkbox" checked={value} onChange={e=>set(e.target.checked)}/>{name}</label>)}</details></div></div>
          {(buffers||step===2)&&<div className="buffer-legend"><strong>Buffer preview · required {previewSettings.clearance_m} m · preferred {previewSettings.preferred_buffer_m??previewSettings.clearance_m} m</strong><span>Amber: required clearance. Blue: preferred room. Purple: tower hard exclusion and fading soft avoidance. Tower distances follow the object surface. Task overrides appear when that task is selected. Preview updates before validation; Validate checks the route.</span>{['planning_area','channel'].some(key=>draft[key]?.length>=3&&insetBoundary(draft[key],draft.clearance_m,workspace.map.geographic_reference)===null)&&<span>Boundary clearance bands follow every edge. Validate checks exact segment containment.</span>}{['planning_area','channel'].some(key=>draft[key]?.length>=3&&insetBoundary(draft[key],draft.clearance_m,workspace.map.geographic_reference)?.length===0)&&<span>No room remains inside a boundary at this required buffer.</span>}</div>}
          <div id="course-map"/>
          <div className={'map-instruction '+(mode!=='inspect'?'drawing':'')}><span>{mode==='inspect'?(step===2?'Configuration · click a purple tower to adjust its zones.':'Inspect mode · click an object for details.'):mode==='waypoint'?'Route editing · click to add a waypoint, drag a numbered waypoint to move it.':['planning_area','channel'].includes(mode)?`Drawing ${mode==='channel'?'channel':'planning area'} · click corners in order.`:`Choose ${mode} · click its new position on the map.`}</span>{mode!=='inspect'&&<button onClick={()=>setMode('inspect')}>Done / cancel tool</button>}</div>
          <div className="map-caption"><span>{routeVisible?'Blue: generated route · amber: approach · L/R: reviewed passing sides':'No course route displayed · Generate a task route when ready'}</span>{tileError&&<span>Street background unavailable; planning still works.</span>}</div>
        </section>
        <aside aria-label="Mission workflow"><Planner workspace={workspace} draft={draft} edit={edit} changeWorkspace={changeWorkspace} mode={mode} setMode={setMode} save={save} notify={setMessage} load={load} onFocusFailure={focusFailure} workLabel={workLabel} step={step} setStep={setStep} selected={selected} setSelected={setSelected} routeVisible={routeVisible} taskSelected={!!activeTask} onTaskSelected={setActiveTask} onGenerated={task=>setGeneratedTasks(tasks=>[...new Set([...tasks,task])])} invalidateRoute={invalidateRoute} updateSettings={updateSettings} saveSettings={saveSettings} onImport={importMap} loadCompetition={loadCompetition} validation={validation} action={action} busy={busy} run={run} stale={stale} status={status} dirty={dirty} operations={operations} results={results}/></aside>
      </div>
      <Feedback notice={notice} busy={busy} label={workLabel} elapsed={Math.max(0,Math.floor((now-startedAt)/1000))} onDismiss={()=>{setNotice(null);setFocusedFailure(null);}} onReview={step=>{setStep(step);setMode('inspect');setNotice(null);if(step===4)requestAnimationFrame(()=>{const details=document.getElementById('command-results');if(details){details.open=true;details.scrollIntoView({block:'center'});}});}} onFocus={focusFailure}/>
      <section className="feedback" aria-live="polite"><p>{message}</p><details><summary>Connection details and map source</summary><p>Boat API: {stale?'offline or stale':status?.state}. Position: {telemetryStale?'unavailable or stale':'live'}. Speed: {telemetry?.speed_m_s?.toFixed(2)??'—'} m/s. Heading: {telemetry?.heading_deg?.toFixed(1)??'—'}°.</p><p>{workspace.map?.schema_version===3?'GPS map · unverified':workspace.map?'Simulator map · alignment required':'No map loaded'}</p><code>{workspace.map?.scene_id||''}</code></details></section>
    </main>;
}
createRoot(document.getElementById('root')).render(<App/>);
