# Keys are generated, not committed
Run `make keys` (or `node app/src/genkeys.js`) to create rsa/ec/hmac keypairs
here, then `node scripts/gen-jwks.js` for envoy/jwks.json. `make tokens` does both.
