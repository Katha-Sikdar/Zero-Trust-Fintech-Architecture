// Central runtime configuration. One image, seven scenarios: behaviour is
// entirely env-driven so the same container serves S0..S6 unchanged.
'use strict';

function bool(v, d = false) {
  if (v === undefined) return d;
  return String(v).toLowerCase() === 'true' || v === '1';
}

const config = {
  port: parseInt(process.env.PORT || '8080', 10),

  // JWT authentication enforcement point:
  //   none      -> no token check (S0/S1/S2 baseline transport-only)
  //   app       -> this process verifies the JWT   (S3 application-layer)
  //   delegated -> Envoy/Istio already verified it; trust forwarded claims (S4+)
  jwtMode: process.env.JWT_MODE || 'none',
  jwtAlg: process.env.JWT_ALG || 'RS256',            // RS256 | ES256 | HS256

  // Authorization (object/function level) enforcement point:
  //   none      -> no authz          (baseline)
  //   app       -> in-process middleware
  //   delegated -> Envoy ext_authz -> OPA already decided; trust the gateway
  authMode: process.env.AUTH_MODE || 'none',

  // Offload JWT verification to a worker_threads pool instead of blocking the
  // event loop. Isolates the "internal jitter" hypothesis (RQ1) from sidecar
  // offloading.
  offloadCrypto: bool(process.env.OFFLOAD_CRYPTO, false),
  workerPoolSize: parseInt(process.env.WORKER_POOL_SIZE || '4', 10),

  // Header the trusted proxy injects with the verified JWT payload (base64url
  // JSON). Envoy's jwt_authn writes this; in delegated mode we read it.
  jwtPayloadHeader: (process.env.JWT_PAYLOAD_HEADER || 'x-jwt-payload').toLowerCase(),

  // Simulated per-request business work (ms of CPU) so latency is not purely
  // crypto. Keeps the service loop realistic.
  businessCpuMs: parseInt(process.env.BUSINESS_CPU_MS || '2', 10),

  scenario: process.env.SCENARIO || 'unknown',
  seed: parseInt(process.env.SEED || '42', 10),
};

module.exports = config;
