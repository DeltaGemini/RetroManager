// Uploading a file to RetroManager in 8 MB pieces (/api/uploads, backend/routes/importing.py):
// one dropped is tried again, and an upload that's cut off (or the page reloaded) carries on
// from where the server got to. For the Add games page and a game's Replace with an updated ROM.
//
//   const id = await RMUpload.send(file, {
//       key,              // the same key gets the same upload back, to carry on (default: name, size and date)
//       onStart(id, received),     // the upload's id (to discard it), and what had already arrived
//       onProgress(received, size, bytesPerSecond?),
//       onRetry(seconds, error),   // waiting to try again
//       stopped(),        // true to stop (the upload is kept, to carry on later)
//       giveUpAfter,      // failures in a row before giving up (default: never)
//   });
// Resolves to the upload's id once it's all there (null if stopped); throws if it can't start or gives up.
(function () {
    const CHUNK = 8 * 1024 * 1024;
    const base = window.location.origin;
    const sleep = (ms) => new Promise(r => setTimeout(r, ms));
    const json = (res) => res.json().catch(() => ({ success: false, error: `HTTP ${res.status}` }));

    async function send(file, options = {}) {
        const { onStart, onProgress, onRetry, stopped, giveUpAfter = Infinity } = options;
        const key = options.key || `${file.name}|${file.size}|${file.lastModified}`;
        const start = await json(await fetch(`${base}/api/uploads`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: file.name, size: file.size, key }) }));
        if (!start.success) throw new Error(start.error || "The upload couldn't start");
        let received = start.received, failures = 0;
        let lastTime = performance.now(), lastBytes = received;
        onStart && onStart(start.id, received);
        onProgress && onProgress(received, file.size);
        while (received < file.size) {
            if (stopped && stopped()) return null;
            try {
                const res = await fetch(`${base}/api/uploads/${start.id}?offset=${received}`, {
                    method: 'PUT', body: file.slice(received, Math.min(received + CHUNK, file.size)), headers: { 'Content-Type': 'application/octet-stream' } });
                const data = await json(res);
                // (409: the server has a different amount than this side thought; it says how much)
                if (!data.success && res.status !== 409) throw new Error(data.error || `HTTP ${res.status}`);
                received = data.received;
                failures = 0;
                const now = performance.now();
                const speed = now - lastTime > 1000 ? (received - lastBytes) / ((now - lastTime) / 1000) : undefined;
                if (speed !== undefined) { lastTime = now; lastBytes = received; }
                onProgress && onProgress(received, file.size, speed);
            } catch (err) {
                // Wait, then carry on from where the server says it got to
                if (++failures > giveUpAfter) throw err;
                const wait = Math.min(30, 2 ** Math.min(failures, 5));
                onRetry && onRetry(wait, err);
                await sleep(wait * 1000);
                const status = await fetch(`${base}/api/uploads/${start.id}`).then(json).catch(() => null);
                if (status && status.success) received = status.received;
            }
        }
        return start.id;
    }

    window.RMUpload = { send };
})();
