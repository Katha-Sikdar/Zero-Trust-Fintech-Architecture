"""Shared constants for the analysis pipeline."""
RISKS = ["API1", "API2", "API4", "API5", "API8", "A10"]
LEVELS = [0.5, 0.9, 1.0, 1.2, 1.5]         # of lambda*
CELLS = ["tp", "fp", "tn", "fn"]

# Core scenarios reported in the paper (S6fo/S3off/S4es are experiment arms).
SCENARIOS = ["S0", "S1", "S2", "S3", "S4", "S5", "S6"]
SCENARIO_LABELS = {
    "S0": "Baseline", "S1": "Edge TLS", "S2": "Full mTLS",
    "S3": "App-layer JWT", "S4": "Sidecar JWT", "S5": "Sidecar+OPA",
    "S6": "S6 adaptive RL", "S6fo": "S6 fail-open", "S3off": "App JWT+worker",
    "S4es": "Sidecar JWT ES256", "S0rl": "Baseline + rate limit",
    "S6oc": "S6 fail-closed, OPA outage", "S6fooc": "S6 fail-open, OPA outage",
}
NOMINAL_LAMBDA = 220        # fallback global elbow if elbow.py has not run
