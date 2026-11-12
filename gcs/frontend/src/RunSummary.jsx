import React from 'react';
import {friendly} from './workflow';

export default function RunSummary({draft, mission, status}) {
    const steps = draft.steps || [];
    const label = id => {
        const index = steps.findIndex(step => step.id === id);
        return index < 0 ? 'Unassigned task' : `Task ${index + 1}: ${friendly(steps[index].type)}`;
    };
    const currentBlock = draft.blocks?.find(block =>
        (status?.current_item ?? 0) > block.waypoint_start &&
        (status?.current_item ?? 0) <= block.waypoint_end);
    const currentMission = !!mission && status?.mission_id === mission;
    const estimated = currentMission
        ? (currentBlock ? label(currentBlock.instance_id) : 'Initial connector')
        : 'Not executing this draft';
    return <div className="callout">
        <p>{steps.map(step => label(step.id)).join(' → ')}</p>
        <p>{draft.route_length_m?.toFixed(1)} m · nominal {Math.ceil(draft.nominal_travel_s || 0)} s · suggested budget {draft.suggested_budget_s} s · budget {draft.execution_budget_s} s</p>
        {draft.blocks?.map(block => <p key={block.instance_id}>
            {block.instances.map(label).join(' + ')} · waypoints {block.waypoint_start + 1}–{block.waypoint_end} · {block.stopped_finish ? 'final stopped finish' : 'transit'}
        </p>)}
        <details><summary>Task and connector sections</summary>
            {draft.route_sections?.map((section, index) => <p key={index}>
                {section.kind === 'connector' ? `Connector to ${label(section.instance_id)}` : `${label(section.instance_id)} · ${friendly(section.kind)}`} · leg {section.leg + 1}
            </p>)}
        </details>
        <p>Estimated task: {estimated} · actual waypoint {currentMission ? (status?.current_item ?? 'unknown') : '—'} / {draft.waypoints.length}. {currentMission ? status?.detail : ''}</p>
        <details><summary>Task diagnostics · internal IDs</summary>
            {steps.map(step => <p key={step.id}>{label(step.id)} · {step.id}</p>)}
        </details>
    </div>;
}
