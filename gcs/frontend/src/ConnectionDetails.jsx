import React from 'react';

export default function ConnectionDetails({connections,status,apiOnline,vehicleStale,telemetry,telemetryStale}){
    const radio=connections?.telemetry;
    return <>
        <h3>Mission commands · Wi-Fi / Ethernet</h3>
        <p><strong>{apiOnline?'Boat API reachable':'Boat API unavailable'}</strong><br/><code>{connections?.boat_url||'Connection settings unavailable'}</code></p>
        <p>Vehicle status: {vehicleStale?'unavailable or stale':status?.state}. Upload, Start, Stop, Disarm and mission results use this connection.</p>
        <h3>Map telemetry · MAVLink</h3>
        <p><strong>{telemetryStale?'Telemetry unavailable or stale':'Telemetry live'}</strong><br/><code>{radio?.connection||'Connection settings unavailable'}</code></p>
        {radio&&<p>{radio.connection.startsWith('/dev/')?`Serial host baud: ${radio.baud}. `:''}Vehicle IDs: {radio.system_id} / {radio.component_id}.</p>}
        <p>Speed: {telemetry?.speed_m_s?.toFixed(2)??'—'} m/s. Heading: {telemetry?.heading_deg?.toFixed(1)??'—'}°. GPS fix: {telemetry?.gps_fix??'—'}.</p>
        {telemetry?.error&&<p className="callout error">{telemetry.error}</p>}
        <p>Telemetry only; this reader sends no commands. A live map does not confirm the mission connection.</p>
        <p className="hint">Change startup settings in the selected environment file, then recreate the affected container. Connection changes require a new run review.</p>
    </>;
}
