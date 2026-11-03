export function defaultSettings(draft={}) {
    const hard=draft.clearance_m??1.8;
    return {version:1,speed_m_s:draft.speed_m_s??.5,clearance_m:hard,preferred_buffer_m:draft.preferred_buffer_m??hard,
        tower_avoidance:{hard_m:hard,soft_m:Math.max(10,hard),strength:10,overrides:{}},task_overrides:{}};
}
export function effectiveSettings(settings,task) {
    return {...settings,...settings.task_overrides?.[task]};
}
export function towerZones(obj,settings) {
    const policy=settings.tower_avoidance;
    return policy?.overrides?.[obj.id]||policy||{hard_m:settings.clearance_m,soft_m:settings.preferred_buffer_m??settings.clearance_m};
}
export function settingsError(settings) {
    for(const task of [null,'gate','slalom','channel']) {
        const value=effectiveSettings(settings,task);
        if(!Number.isFinite(value.speed_m_s)||value.speed_m_s<=0)return 'Speed must be greater than zero.';
        if(!Number.isFinite(value.clearance_m)||value.clearance_m<0||!Number.isFinite(value.preferred_buffer_m)||value.preferred_buffer_m<value.clearance_m)return 'Preferred obstacle room must be at least the required clearance.';
        const p=value.tower_avoidance;
        if(!p||!Number.isFinite(p.strength)||p.strength<0||p.strength>100)return 'Choose a tower avoidance strength from 0 to 100.';
        for(const z of [p,...Object.values(p.overrides||{})])if(!Number.isFinite(z.hard_m)||!Number.isFinite(z.soft_m)||z.hard_m<0||z.soft_m<z.hard_m)return 'Tower soft distance must be at least its nonnegative hard distance.';
    }
    return '';
}
// Persisted drafts are not permission to display a route on a new browser boot.
export function routeIsVisible(task,generated,activeTask) {
    return activeTask==='manual'||(activeTask===task&&generated.includes(task));
}
