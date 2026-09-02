// Minimal fixed-size worker pool for JWT verification.
'use strict';
const { Worker } = require('worker_threads');
const path = require('path');

class Pool {
  constructor(size) {
    this.workers = [];
    this.queue = [];
    this.pending = new Map();
    this.rr = 0;
    this.seq = 0;
    for (let i = 0; i < size; i++) {
      const w = new Worker(path.join(__dirname, 'worker.js'));
      w.on('message', (msg) => {
        const cb = this.pending.get(msg.id);
        if (cb) { this.pending.delete(msg.id); cb(msg); }
      });
      w.on('error', () => {});
      this.workers.push(w);
    }
  }
  verify(token, key, algs) {
    return new Promise((resolve) => {
      const id = ++this.seq;
      this.pending.set(id, resolve);
      const w = this.workers[this.rr++ % this.workers.length];
      w.postMessage({ id, token, key, algs });
    });
  }
}
module.exports = Pool;
