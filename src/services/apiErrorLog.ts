export interface ApiErrorEntry {
  id: number;
  timestamp: Date;
  method: string;
  path: string;
  statusCode: number | null;
  errorCode: string;
  message: string;
}

type Listener = () => void;

const MAX_ENTRIES = 50;
let nextId = 1;
let entries: ApiErrorEntry[] = [];
const listeners = new Set<Listener>();

function notify() {
  listeners.forEach((fn) => fn());
}

export function logApiError(opts: {
  method?: string;
  path: string;
  statusCode?: number | null;
  errorCode?: string;
  message: string;
}) {
  const entry: ApiErrorEntry = {
    id: nextId++,
    timestamp: new Date(),
    method: opts.method || 'GET',
    path: opts.path,
    statusCode: opts.statusCode ?? null,
    errorCode: opts.errorCode || 'unknown',
    message: opts.message,
  };
  entries = [entry, ...entries].slice(0, MAX_ENTRIES);
  notify();
}

export function getApiErrors(): ApiErrorEntry[] {
  return entries;
}

export function clearApiErrors() {
  entries = [];
  notify();
}

export function subscribeApiErrors(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
