import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './style.css';
import './appShell.css';
import Planner,{WorkflowNav} from './Planner';
import {replaceGateObject} from './gateGeometry';
import {TASK_STYLE} from './RunBuilder';
import Feedback from './Feedback';
import {freshStatus,operationNotice} from './readiness';
import {defaultSettings,effectiveSettings,towerZones,routeIsVisible,settingsError} from './settings';
import BoatControls from './BoatControls';
import FlightMode from './FlightMode';
import ConnectionDetails from './ConnectionDetails';
import ConnectionsDialog from './Connections';
import {configuration,heading,friendly} from './workflow';
import {boundaryBands,local,gps,expandedFootprint,insetBoundary,crossingWindow} from './buffers';
import {api,newSession,setConnectionGeneration} from './api';
import {addedObject} from './MapReview';
import {courseOverlay} from './courseOverlay';
import {suggestBoundary,DEFAULT_BOUNDARY_PADDING_M} from './planningBoundary';

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
    const [originalOverlay,setOriginalOverlay]=useState(false),[candidateId,setCandidateId]=useState('');
    const [mapPreview,setMapPreview]=useState(false),[expandedMap,setExpandedMap]=useState(false),[sequenceHost,setSequenceHost]=useState(null),[focusedPassage,setFocusedPassage]=useState(null);
    const [step,setStep]=useState(1), [selected,setSelected]=useState('');
    const [mode,setMode]=useState('inspect'), [labels,setLabels]=useState(false), [stations,setStations]=useState(false), [overlays,setOverlays]=useState(true);
    const [buffers,setBuffers]=useState(false);
    const [boundaryPadding,setBoundaryPadding]=useState(DEFAULT_BOUNDARY_PADDING_M);
    const [activeTask,setActiveTask]=useState(null),[generatedTasks,setGeneratedTasks]=useState([]);
    const settingsChanged=useRef(false),serverSession=useRef(null);
    const mapChanged=useRef(false), pendingWork=useRef(0);
    const [workspace,setWorkspace]=useState({map:null,draft:null,approval:null});
    const [status,setStatus]=useState(null), [received,setReceived]=useState(0);
    const [connections,setConnections]=useState(null),[connectionsOpen,setConnectionsOpen]=useState(false);
    const connectionGeneration=useRef(null),connectionRevision=useRef(null);
    async function receiveConnections(value){
        if(connectionRevision.current!==null&&value.revision<connectionRevision.current)return;
        setConnections(old=>({...value,review_demo:value.review_demo??old?.review_demo}));connectionRevision.current=value.revision;
        if(connectionGeneration.current!==null&&connectionGeneration.current!==value.generation){
            setConnectionGeneration(value.generation);setStatus(null);setReceived(0);setOperations([]);setResults({});watchedOperations.current.clear();
            invalidateRoute();setActiveTask(null);setValidation(null);setDirty(false);setStep(1);setMode('inspect');setSelected('');setCandidateId('');setOriginalOverlay(false);settingsChanged.current=false;mapChanged.current=false;
            setWorkspace({map:null,approval:null});
            newSession().then(v=>setWorkspace(v.workspace)).catch(reportError);
            setMessage('Mission API target changed. Every tab must load a fresh map and review a new run. No vehicle command was sent.');
        }
        connectionGeneration.current=value.generation;
    }
    const [telemetry,setTelemetry]=useState(null), [telemetryReceived,setTelemetryReceived]=useState(0), [now,setNow]=useState(Date.now());
    const boatMarker=useRef();
    const [focusedFailure,setFocusedFailure]=useState(null);
    const [message,updateMessage]=useState('Load the full competition map, review object positions and types, then build a run.'), [validation,setValidation]=useState(null);
    const [notice,setNotice]=useState(null),[workLabel,setWorkLabel]=useState('Working…'),[startedAt,setStartedAt]=useState(0);
    function setMessage(text,kind='info',errors=[]){updateMessage(text);setNotice({text,detail:text,kind,errors});}
    function reportError(error){updateMessage(error.message);setNotice({kind:'error',text:error.message,detail:error.detail||error.message,errors:error.errors||[]});}
    const [dirty,setDirty]=useState(false), [busy,setBusy]=useState(false), [tiles,setTiles]=useState(false), [tileError,setTileError]=useState(false);
    const [operations,setOperations]=useState([]);
    const [results,setResults]=useState({});
    const watchedOperations=useRef(new Set());
    const mapRef=useRef(), layers=useRef(), tileRef=useRef(), vehicleLayer=useRef(), current=useRef(), [ready,setReady]=useState(false);
    const competition=true;
    const draft=((step!==4&&workspace.run_draft?.planning_mode==='return'?workspace.run_setup:workspace.run_draft))||blank();
    const routeVisible=generatedTasks.length>0&&draft.waypoints?.length>0;
    const selectedCard=draft.steps?.find(s=>s.id===activeTask);
    const previewSettings={...draft,...draft.settings};
    function invalidateRoute(){setGeneratedTasks([]);}
    function updateSettings(settings){
        settingsChanged.current=true;invalidateRoute();
        setWorkspace(w=>({...w,game_settings:settings,run_draft:{...draft,settings:{speed_m_s:settings.speed_m_s,clearance_m:settings.clearance_m,preferred_buffer_m:settings.preferred_buffer_m,tower_avoidance:settings.tower_avoidance},shared_crossings:[],waypoints:[],generation_identity:null},approval:null}));setDirty(true);setValidation(null);
    }
    async function saveSettings(){await run(async()=>{
        const error=settingsError(workspace.game_settings||defaultSettings(draft));if(error)throw new Error(error);
        settingsChanged.current=true;await save();setStep(3);setMode('inspect');
        setMessage('Shared settings applied. Add tasks and review their assignments before generating.');
    });}
    function changeWorkspace(w,mapEdit=false,isDirty=true){
        if(mapEdit){invalidateRoute();mapChanged.current=true;for(const config of Object.values(w.course||{})){config.sizes_confirmed=false;config.course_confirmed=false;}if(w.draft){w.draft.sizes_confirmed=false;w.draft.course_confirmed=false;}if(w.run_draft){w.run_draft.generation_identity=null;w.run_draft.waypoints=[];}}
        setWorkspace(w);setDirty(isDirty);setValidation(null);
    }
    current.current={workspace,draft,activeTask,edit,mode,changeWorkspace,setMode,setSelected,busy,selectObject,addObservation,changeBoundary};
    function changeBoundary(planning_area){
        const latest=current.current.draft;
        edit({...latest,planning_area,shared_crossings:[],waypoints:[],generation_identity:null});
    }
    function boundaryStart(){
        if(draft.attempt?.start_source==='manual')return draft.start;
        return !telemetryStale?telemetry?.position:null;
    }
    function regenerateBoundary(){
        try{
            const planning_area=suggestBoundary(workspace.map,boundaryPadding,boundaryStart());
            changeBoundary(planning_area);setMode('inspect');
            if(planning_area.length)mapRef.current.fitBounds(planning_area.map(latlng),{padding:[40,40],maxZoom:22});
            setMessage('Boundary regenerated around the map and known start. Check permitted water and review the updated outline.');
        }catch(error){reportError(error);}
    }
    async function addObservation(position){await run(async()=>{
        const currentMap=current.current.workspace;
        const object=addedObject(position,'observed_'+crypto.randomUUID().replaceAll('-',''));
        await save({...currentMap,map:{...currentMap.map,buoys:[...currentMap.map.buoys,object]}},true);
        invalidateRoute();setSelected(object.id);setMode('inspect');
        setMessage('Object added at the clicked GPS position. Set its color and type, then compile again.');
    });}
    function edit(next) {
        if(competition&&['start','planning_area','settings','steps','shared_crossings'].some(key=>next[key]!==draft[key]))invalidateRoute();
        setWorkspace(w=>{
            if(w.planning_mode==='run')return {...w,run_draft:next,approval:null};
            if(next.planner_task){
                const roles=configuration(next);const planner_task=next.planner_task;
                return {...w,draft:next,course:{...w.course,[planner_task]:roles},approval:null};
            }
            return {...w,draft:next,approval:null};
        }); setDirty(true); setValidation(null);
    }
    function selectObject(object){
        const {mode,draft,edit}=current.current;
        if(current.current.busy)return;
        if(mode.startsWith('replace:')){
            try {edit(replaceGateObject(draft,JSON.parse(mode.slice(8)),object));setMode('inspect');setSelected(object.id);setMessage('Gate pair updated. Review its geometry and confirm the task again.');}catch(error){reportError(error);}
            return;
        }
        setSelected(object.id);
        if(step===3)setMessage(`${friendly(object.id)} · ${draft.steps?.flatMap(s=>(s.setup.passages||[]).filter(p=>[p.red,p.green,p.buoy].includes(object.id)).map(p=>`${friendly(s.type)}: ${p.kind==='gate'?'gate pair':'turn'}`)).join(', ')||'not assigned to a passage'}`);
        else if(step===2&&object.object_type==='detector')setStep(2);
    }
    function focusPassage(id){
        setFocusedPassage(id);setMode('inspect');
        const passage=selectedCard?.setup.passages?.find(p=>p.id===id);
        const ids=[passage?.red,passage?.green,passage?.buoy];
        const points=[...(workspace.map?.buoys||[]),...(workspace.map?.obstacles||[])].filter(o=>ids.includes(o.id)).map(o=>latlng(o.centre));
        if(points.length)mapRef.current.fitBounds(points,{padding:[100,100],maxZoom:22});
    }
    useEffect(()=>{
        const map=L.map('course-map',{attributionControl:true,maxZoom:24}).setView([51.566151,-4.034345],20);
        mapRef.current=map; layers.current=L.layerGroup().addTo(map); vehicleLayer.current=L.layerGroup().addTo(map);
        map.on('click',e=>{const {draft,edit,workspace,activeTask,mode,changeWorkspace,setMode}=current.current;
            if(current.current.busy||mode==='inspect'||mode==='boundary-corners'||mode.startsWith('replace:'))return;
            if(mode==='add-object'){current.current.addObservation(point(e.latlng));return;}
            if(mode.startsWith('card:')){
                const key=mode.slice(5),card=draft.steps?.find(s=>s.id===activeTask);if(!card)return;
                const setup={...card.setup,course_confirmed:false,derived_sections:[]};
                if(key==='waypoint')setup.waypoints=[...(setup.waypoints||[]),point(e.latlng)];
                else setup[key]=key==='channel'?[...(setup[key]||[]),point(e.latlng)]:point(e.latlng);
                edit({...draft,steps:draft.steps.map(s=>s.id===activeTask?{...s,setup}:s),shared_crossings:[],waypoints:[],generation_identity:null});
                if(!['channel','waypoint'].includes(key))setMode('inspect');return;
            }

            if(mode==='waypoint'){edit({...draft,waypoints:[...draft.waypoints,point(e.latlng)],...(!draft.planner_task?{finish:point(e.latlng)}:{})});return;}
            if(mode==='planning_area'){current.current.changeBoundary([...(draft.planning_area||[]),point(e.latlng)]);return;}
            const next={...draft,[mode]:['planning_area','channel'].includes(mode)?[...(draft[mode]||[]),point(e.latlng)]:point(e.latlng),course_confirmed:false};
            if(mode==='start'){next.attempt={...draft.attempt,start_source:'manual',selection_confirmed:false};edit(next);setMode('inspect');return;}
            if(workspace.planning_mode==='run'){edit({...next,waypoints:[],generation_identity:null});if(!['planning_area','channel'].includes(mode))setMode('inspect');return;}
            const roles=configuration(next);const planner_task=next.planner_task;
            changeWorkspace({...workspace,draft:next,course:draft.planner_task?{...workspace.course,[draft.planner_task]:roles}:workspace.course,approval:null});
            if(!['planning_area','channel'].includes(mode))setMode('inspect');
        });
        setReady(true);
        newSession().then(value=>{serverSession.current=value.backend_id;setWorkspace(value.workspace);}).catch(reportError);
        return ()=>map.remove();
    },[]);
    // Keep one Leaflet instance and its viewport while the preview is collapsed.
    useEffect(()=>{
        if(!ready)return;
        const observer=new ResizeObserver(()=>mapRef.current.invalidateSize({pan:false}));
        observer.observe(document.getElementById('course-map'));
        return()=>observer.disconnect();
    },[ready]);
    useEffect(()=>{setMapPreview(false);document.querySelector('.workspace-layout aside')?.scrollTo({top:0});},[step]);
    useEffect(()=>{if(mode!=='inspect')setMapPreview(true);},[mode]);
    useEffect(()=>{
        let active=true;
        let timer, controller;
        async function poll(){controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),5500);try {const response=await fetch('/api/status',{signal:controller.signal});const value=await response.json();if(!response.ok)throw new Error(value.detail||'Boat API unavailable');if(active&&String(connectionGeneration.current??response.headers.get('X-Connection-Generation'))===response.headers.get('X-Connection-Generation')){setStatus(value);setReceived(Date.now());}}catch(error) {if(active)setStatus(s=>({...s,connection_lost:true,connection_error:error.message}));}finally{clearTimeout(timeout);if(active)timer=setTimeout(poll,1000);}}
        poll();return()=>{active=false;clearTimeout(timer);controller?.abort();};
    },[]);
    useEffect(()=>{
        const stream=new EventSource('/api/telemetry/events');
        stream.onmessage=event=>{const value=JSON.parse(event.data);
            if(serverSession.current&&value.gcs_session_id&&serverSession.current!==value.gcs_session_id){
                connectionGeneration.current=null;connectionRevision.current=null;setConnectionGeneration(value.connection_generation);setStatus(null);setReceived(0);
                setGeneratedTasks([]);setActiveTask(null);setValidation(null);setStep(1);setMode('inspect');
                setOperations([]);setResults({});newSession().then(v=>setWorkspace(v.workspace)).catch(reportError);
                setMessage('GCS restarted. Planning starts empty; live boat status and Hold / Stop remain available.');
            }
            serverSession.current=value.gcs_session_id||serverSession.current;
            if(value.connection_revision!==connectionRevision.current||value.connection_generation!==connectionGeneration.current){fetch('/api/connections').then(r=>r.json()).then(receiveConnections).catch(()=>{});}
            setTelemetry(value);setTelemetryReceived(Date.now());};
        stream.onerror=()=>setTelemetry(t=>t?{...t,stale:true,connection_state:'disconnected'}:null);
        const timer=setInterval(()=>setNow(Date.now()),250);
        return()=>{stream.close();clearInterval(timer);};
    },[]);
    const telemetryStale=!telemetry||telemetry.stale||now-telemetryReceived>1500;
    useEffect(()=>{
        const controller=new AbortController();
        const refresh=()=>fetch('/api/connections',{signal:controller.signal}).then(response=>{
            if(!response.ok)throw new Error('Connection settings unavailable');
            return response.json();
        }).then(receiveConnections).catch(()=>{if(!controller.signal.aborted)setConnections(null);});
        refresh();const timer=setInterval(refresh,1000);
        return()=>{controller.abort();clearInterval(timer);};
    },[telemetry?.gcs_session_id]);
    useEffect(()=>{
        let active=true;
        async function poll(){for(const id of operations){try {const value=await api('operations/'+encodeURIComponent(id));if(active){setResults(r=>({...r,[id]:value}));if(watchedOperations.current.has(id)&&value.command==='start'&&value.state==='succeeded')api('workspace').then(w=>setWorkspace(old=>old.revision===w.revision?{...old,return_target:w.return_target,run_consumed:w.run_consumed,execution:w.execution}:old)).catch(reportError);if(watchedOperations.current.has(id)){const update=operationNotice(value);if(update){watchedOperations.current.delete(id);updateMessage(update.text);setNotice(update);}}}}catch{}}}
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
        if(originalOverlay&&workspace.original_map)for(const obj of [...workspace.original_map.buoys,...(workspace.original_map.obstacles||[])]){
            L.circleMarker(latlng(obj.centre),{radius:10,color:'#b3bac6',weight:1.5,dashArray:'3 3',fillOpacity:0,interactive:false}).addTo(group).bindTooltip(document.createTextNode('Original: '+obj.id));
        }
        if(map) for(const [i,b] of map.buoys.entries()){
            const colour={red:'#e74b50',green:'#35c78b',white:'#dfe7f2',blue:'#4e9feb',orange:'#fa8b24',purple:'#b15ce5',yellow:'#eed831',cyan:'#25d9df',black:'#151515',zebra:'#ffffff'}[b.category]||'#999';
            (b.type==='point'?(b.object_type==='detector'?L.marker(latlng(b.centre),{icon:L.divIcon({className:'tower-point-marker',iconSize:[14,14],iconAnchor:[7,7]})}):L.circleMarker(latlng(b.centre),{radius:6,color:colour,fillOpacity:0.8})):L.circle(latlng(b.centre),{radius:b.radius_m,color:colour,fillOpacity:0.7})).addTo(group).on('click',e=>{L.DomEvent.stopPropagation(e);current.current.selectObject(b);}).bindTooltip(document.createTextNode(friendly(b.id)),{permanent:labels,direction:'top',className:'buoy-tooltip'});
            if(b.category==='zebra')L.marker(latlng(b.centre),{interactive:false,icon:L.divIcon({className:'zebra-marker',iconSize:[16,16],iconAnchor:[8,8]})}).addTo(group);

        }
        if(map)for(const obj of map.obstacles||[]){
            const style={color:obj.task==='launch'?'#20252b':obj.task==='recover'?'#edcc35':obj.task==='evade'?'#bd79e4':'#99724d',fillOpacity:0.65,weight:2};
            const shape=obj.type==='point'?(obj.object_type==='detector'?L.marker(latlng(obj.centre),{icon:L.divIcon({className:'tower-point-marker',iconSize:[14,14],iconAnchor:[7,7]})}):L.circleMarker(latlng(obj.centre),{...style,radius:6})):obj.type==='polygon'?L.polygon(obj.footprint.map(latlng),style):L.circle(latlng(obj.centre),{...style,radius:obj.radius_m});
            shape.addTo(group).on('click',e=>{L.DomEvent.stopPropagation(e);current.current.selectObject(obj);}).bindTooltip(document.createTextNode(friendly(obj.id)),{permanent:labels,direction:'top',className:'buoy-tooltip'});

        }
        if(map&&step===1&&overlays&&(workspace.compilation||Object.keys(workspace.course_assignments||{}).length)){
            const result=workspace.compilation;
            const proposal=result?.candidates.find(c=>c.id===candidateId)||result?.candidates[0];
            const tasks=proposal?.tasks||Object.fromEntries(Object.entries(workspace.course_assignments||{}).map(([task,value])=>[task,value.roles]));
            const geometry=courseOverlay(map,tasks);
            for(const line of geometry.lines){
                L.polyline(line.points,{color:TASK_STYLE[line.task].color,weight:line.kind==='gate'?4:3,dashArray:line.kind==='travel'?'5 4':undefined,interactive:false}).addTo(group);
                if(line.label){const a=line.points[0],b=line.points[1];L.tooltip({permanent:true,direction:'top'}).setLatLng([(a[0]+b[0])/2,(a[1]+b[1])/2]).setContent(document.createTextNode(line.label)).addTo(group);}
            }
            for(const label of geometry.labels)L.marker(label.position,{interactive:false,icon:icon(label.text,TASK_STYLE[label.task].color)}).addTo(group);
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
                    else L.circle(latlng(obj.centre),{...style,radius:(obj.radius_m??0)+radius}).addTo(group);
                }
                for(const key of ['planning_area','channel'])if(draft[key]?.length>=3){
                    for(const band of boundaryBands(draft[key],radius,ref))L.polygon(band,{...style,stroke:false,fillOpacity:.08}).addTo(group);
                    for(const vertex of draft[key])L.circle(latlng(vertex),{...style,radius,stroke:false,fillOpacity:.04}).addTo(group);
                    const inset=insetBoundary(draft[key],radius,ref);
                    if(inset?.length)L.polygon(inset,{...style,fillOpacity:0}).addTo(group);
                }
                if(activeTask&&step>=3&&(routeVisible||draft.attempt?.start_source==='manual')&&draft.start)L.circle(latlng(draft.start),{...style,radius}).addTo(group);
                if(activeTask&&step>=3&&draft.finish&&(!competition||draft.waypoints?.length))L.circle(latlng(draft.finish),{...style,radius:(draft.finish_radius_m||0)+radius}).addTo(group);
            }
        }
        if(map&&(buffers||step===2)&&previewSettings.tower_avoidance){
            for(const obj of [...map.buoys,...(map.obstacles||[])].filter(o=>o.object_type==='detector')){
                const {hard_m:hard,soft_m:soft}=towerZones(obj,previewSettings);
                if(!Number.isFinite(hard)||!Number.isFinite(soft)||hard<0||soft<hard)continue;
                const draw=(distance,style)=>obj.type==='polygon'?L.polygon(expandedFootprint(obj.footprint,distance,map.geographic_reference),style):L.circle(latlng(obj.centre),{...style,radius:(obj.radius_m??0)+distance});
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
            for(const key of ['planning_area','channel'])if(draft[key]?.length)L.polygon(draft[key].map(latlng),{color:key==='channel'?'#44ddb5':'#ffce70',fillOpacity:.03,interactive:false}).addTo(group);
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
        if(competition&&step>=3&&overlays&&map){
            for(const card of draft.steps||[]){
                const setup=card.setup,highlight=card.id===activeTask,taskColor=TASK_STYLE[card.type].color;
                if(setup.channel?.length)L.polygon(setup.channel.map(latlng),{color:highlight?taskColor:'#667c78',weight:highlight?4:1,fillOpacity:.03,interactive:false}).addTo(group);
                for(const [passageIndex,p] of (setup.passages||[]).entries()){
                    const points=[p.red,p.green,p.buoy].filter(Boolean).map(id=>[...map.buoys,...(map.obstacles||[])].find(o=>o.id===id)?.centre).filter(Boolean);
                    if(points.length===2){
                        const focus=highlight&&(!focusedPassage||focusedPassage===p.id);
                        L.polyline(points.map(latlng),{color:highlight?taskColor:'#777',weight:focus?6:2,opacity:highlight?1:.35,interactive:!mode.startsWith('replace:')}).addTo(group).on('click',e=>{L.DomEvent.stopPropagation(e);if(!current.current.busy){setActiveTask(card.id);setFocusedPassage(p.id);}});
                        if(highlight){
                            for(const id of [p.red,p.green]){const object=[...map.buoys,...(map.obstacles||[])].find(o=>o.id===id);if(object)L.circleMarker(latlng(object.centre),{radius:12,color:taskColor,weight:2,fillOpacity:0,interactive:false}).addTo(group).bindTooltip(document.createTextNode(friendly(id)),{permanent:true,direction:id===p.red?'left':'right',className:'gate-object-label'});}
                            const a=local(points[0],map.geographic_reference),b=local(points[1],map.geographic_reference),centre=[(a[0]+b[0])/2,(a[1]+b[1])/2];
                            const direction=p.direction_override||setup.derived_sections?.find(v=>v.id===p.id)?.direction||setup.direction;
                            L.tooltip({permanent:true,direction:'top',className:'gate-pair-label'}).setLatLng(gps(centre,map.geographic_reference)).setContent(document.createTextNode(`Gate ${passageIndex+1}${direction?' · crossing direction':' · direction needs review'}`)).addTo(group);
                            if(direction?.length===2&&direction.every(Number.isFinite)){const length=Math.hypot(...direction);if(length>0){const d=direction.map(v=>v/length),at=(forward,side=0)=>gps([centre[0]+forward*d[0]-side*d[1],centre[1]+forward*d[1]+side*d[0]],map.geographic_reference);L.polyline([at(-3),at(3),at(1.6,1),at(3),at(1.6,-1)],{color:taskColor,weight:4,interactive:false}).addTo(group);}}
                        }
                    }
                    else if(points.length===1&&highlight)L.marker(latlng(points[0]),{icon:icon(p.side==='left'?'L':'R',taskColor)}).addTo(group);
                }
                for(const [i,section] of (setup.derived_sections||[]).entries())if(highlight){
                    L.marker(latlng(section.centre),{icon:icon(i+1,taskColor)}).addTo(group);
                    if(section.direction){const [x,y]=local(section.centre,map.geographic_reference),d=section.direction;L.polyline([gps([x-2*d[0],y-2*d[1]],map.geographic_reference),gps([x+2*d[0],y+2*d[1]],map.geographic_reference)],{color:taskColor}).addTo(group).bindTooltip('Local travel →');}
                }
                if(card.type==='manual'&&setup.waypoints?.length){L.polyline(setup.waypoints.map(latlng),{color:highlight?taskColor:'#777',weight:highlight?4:1}).addTo(group);for(const [i,p] of setup.waypoints.entries())L.marker(latlng(p),{icon:icon(i+1,highlight?taskColor:'#666')}).addTo(group);}
                if(setup.finish)L.circle(latlng(setup.finish),{radius:setup.finish_radius_m||1,color:highlight?taskColor:'#777'}).addTo(group);
            }
        }
        if(map&&(overlays||step===1||mode==='boundary-corners'||mode==='planning_area')&&draft.planning_area?.length){
            L.polygon(draft.planning_area.map(latlng),{color:'#ffce70',fillOpacity:.04,interactive:false,dashArray:step===1&&!draft.sizes_confirmed?'7 5':undefined}).addTo(group);
            if(mode==='boundary-corners')for(const [i,p] of draft.planning_area.entries()){
                const marker=L.marker(latlng(p),{draggable:!busy,icon:icon(i+1,'#79612d')}).addTo(group).bindTooltip(`Boundary corner ${i+1} · drag to move`);
                marker.on('dragend',()=>{if(current.current.busy)return;const latest=current.current.draft;current.current.changeBoundary(latest.planning_area.map((v,n)=>n===i?point(marker.getLatLng()):v));});
            }
        }
        if(routeVisible&&draft.route_sections?.length)for(const section of draft.route_sections){const route=[draft.start,...draft.waypoints];if(route[section.leg+1])L.polyline([latlng(section.start||route[section.leg]),latlng(section.end||route[section.leg+1])],{color:['approach','connector'].includes(section.kind)?'#d9b470':'#6ea9ff',weight:5}).addTo(group).bindTooltip(['approach','connector'].includes(section.kind)?'Approach to first included passage':`Task route · ${section.task||draft.planner_task}`);}
        if(routeVisible&&draft.waypoints.length&&!draft.route_sections?.length)L.polyline([latlng(draft.start),...draft.waypoints.map(latlng)],{color:'#6ea9ff',weight:3}).addTo(group);
        for(const [i,p]of (routeVisible?draft.waypoints:[]).entries()){
            const marker=L.marker(latlng(p),{draggable:mode==='waypoint'&&!busy,icon:icon(i+1,'#487dce')}).addTo(group);
            marker.on('dragend',()=>{if(current.current.busy)return;const {draft,edit}=current.current;const moved=point(marker.getLatLng());edit({...draft,waypoints:draft.waypoints.map((v,n)=>n===i?moved:v),...(i===draft.waypoints.length-1?{finish:moved}:{})});});
            marker.bindTooltip('Waypoint '+(i+1)+(mode==='waypoint'?' · drag to move':' · enable Edit on map to move'));
        }
        if(draft.start&&(draft.attempt?.start_source==='manual'||(activeTask&&step>=3&&routeVisible)))L.marker(latlng(draft.start),{icon:icon('S','#596579')}).addTo(group).bindTooltip('Planning start');
        if(activeTask&&step>=3&&draft.finish&&(!competition||draft.waypoints?.length))L.circle(latlng(draft.finish),{radius:draft.finish_radius_m,color:'#ab91f2',fillOpacity:0.1}).addTo(group).bindTooltip('Finish',{permanent:true,direction:'top',className:'setup-tooltip'});

        if(workspace.return_target)L.circle(latlng(workspace.return_target),{radius:1,color:'#43e5d3',fillOpacity:.2}).addTo(group).bindTooltip('Frozen run start · return stopping area (1 m)',{permanent:true});

        for(const failure of [...(validation?.errors||[]),...(draft.generation_errors||[]),...(focusedFailure?[focusedFailure]:[])])if(failure.location&&map){const [x,y]=failure.location;const ref=map.geographic_reference;const lat=ref.latitude+y/111319.49079327357;const lon=ref.longitude+x/(111319.49079327357*Math.cos(lat*Math.PI/180));L.circleMarker([lat,lon],{radius:10,color:'#ff5d68',failureReason:failure.reason}).addTo(group).bindTooltip(failure.reason,{permanent:failure===focusedFailure,direction:'top',className:'failure-tooltip'});}
    },[workspace,validation,ready,labels,stations,overlays,buffers,mode,step,activeTask,routeVisible,selected,focusedFailure,busy,focusedPassage,originalOverlay,candidateId]);
    useEffect(()=>{
        if(!ready)return;
        if(!telemetry?.position){if(boatMarker.current){boatMarker.current.remove();boatMarker.current=null;}return;}
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
        const value=await api('workspace','PUT',{revision:next.revision,run_draft:step!==4&&next.run_draft?.planning_mode==='return'?draft:next.run_draft,...(settingsChanged.current?{game_settings:next.game_settings}:{}),...(mapEdit?{map:next.map}:{})});
        mapChanged.current=false;settingsChanged.current=false;setWorkspace(value);setDirty(false);return value;
    }
    async function action(name,body){beginWork({validate:'Validating route',approve:'Approving route',upload:'Requesting upload',start:'Requesting start',stop:'Requesting Hold / Stop',disarm:'Requesting Disarm',mode:'Changing flight mode'}[name]);try{
        if(['validate','approve'].includes(name)&&dirty)await save();
        if(['upload','start','mode'].includes(name)&&identityMismatch)throw new Error('Vehicle identity mismatch. Correct Connections before Upload, Start or flight mode changes. Stop remains available.');
        if(['upload','start'].includes(name)&&dirty)throw new Error('Save, validate and approve the edited route first.');
        const value=await api(name,'POST',body);
        if(['stop','start'].includes(name)||(name==='mode'&&['starting','executing','stopping'].includes(status?.state))){setWorkspace(w=>({...w,approval:null,run_consumed:true}));setValidation(null);}
        else if(name==='mode'&&status?.state==='uploaded'&&status?.mode!==status?.available_modes?.[body.mode]){setWorkspace(w=>({...w,approval:null}));setValidation(null);}
        if(name==='validate'){setValidation(value);if(!value.valid){setMessage(value.errors.map(e=>e.reason).join('; '),'error',value.errors);return;}}
        if(name==='approve'){setWorkspace(w=>({...w,approval:value}));setValidation(value.validation);}
        if(value.operation_id){
            setOperations(ids=>[...new Set([...ids,value.operation_id])]);
            setResults(r=>({...r,[value.operation_id]:value}));
            const update=operationNotice(value);
            if(update){
                if(name==='start'&&value.state==='succeeded')setWorkspace(await api('workspace'));
                updateMessage(update.text);setNotice(update);return;
            }
            watchedOperations.current.add(value.operation_id);
        }
        setMessage(value.operation_id?'Request received. Waiting for the boat to confirm the result; this is not execution confirmation.':name==='validate'?(value.valid?'Route validation passed.':`${value.errors.length} validation failures.`):'Route approved. Upload and Start remain separate.');
    }catch(e){reportError(e);}finally{endWork();}}
    async function importMap(event){const file=event.target.files[0];if(!file)return;await run(async()=>{
        const value=await api('import','POST',{revision:workspace.revision,content:await file.text(),format:file.name.endsWith('.csv')?'csv':'json'});
        await initializeMap(value);setMessage('Map imported. Review its objects before building a run.');
    });event.target.value='';}
    async function initializeMap(value){invalidateRoute();setActiveTask(null);settingsChanged.current=false;mapChanged.current=false;
        const planning_area=suggestBoundary(value.map,DEFAULT_BOUNDARY_PADDING_M,!telemetryStale?telemetry?.position:null);
        const next={...value,run_draft:{...value.run_draft,planning_area}};
        setWorkspace(next);setDirty(true);setBoundaryPadding(DEFAULT_BOUNDARY_PADDING_M);setValidation(null);setStep(1);setSelected('');setMode('inspect');setCandidateId('');setOriginalOverlay(false);
        mapRef.current.fitBounds([...mapBounds(value.map),...planning_area.map(latlng)],{padding:[40,40],maxZoom:22});
    }
    async function loadCompetition(){await run(async()=>{
        const objectMap=await api('examples/competition');
        const value=await api('import','POST',{revision:workspace.revision,content:JSON.stringify(objectMap)});
        await initializeMap(value);setMessage('Full competition map loaded: 23 buoys and 6 props. Review object positions and types, then build a run.');
    });}
    function fitMap(taskOnly=false){
        if(!workspace.map)return;
        const view=taskOnly?(selectedCard?.setup||draft):draft;
        const ids=new Set((view.passages||[]).flatMap(p=>[p.red,p.green,p.buoy]).filter(Boolean));
        const points=taskOnly?[...workspace.map.buoys.filter(o=>ids.has(o.id)).map(o=>latlng(o.centre)),...[view.entry,view.exit,view.finish].filter(Boolean).map(latlng),...(view.channel||[]).map(latlng)]:[...mapBounds(workspace.map),...(draft.planning_area||[]).map(latlng)];
        if(points.length)mapRef.current.fitBounds(points,{padding:[60,60],maxZoom:22});
    }
    useEffect(()=>{setFocusedPassage(null);setMode('inspect');if(ready&&step===3)requestAnimationFrame(()=>{mapRef.current.invalidateSize();fitMap(true);});},[activeTask,step,ready]);
    function focusFailure(failure){
        if(!failure?.location||!workspace.map)return;
        const centre=gps(failure.location,workspace.map.geographic_reference);
        mapRef.current.setView(centre,Math.max(mapRef.current.getZoom(),22));setBuffers(true);setFocusedFailure(failure);
    }
    async function load(path,...args){
        if(path==='course/compile')setWorkLabel('Compiling observed course');
        else if(path==='generate')setWorkLabel('Generating route');
        else if(path==='course/geometry')setWorkLabel('Checking task geometry');
        return api(path,...args);
    }
    const stale=!freshStatus(status,now-received);
    const identityMismatch=!stale&&!telemetryStale&&['system_id','component_id'].some(k=>status?.[k]!=null&&status[k]!==telemetry?.[k]);
    return <main>
      {connectionsOpen&&connections&&<ConnectionsDialog connections={{...connections,identity_mismatch:identityMismatch}} onClose={()=>setConnectionsOpen(false)} onUpdate={receiveConnections} load={api} status={status} vehicleStale={stale} telemetry={telemetry} telemetryStale={telemetryStale}/>}
      <header><div><span className="eyebrow">{connections?.review_demo||'MARITIME · MISSION PLANNER'}</span><h1>Run builder</h1></div><div className="header-actions"><FlightMode status={status} stale={stale} busy={busy||identityMismatch||operations.some(id=>['pending','running'].includes(results[id]?.state))} action={action} canStart={!identityMismatch&&!dirty&&!!workspace.approval&&status?.state==='uploaded'&&status?.mission_id===workspace.approval?.envelope?.approval_id}/><button onClick={()=>run(async()=>{const w=await api('reset','POST');setWorkspace(w);setOperations([]);setResults({});invalidateRoute();setActiveTask(null);setValidation(null);setDirty(false);setStep(1);settingsChanged.current=false;mapChanged.current=false;setMessage('New empty run. Uploaded boat missions are unchanged.');})}>New run</button><span className={'connection '+(stale?'offline':'')}>{identityMismatch?'Vehicle identity mismatch':stale?'Waiting for vehicle · planning available':'Boat live'}</span><button onClick={()=>setConnectionsOpen(true)} disabled={!connections}>Connections</button><button className="stop" onClick={()=>action('stop')}>Stop boat</button></div></header>
      <BoatControls returnTarget={workspace.return_target} onReturn={()=>run(async()=>{invalidateRoute();const r=await api('return/prepare','POST',dirty?{revision:workspace.revision,run_draft:workspace.run_draft,...(settingsChanged.current?{game_settings:workspace.game_settings}:{})}:undefined);settingsChanged.current=false;setWorkspace(r.workspace);setDirty(false);setValidation(null);if(!r.success){setMessage(r.diagnostics.join('; '),'error',r.errors);return;}setGeneratedTasks(['return']);setActiveTask('return');setStep(4);setMode('inspect');setMessage('Fresh return prepared. Validate and Approve, then select Loiter for armed replacement Upload/readback and Start, or disarm outside Auto.');})} status={status} stale={stale} action={action} operations={operations} results={results}/>
      <div className="workspace-navigation"><WorkflowNav {...{step,setStep,setMode,busy,workspace,routeVisible}}/>{step===2&&<button className={'preview-toggle '+(mapPreview?'active-tool':'quiet')} aria-pressed={mapPreview} onClick={()=>{setMapPreview(v=>!v);setMode('inspect');}}>{mapPreview?'Hide map preview':'Show map preview'}</button>}</div>
      <div id="builder-sequence-host" ref={setSequenceHost} hidden={step!==3}/>
      <div className={'workspace-layout view-'+step+(step===3?' with-preview persistent-map'+(expandedMap?' expanded-map':''):step===2?(mapPreview?' with-preview':' without-preview'):'')}>

        <section className="map-panel" aria-label="Course map">
          <div className="map-toolbar"><div><strong>{workspace.map?.name||'Course map'}</strong><small>{workspace.map?`${workspace.map.buoys.length} buoys · ${workspace.map.obstacles?.length||0} props`:'Load a map to begin'}</small></div><div className="button-row"><button className={(buffers||step===2)?'buffer-toggle active-tool':'buffer-toggle quiet'} aria-pressed={buffers||step===2} title={step===2?'Buffers stay visible while configuring distances.':'Toggle buffer preview'} onClick={()=>{if(step===2)setMessage('Buffer preview stays visible while configuring distances.');else setBuffers(!buffers);}}>Show buffers</button>{step===3&&<button className="quiet" aria-pressed={expandedMap} onClick={()=>setExpandedMap(v=>!v)}>{expandedMap?'Balanced workspace':'Expand map'}</button>}<button className="quiet" onClick={()=>fitMap()}>Full course</button><button className="quiet" disabled={!selectedCard} onClick={()=>fitMap(true)}>Selected task</button><details className="map-options"><summary>Map layers</summary>{[['Object labels',labels,setLabels],['Station annotations',stations,setStations],['Planning overlays',overlays,setOverlays],['Street background',tiles,setTiles]].map(([name,value,set])=><label key={name}><input type="checkbox" checked={value} onChange={e=>set(e.target.checked)}/>{name}</label>)}</details></div></div>
          {(buffers||step===2)&&<div className="buffer-legend"><strong>Buffer preview · required {previewSettings.clearance_m} m · preferred {previewSettings.preferred_buffer_m??previewSettings.clearance_m} m</strong><span>Amber: required clearance. Blue: preferred room. Purple: tower hard exclusion and fading soft avoidance. Tower distances follow each GPS point. Shared settings apply to every card. Preview updates before validation; Validate checks the route.</span>{['planning_area','channel'].some(key=>draft[key]?.length>=3&&insetBoundary(draft[key],previewSettings.clearance_m,workspace.map.geographic_reference)===null)&&<span>Boundary clearance bands follow every edge. Validate checks exact segment containment.</span>}{['planning_area','channel'].some(key=>draft[key]?.length>=3&&insetBoundary(draft[key],previewSettings.clearance_m,workspace.map.geographic_reference)?.length===0)&&<span>No room remains inside a boundary at this required buffer.</span>}</div>}
          <div id="course-map"/>
          {step===3&&selected&&<div className="selected-object-info"><strong>{friendly(selected)}</strong><span>{selectedCard?.setup.passages?.filter(p=>[p.red,p.green,p.buoy].includes(selected)).map(p=>p.kind==='gate'?`Gate ${selectedCard.setup.passages.indexOf(p)+1} · ${p.red===selected?'first':'second'} buoy`:'Turn buoy').join(' · ')||'Not assigned to the selected task'}</span></div>}
          <div className={'map-instruction '+(mode!=='inspect'?'drawing':'')}><span>{mode.startsWith('replace:')?'Choose a replacement buoy · click its point on the map.':mode==='boundary-corners'?'Drag numbered boundary corners to adjust the outline.':mode==='add-object'?'Add observation · click its GPS position, then set color and type.':mode==='inspect'?(step===2?'Configuration · click a purple tower to adjust its zones.':'Inspect mode · click an object for details.'):mode==='card:waypoint'?'Manual task · click to append exact waypoints.':mode==='waypoint'?'Route editing · click to add a waypoint, drag a numbered waypoint to move it.':['planning_area','channel','card:channel'].includes(mode)?`Drawing ${mode.includes('channel')?'channel':'planning area'} · click corners in order.`:`Choose ${mode} · click its new position on the map.`}</span>{mode!=='inspect'&&<button onClick={()=>setMode('inspect')}>Done / cancel tool</button>}</div>
          <div className="map-caption"><span>{routeVisible?'Blue: generated route · amber: approach · L/R: reviewed passing sides':'No route displayed · Build your run, then generate'}</span>{tileError&&<span>Street background unavailable; planning still works.</span>}</div>
        </section>
        <aside aria-label="Mission workflow"><Planner knownBoundaryStart={boundaryStart()} {...{boundaryPadding,setBoundaryPadding,onRegenerateBoundary:regenerateBoundary,onBoundaryChange:changeBoundary}} originalOverlay={originalOverlay} setOriginalOverlay={setOriginalOverlay} candidateId={candidateId} setCandidateId={setCandidateId} sequenceHost={sequenceHost} onPassageSelected={focusPassage} focusedPassage={focusedPassage} showMap={()=>{setMapPreview(true);fitMap(true);}} selectedCard={activeTask} workspace={workspace} draft={draft} edit={edit} changeWorkspace={changeWorkspace} mode={mode} setMode={setMode} save={save} notify={setMessage} load={load} onFocusFailure={focusFailure} workLabel={workLabel} step={step} setStep={setStep} selected={selected} setSelected={setSelected} routeVisible={routeVisible} taskSelected={!!activeTask} onTaskSelected={setActiveTask} onGenerated={task=>{if(task!=='run')setActiveTask(task);setGeneratedTasks(tasks=>[...new Set([...tasks,task])]);}} invalidateRoute={invalidateRoute} updateSettings={updateSettings} saveSettings={saveSettings} onImport={importMap} loadCompetition={loadCompetition} validation={validation} action={action} busy={busy} run={run} stale={stale} status={{...status,identity_mismatch:identityMismatch}} dirty={dirty} operations={operations} results={results}/></aside>
      </div>
      <Feedback notice={notice} busy={busy} label={workLabel} elapsed={Math.max(0,Math.floor((now-startedAt)/1000))} onDismiss={()=>{setNotice(null);setFocusedFailure(null);}} onReview={step=>{setStep(step);setMode('inspect');setNotice(null);if(step===4)requestAnimationFrame(()=>{const details=document.getElementById('command-results');if(details){details.open=true;details.scrollIntoView({block:'center'});}});}} onFocus={focusFailure}/>
      <section className="feedback" aria-live="polite"><p title={message}>{message}</p><details><summary>Connection details</summary><div className="connection-popover"><ConnectionDetails connections={{...connections,identity_mismatch:identityMismatch}} status={status} apiOnline={!!status&&!status.connection_lost&&now-received<=3500} vehicleStale={stale} telemetry={telemetry} telemetryStale={telemetryStale}/><p>{workspace.map?.schema_version===3?'GPS map · unverified':workspace.map?'Simulator map · alignment required':'No map loaded'}</p><code>{workspace.map?.scene_id||''}</code></div></details></section>
    </main>;
}
createRoot(document.getElementById('root')).render(<App/>);
