// Generates the RS256 and ES256 keypairs used by the API and by the k6 JWT
// forging library. Deterministic filenames; run once before first boot.
'use strict';
const { generateKeyPairSync } = require('crypto');
const fs = require('fs');
const path = require('path');

const dir = path.join(__dirname, '..', 'keys');
fs.mkdirSync(dir, { recursive: true });

function write(name, obj) {
  for (const [k, v] of Object.entries(obj)) {
    fs.writeFileSync(path.join(dir, `${name}-${k}.pem`), v);
  }
  console.log(`wrote ${name} keypair`);
}

// RSA (RS256)
const rsa = generateKeyPairSync('rsa', {
  modulusLength: 2048,
  publicKeyEncoding: { type: 'spki', format: 'pem' },
  privateKeyEncoding: { type: 'pkcs8', format: 'pem' },
});
write('rsa', { public: rsa.publicKey, private: rsa.privateKey });

// EC P-256 (ES256)
const ec = generateKeyPairSync('ec', {
  namedCurve: 'P-256',
  publicKeyEncoding: { type: 'spki', format: 'pem' },
  privateKeyEncoding: { type: 'pkcs8', format: 'pem' },
});
write('ec', { public: ec.publicKey, private: ec.privateKey });

// Shared HMAC secret (HS256 baseline / key-confusion attack material)
fs.writeFileSync(path.join(dir, 'hmac.key'), 'zta-testbed-shared-secret-do-not-use-in-prod');
console.log('wrote hmac secret');
