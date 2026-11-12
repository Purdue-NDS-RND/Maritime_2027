import {useEffect, useRef} from 'react';
import {api} from './api';
import {pollOperations} from './operationPolling';

export function useOperationPolling(operations, results, onResult) {
    const latest = useRef();
    latest.current = {results, onResult};
    useEffect(() => pollOperations({
        ids: operations,
        getResult: id => latest.current.results[id],
        request: (id, signal) => api('operations/' + encodeURIComponent(id), 'GET', undefined, {signal}),
        onResult: (id, value) => latest.current.onResult(id, value),
    }), [operations]);
}
