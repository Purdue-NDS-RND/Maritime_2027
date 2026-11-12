import assert from 'node:assert/strict';
import {defaultSettings,effectiveSettings,towerZones,settingsError,routeIsVisible} from '../src/settings.js';
const settings=defaultSettings({speed_m_s:2,clearance_m:2});
assert.equal(settings.speed_m_s,2);assert.equal(settings.clearance_m,2);
settings.task_overrides.channel={speed_m_s:.6};
assert.equal(effectiveSettings(settings,'channel').speed_m_s,.6);
assert.equal(effectiveSettings(settings,'gate').speed_m_s,2);
settings.tower_avoidance.overrides.tower={hard_m:3,soft_m:14};
assert.deepEqual(towerZones({id:'tower'},settings),{hard_m:3,soft_m:14});
assert.equal(towerZones({id:'other'},settings).hard_m,2);
assert.equal(settingsError(settings),'');
settings.tower_avoidance.overrides.tower.soft_m=1;
assert.match(settingsError(settings),/Tower soft/);
for(const task of ['gate','slalom','channel']){
 assert.equal(routeIsVisible(task,[],null),false);
 assert.equal(routeIsVisible(task,[],task),false);
 assert.equal(routeIsVisible(task,[task],task),true);
 assert.equal(routeIsVisible(task,[task],'other'),false);
 // Reload resets session authorization even with persisted waypoints.
 assert.equal(routeIsVisible(task,[],null),false);
}
