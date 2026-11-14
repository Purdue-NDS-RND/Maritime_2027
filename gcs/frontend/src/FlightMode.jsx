import React,{useEffect,useState} from 'react';

export default function FlightMode({status,stale,busy,action,canStart=false}) {
    const modes=status?.available_modes||{};
    const current=Object.keys(modes).find(name=>modes[name]===status?.mode)||'';
    const [selected,setSelected]=useState(current);
    useEffect(()=>setSelected(current),[current]);
    const unavailable=stale||busy||!Object.keys(modes).length;
    return <div className="flight-mode-control">
        <label htmlFor="flight-mode">Flight mode <span>{stale?'Unknown':current||`Mode ${status?.mode??'unknown'}`}</span></label>
        <select id="flight-mode" value={selected} disabled={unavailable} onChange={event=>setSelected(event.target.value)}>
            {!selected&&<option value="">Select mode</option>}
            {Object.keys(modes).filter(name=>name!=='INITIALISING').map(name=><option key={name} value={name} disabled={name==='AUTO'&&!canStart}>{name}{name==='LOITER'?' · position hold':name==='AUTO'?' · start approved mission':''}</option>)}
        </select>
        <button disabled={unavailable||!selected||(selected==='AUTO'&&!canStart)} onClick={()=>selected==='AUTO'?action('start'):action('mode',{mode:selected})}>Set mode</button>
    </div>;
}
