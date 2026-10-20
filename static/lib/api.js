const _baseHref = new URL(document.baseURI).pathname;
export const BASE_PATH = _baseHref.endsWith('/') ? _baseHref.slice(0, -1) : _baseHref;

const API_PREFIX = `${BASE_PATH}/api/v1`;

const joinUrl = (...parts) => parts.join('/').replace(/\/{2,}/g, '/');
const encodeHash = (hash) => encodeURIComponent(String(hash));
const query = (params) =>
    Object.entries(params)
        .map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
        .join('&');

// Feeds with a null prefetch are left out of the stream.
const LIVE_STREAM = (prefetch) =>
    `${joinUrl(API_PREFIX, 'stream')}?${query(Object.fromEntries(Object.entries(prefetch).filter(([, v]) => v != null)))}`;

const BLOCK_DETAIL_BY_HASH = (hash) => joinUrl(API_PREFIX, 'blocks', encodeHash(hash));
const BLOCKS_LIST = (page, pageSize) =>
    `${joinUrl(API_PREFIX, 'blocks/list')}?${query({ page, 'page-size': pageSize })}`;

const TRANSACTION_DETAIL_BY_HASH = (hash) => joinUrl(API_PREFIX, 'transactions', encodeHash(hash));
const TRANSACTIONS_LIST = (page, pageSize) =>
    `${joinUrl(API_PREFIX, 'transactions/list')}?${query({ page, 'page-size': pageSize })}`;

const CHANNELS_LIST = (limit, opsLimit) =>
    `${joinUrl(API_PREFIX, 'channels/list')}?${query({ limit, 'ops-limit': opsLimit })}`;
const CHANNEL_DETAIL_BY_ID = (channelId, page, pageSize) =>
    `${joinUrl(API_PREFIX, 'channels', encodeHash(channelId))}?${query({ page, 'page-size': pageSize })}`;

const NOTE_SEARCH = (noteId) => joinUrl(API_PREFIX, 'notes', encodeHash(noteId));
const KEY_SEARCH = (publicKey) => joinUrl(API_PREFIX, 'keys', encodeHash(publicKey));

export const API = {
    LIVE_STREAM,
    CHANNELS_LIST,
    CHANNEL_DETAIL_BY_ID,
    NOTE_SEARCH,
    KEY_SEARCH,
    TRANSACTION_DETAIL_BY_HASH,
    TRANSACTIONS_LIST,
    BLOCK_DETAIL_BY_HASH,
    BLOCKS_LIST,
};

const BLOCK_DETAIL = (hash) => joinUrl(`${BASE_PATH}/blocks`, encodeHash(hash));
const TRANSACTION_DETAIL = (hash) => joinUrl(`${BASE_PATH}/transactions`, encodeHash(hash));
const CHANNEL_DETAIL = (channelId) => joinUrl(`${BASE_PATH}/channel`, encodeHash(channelId));
const NOTE_DETAIL = (noteId) => joinUrl(`${BASE_PATH}/notes`, encodeHash(noteId));
const KEY_DETAIL = (publicKey) => joinUrl(`${BASE_PATH}/keys`, encodeHash(publicKey));

export const PAGE = {
    BLOCK_DETAIL,
    TRANSACTION_DETAIL,
    CHANNEL_DETAIL,
    NOTE_DETAIL,
    KEY_DETAIL,
};
