export async function streamNdjson(url, handleItem, { signal, onError = () => {} } = {}) {
    const response = await fetch(url, {
        headers: { accept: 'application/x-ndjson' },
        signal,
        cache: 'no-cache',
    });

    if (!response.ok || !response.body) {
        throw new Error(`Stream failed: ${response.status}`);
    }

    const responseBodyReader = response.body.getReader();
    const textDecoder = new TextDecoder();
    let buffer = '';

    while (true) {
        let chunk;
        try {
            chunk = await responseBodyReader.read();
        } catch (error) {
            if (signal?.aborted) return;
            onError(error);
            break;
        }
        const { value, done } = chunk;
        if (done) break;

        buffer += textDecoder.decode(value, { stream: true });

        let newlineIndex;
        while ((newlineIndex = buffer.indexOf('\n')) >= 0) {
            const line = buffer.slice(0, newlineIndex).trim();
            buffer = buffer.slice(newlineIndex + 1);
            if (!line) continue;
            try {
                handleItem(JSON.parse(line));
            } catch (error) {
                onError(error);
            }
        }
    }

    const trailing = buffer.trim();
    if (trailing) {
        try {
            handleItem(JSON.parse(trailing));
        } catch (error) {
            onError(error);
        }
    }
}

export const shortenHex = (hexString, left = 10, right = 8) => {
    if (!hexString) return '';
    return hexString.length <= left + right + 1 ? hexString : `${hexString.slice(0, left)}…${hexString.slice(-right)}`;
};

/** Programmatic in-app navigation (plain <a href> links are handled by the Router). */
export function navigateTo(url) {
    history.pushState({}, '', url);
    window.dispatchEvent(new PopStateEvent('popstate'));
}
