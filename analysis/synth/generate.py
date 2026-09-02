"""
Synthetic result generator.

Produces result files in the EXACT schema loadgen/main.js emits, so the whole
analysis pipeline can be exercised before any container is running. The
generated numbers encode the study's HYPOTHESES (they are not measurements):

  * app-layer JWT (S3) costs more p99 than sidecar JWT (S4); ES256 < RS256
  * JWT offloading alone (S4) does NOT cover authorization: BOLA/BFLA/A10 pass
  * OPA (S5) restores authorization coverage; S6 adds rate-limit coverage (API4)
  * past lambda*, the fail-OPEN mesh (S6fo) drops enforcement (RQ5); the
    fail-CLOSED mesh (S6) holds coverage but sheds benign traffic (FPR rises)

Everything is clearly stamped "synthetic": true so no run is mistaken for real.
Reproducible via --seed.
"""
import argparse, json, os, sys, math, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import RISKS, LEVELS

# per-scenario: added p99 ms over baseline, service capacity (lambda*), and the
# nominal block rate per risk at low load.
SCEN = {
    #            add_p99  cap   API1 API2 API4 API5 API8 A10
    "S0":  dict(add=0.0,  cap=460, cov=dict(API1=0.00, API2=0.00, API4=0.00, API5=0.00, API8=0.00, A10=0.00)),
    "S1":  dict(add=1.4,  cap=450, cov=dict(API1=0.00, API2=0.00, API4=0.00, API5=0.00, API8=0.02, A10=0.00)),
    "S2":  dict(add=3.1,  cap=420, cov=dict(API1=0.00, API2=0.00, API4=0.00, API5=0.00, API8=0.05, A10=0.00)),
    "S3":  dict(add=9.6,  cap=210, cov=dict(API1=0.99, API2=0.99, API4=0.30, API5=0.99, API8=0.99, A10=0.99)),
    "S4":  dict(add=4.2,  cap=300, cov=dict(API1=0.00, API2=0.99, API4=0.30, API5=0.00, API8=0.99, A10=0.00)),
    "S4es":dict(add=2.6,  cap=330, cov=dict(API1=0.00, API2=0.99, API4=0.30, API5=0.00, API8=0.99, A10=0.00)),
    "S3off":dict(add=6.8, cap=250, cov=dict(API1=0.99, API2=0.99, API4=0.30, API5=0.99, API8=0.99, A10=0.99)),
    "S5":  dict(add=5.6,  cap=280, cov=dict(API1=0.99, API2=0.99, API4=0.35, API5=0.99, API8=0.99, A10=0.99)),
    "S6":  dict(add=6.4,  cap=270, cov=dict(API1=0.99, API2=0.99, API4=0.92, API5=0.99, API8=0.99, A10=0.99)),
    "S6fo":dict(add=6.2,  cap=270, cov=dict(API1=0.99, API2=0.99, API4=0.92, API5=0.99, API8=0.99, A10=0.99)),
}
BASE_P50 = 2.8
ATTACK_FRACTION = 0.4
DURATION = "60s"


def latency(scn, rps, rng):
    """Non-linear latency vs load: gentle below capacity, blow-up past it."""
    cap = SCEN[scn]["cap"]
    rho = rps / cap
    base = BASE_P50 + SCEN[scn]["add"] * 0.35
    # p50 stays flat until the knee; p99 shows queueing growth that rises
    # sharply past rho~1 but remains in a believable ms range (bounded blow-up).
    knee = max(0.0, rho - 0.85)
    growth = 1.0 + 6.0 * knee ** 2 + 22.0 * knee ** 3       # ~1x below knee, ~10-15x at 1.5x
    p50 = base * (1 + 0.12 * rho) + rng.gauss(0, 0.05)
    p99 = (base + SCEN[scn]["add"]) * growth + rng.gauss(0, base * 0.06)
    p95 = 0.45 * p50 + 0.55 * p99
    return max(0.5, p50), max(0.6, p95), max(0.7, p99)


def block_rate(scn, risk, rps, rng):
    cov = SCEN[scn]["cov"][risk]
    cap = SCEN[scn]["cap"]
    rho = rps / cap
    # API4 coverage rises with load where a rate limit exists (more to shed)
    if risk == "API4" and cov > 0.5:
        cov = min(0.995, cov + 0.05 * max(0, rho - 0.8))
    # RQ5: fail-open mesh loses authz enforcement past lambda* (rho>1)
    if scn == "S6fo" and risk in ("API1", "API5", "A10") and rho > 1.0:
        drop = min(0.9, 2.2 * (rho - 1.0))
        cov = max(0.03, cov - drop)
    # fail-closed mesh under overload: tiny enforcement noise only
    cov = min(0.999, max(0.0, cov + rng.gauss(0, 0.01)))
    return cov


def fpr(scn, rps, rng):
    """Benign traffic wrongly blocked. Rises past capacity for rate-limited
    scenarios (fail-closed sheds real traffic — the cost of holding the line)."""
    cap = SCEN[scn]["cap"]; rho = rps / cap
    base = 0.002
    if scn in ("S3", "S5", "S6", "S6fo") and rho > 1.0:
        base += (0.25 if scn in ("S6", "S6fo") else 0.08) * (rho - 1.0)
    return min(0.6, max(0.0, base + rng.gauss(0, 0.003)))


def make_summary(scn, rps, alg, trial, rng):
    matrix = {}
    # per-risk request volumes over a 60s run at `rps`
    total = rps * 60
    attack_total = int(total * ATTACK_FRACTION)
    benign_total = total - attack_total
    per_risk_attacks = max(1, attack_total // len(RISKS))
    per_risk_benign = max(1, benign_total // len(RISKS))
    for r in RISKS:
        br = block_rate(scn, r, rps, rng)
        fp_rate = fpr(scn, rps, rng)
        tp = int(round(per_risk_attacks * br))
        fn = per_risk_attacks - tp
        fp = int(round(per_risk_benign * fp_rate))
        tn = per_risk_benign - fp
        _, p95r, _ = latency(scn, rps, rng)
        matrix[r] = dict(
            tp=tp, fp=fp, tn=tn, fn=fn,
            block_rate=(tp / (tp + fn) if (tp + fn) else None),
            false_positive_rate=(fp / (fp + tn) if (fp + tn) else None),
            attacks_sent=tp + fn, benign_sent=fp + tn,
            p95_latency_ms=round(p95r, 3),
        )
    p50, p95, p99 = latency(scn, rps, rng)
    return dict(
        scenario=scn, load_rps=rps, jwt_alg=alg, duration=DURATION,
        attack_fraction=ATTACK_FRACTION, synthetic=True,
        http_reqs=total,
        p50_ms=round(p50, 3), p95_ms=round(p95, 3), p99_ms=round(p99, 3),
        dropped_iterations=max(0, int((rps - SCEN[scn]["cap"]) * 60)) if rps > SCEN[scn]["cap"] else 0,
        matrix=matrix, trial=trial,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--trials", type=int, default=30)
    ap.add_argument("--lambda-star", type=int, default=220)
    ap.add_argument("--scenarios", nargs="*",
                    default=["S0", "S1", "S2", "S3", "S4", "S5", "S6", "S6fo", "S4es", "S3off"])
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    n = 0
    for scn in args.scenarios:
        alg = "ES256" if scn == "S4es" else "RS256"
        for lvl in LEVELS:
            rps = int(round(args.lambda_star * lvl))
            for t in range(1, args.trials + 1):
                rng = random.Random(f"{args.seed}-{scn}-{rps}-{t}")
                s = make_summary(scn, rps, alg, t, rng)
                fn = f"summary_{scn}_rps{rps}_{alg}_t{t}.json"
                with open(os.path.join(args.out, fn), "w") as f:
                    json.dump(s, f)
                n += 1
    # a stand-in lambda* so downstream steps have one before elbow.py runs
    with open(os.path.join(args.out, "lambda_star.txt"), "w") as f:
        f.write(str(args.lambda_star))
    print(f"wrote {n} synthetic summaries to {args.out}/ (SYNTHETIC — stamped)")


if __name__ == "__main__":
    main()
