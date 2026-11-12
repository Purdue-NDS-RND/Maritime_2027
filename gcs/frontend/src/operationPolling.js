const terminalStates = new Set(['succeeded', 'failed', 'unknown', 'cancelled']);

// One request at a time; retain completed results without requesting them again.
export function pollOperations({ids, getResult, request, onResult, schedule = setTimeout, cancel = clearTimeout, intervalMs = 1000, timeoutMs = 5500}) {
    let active = true, timer, controller;
    const completed = new Set(ids.filter(id => terminalStates.has(getResult(id)?.state)));
    async function poll() {
        for (const id of ids) {
            if (!active) return;
            if (completed.has(id)) continue;
            controller = new AbortController();
            const timeout = schedule(() => controller.abort(), timeoutMs);
            try {
                const value = await request(id, controller.signal);
                if (!active) return;
                if (terminalStates.has(value.state)) completed.add(id);
                onResult(id, value);
            } catch {
                // A read failure is retried; it never resends a vehicle command.
            } finally {
                cancel(timeout);
            }
        }
        if (active && completed.size < ids.length) timer = schedule(poll, intervalMs);
    }
    poll();
    return () => {
        active = false;
        cancel(timer);
        controller?.abort();
    };
}
