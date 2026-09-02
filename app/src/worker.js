// Worker thread: performs the CPU-bound JWT verification off the main event
// loop. Enabled by OFFLOAD_CRYPTO=true (RQ1 internal-threading arm).
'use strict';
const { parentPort } = require('worker_threads');
const jwt = require('jsonwebtoken');

parentPort.on('message', ({ id, token, key, algs }) => {
  try {
    const payload = jwt.verify(token, key, { algorithms: algs });
    parentPort.postMessage({ id, ok: true, payload });
  } catch (e) {
    parentPort.postMessage({ id, ok: false, error: e.message });
  }
});
