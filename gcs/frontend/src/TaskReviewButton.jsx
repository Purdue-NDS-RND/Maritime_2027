import React from 'react';

export default function TaskReviewButton({reviewed,disabled,onChange,children}) {
    return <button type="button" className="task-review-button" aria-pressed={reviewed} disabled={disabled} onClick={()=>onChange(!reviewed)}>
        <span className="task-review-icon" aria-hidden="true">{reviewed?'✓':'○'}</span>
        <span><strong>{reviewed?'Task reviewed':'Mark task as reviewed'}</strong><small>{children}{reviewed?' · Click again to undo':''}</small></span>
    </button>;
}
