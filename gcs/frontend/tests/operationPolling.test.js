import test from 'node:test';
import assert from 'node:assert/strict';
import {pollOperations} from '../src/operationPolling.js';
const flush = () => new Promise(resolve => setImmediate(resolve));
function clock() {
    const jobs = new Map(); let next = 0;
    return {schedule(fn, delay) {const id = ++next; jobs.set(id, {fn, delay}); return id;},
        cancel(id) {jobs.delete(id);},
        run(delay) {const entry = [...jobs].find(([, job]) => job.delay === delay); assert.ok(entry); jobs.delete(entry[0]); entry[1].fn();}, jobs};
}
test('completed commands are retained without reads; pending commands stop after completion', async () => {
    const timers = clock(), calls = [], results = {old: {state: 'succeeded'}}; let attempts = 0;
    const stop = pollOperations({ids: ['old', 'new'], getResult: id => results[id], ...timers,
        request: async id => {calls.push(id); return {state: ++attempts === 1 ? 'running' : 'succeeded'};},
        onResult: (id, value) => {results[id] = value;}});
    await flush(); assert.deepEqual(calls, ['new']);
    timers.run(1000); await flush(); assert.deepEqual(calls, ['new', 'new']);
    assert.equal(results.new.state, 'succeeded'); assert.equal(timers.jobs.size, 0); stop();
});
test('slow reads do not overlap and cleanup aborts and discards late results', async () => {
    const timers = clock(); let release, signal, calls = 0, updates = 0;
    const stop = pollOperations({ids: ['one', 'two'], getResult: () => null, ...timers,
        request: (_id, value) => {calls++; signal = value; return new Promise(resolve => {release = resolve;});}, onResult: () => updates++});
    await flush(); assert.equal(calls, 1);
    assert.ok([...timers.jobs.values()].every(job => job.delay !== 1000));
    stop(); assert.equal(signal.aborted, true); release({state: 'succeeded'}); await flush();
    assert.equal(calls, 1); assert.equal(updates, 0); assert.equal(timers.jobs.size, 0);
});
test('timed out reads retry and unknown outcomes stop polling', async () => {
    const timers = clock(), calls = [];
    const stop = pollOperations({ids: ['one'], getResult: () => null, ...timers,
        request: (id, signal) => {calls.push(id); return calls.length === 1 ? new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new Error('timeout')))) : Promise.resolve({state: 'unknown'});}, onResult: () => {}});
    timers.run(5500); await flush(); timers.run(1000); await flush();
    assert.deepEqual(calls, ['one', 'one']); assert.equal(timers.jobs.size, 0); stop();
});
