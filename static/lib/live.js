// static/lib/live.js
// One shared connection for every live feed on the page (health, blocks, transactions).
// Browsers open at most six HTTP/1.1 connections per host; a stream per feed held
// three of them for every open tab, so a second tab could stall all requests.
import { API } from './api.js';
import { streamNdjson } from './utils.js';

const subscribers = new Set(); // { topic, prefetch, onItem, onError }
let controller = null;
let reconnectQueued = false;

/**
 * Receive the items of one feed ('health', 'block' or 'transaction') until the returned
 * function is called. Blocks and transactions start with their newest `prefetch` items.
 * Subscribing or unsubscribing reconnects (once per tick), so subscribers may see items
 * they already have again and should de-duplicate.
 */
export function subscribe(topic, { prefetch = 0, onItem, onError = () => {} }) {
    const subscriber = { topic, prefetch, onItem, onError };
    subscribers.add(subscriber);
    queueReconnect();
    return () => {
        subscribers.delete(subscriber);
        queueReconnect();
    };
}

function queueReconnect() {
    if (reconnectQueued) return;
    reconnectQueued = true;
    queueMicrotask(() => {
        reconnectQueued = false;
        connect();
    });
}

function connect() {
    controller?.abort();
    controller = null;
    if (subscribers.size === 0) return;

    const prefetch = (topic) => {
        const counts = [...subscribers].filter((s) => s.topic === topic).map((s) => s.prefetch);
        return counts.length ? Math.max(...counts) : null;
    };
    const current = new AbortController();
    controller = current;
    const fail = (error) => {
        if (current.signal.aborted) return;
        for (const subscriber of subscribers) subscriber.onError(error);
    };

    streamNdjson(
        API.LIVE_STREAM({ blocks: prefetch('block'), transactions: prefetch('transaction') }),
        ({ topic, data }) => {
            for (const subscriber of subscribers) {
                if (subscriber.topic === topic) subscriber.onItem(data);
            }
        },
        { signal: current.signal, onError: fail },
    )
        .then(() => fail(new Error('Live stream ended')))
        .catch(fail);
}
