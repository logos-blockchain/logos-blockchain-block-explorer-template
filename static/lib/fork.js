import { API } from './api.js';

const POLL_INTERVAL_MS = 3000;

let subscribers = new Set();
let currentFork = null;
let pollTimer = null;

async function poll() {
    try {
        const res = await fetch(API.FORK_CHOICE, { cache: 'no-cache' });
        if (!res.ok) return;
        const data = await res.json();
        const newFork = data.fork;
        if (newFork !== currentFork) {
            currentFork = newFork;
            for (const cb of subscribers) cb(currentFork);
        }
    } catch {
        // ignore transient errors
    }
}

function startPolling() {
    if (pollTimer != null) return;
    poll(); // immediate first poll
    pollTimer = setInterval(poll, POLL_INTERVAL_MS);
}

function stopPolling() {
    if (pollTimer == null) return;
    clearInterval(pollTimer);
    pollTimer = null;
}

/**
 * Subscribe to fork-choice changes.
 * The callback is invoked immediately if a fork is already known,
 * and again whenever the fork changes.
 * Returns an unsubscribe function.
 */
export function subscribeFork(callback) {
    subscribers.add(callback);
    if (subscribers.size === 1) startPolling();
    if (currentFork != null) callback(currentFork);
    return () => {
        subscribers.delete(callback);
        if (subscribers.size === 0) stopPolling();
    };
}
