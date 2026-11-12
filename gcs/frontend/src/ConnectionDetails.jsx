import React from 'react';

export default function ConnectionDetails({connections,status,apiOnline,vehicleStale,telemetry,telemetryStale}){
    const radio=connections?.telemetry;
    return <>
        {connections?.error&&<p className="callout error">{connections.error}</p>}
        {connections?.identity_mismatch&&<p className="callout error">Vehicle identity mismatch · Upload and Start blocked</p>}
        <h3>Mission commands · Wi-Fi / Ethernet</h3>
        <p><strong>{apiOnline?'Boat API reachable':'Boat API unavailable'}</strong><br/><code>{connections?.boat_url||'Connection settings unavailable'}</code></p>
        <p>Vehicle status: {vehicleStale?'unavailable or stale':status?.state}. Upload, Start, Stop, Disarm and mission results use this connection.</p>
        <h3>Map telemetry · MAVLink</h3>
        <p><strong>{telemetryStale?'Telemetry unavailable or stale':'Telemetry live'}</strong><br/><code>{radio?.connection||'Connection settings unavailable'}</code></p>
        {radio&&<p>{radio.connection.startsWith('/dev/')?`Serial host baud: ${radio.baud}. `:''}Vehicle IDs: {radio.system_id} / {radio.component_id}.</p>}
        <p>Speed: {telemetry?.speed_m_s?.toFixed(2)??'—'} m/s. Heading: {telemetry?.heading_deg?.toFixed(1)??'—'}°. GPS fix: {telemetry?.gps_fix??'—'}.</p>
        {telemetry?.error&&<p className="callout error">{telemetry.error}</p>}
        <p>Telemetry only; this reader sends no commands. A live map does not confirm the mission connection.</p>
        <p className="hint">Open Connections beside the vehicle indicator to edit profiles, test the API or reconnect. Mission target changes require a fresh map/run review.</p>
    </>;
}
