# ZTA FinTech Testbed — one-command orchestration.
# `make demo` needs only Python (no Docker). Everything else needs Docker/k6.
SHELL := /bin/bash
ALG ?= RS256
N   ?= 30

COMPOSE  := docker compose -f compose/docker-compose.yml
# images that are pulled rather than built (pre-pulled by `make images`)
IMAGES   := node:20-alpine nginx:1.27-alpine prom/prometheus:v2.54.1 \
            envoyproxy/envoy:v1.31-latest openpolicyagent/opa:0.68.0-envoy

.PHONY: help demo keys tokens images istioctl analyse check calibrate rate-limits \
        clean down up-% run-% sweep-% k8s-% all-compose

help:
	@echo "Targets:"
	@echo "  make demo            Generate synthetic data + run the full analysis (no Docker)"
	@echo "  make keys            Generate JWT keypairs + JWKS"
	@echo "  make tokens          Mint the deterministic attack-token corpus"
	@echo "  make images          Pre-pull the base images (retries on flaky networks)"
	@echo "  make up-S5           Bring up scenario S5 on Docker Compose"
	@echo "  make run-S5 N=30     Up S5, run the load sweep (N trials/level), tear down"
	@echo "  make sweep-S5        Run the k6 sweep against an already-running stack"
	@echo "  make all-compose     Run every scenario S0..S6 (+ experiment arms) on Compose"
	@echo "  make down            Tear down any running Compose stack"
	@echo "  make analyse         Ingest results/ and produce stats, tables, figures"
	@echo ""
	@echo "  -- calibrated measured run (do these in order) --"
	@echo "  make calibrate       Measure lambda* from real S0 data (wipes results/, keeps archive)"
	@echo "  make rate-limits     Set NGINX_RATE in every scenario from the measured lambda*"
	@echo "  make all-compose     Run the real sweep across every scenario"
	@echo "  make check           Analyse the sweep and print a one-screen PASS/FAIL"
	@echo ""
	@echo "  make istioctl        Fetch the pinned istioctl into tools/"
	@echo "  make k8s-setup       Install Istio + namespace + keys (needs kubectl + a cluster)"
	@echo "  make k8s-S5 N=30     Apply overlay S5 on the cluster and run the sweep"
	@echo "  make clean           Remove generated results"

# ---- no-infrastructure demo: prove the analysis works today ----
demo:
	python3 analysis/synth/generate.py --trials $(N) --lambda-star 220
	python3 analysis/run_all.py

keys:
	cd app && node src/genkeys.js
	node scripts/gen-jwks.js

tokens: keys
	cd app && npm install --omit=dev --no-audit --no-fund
	node scripts/mint-tokens.js

# ---- Docker Compose (deterministic control testbed) ----
# Docker Hub auth can drop out transiently (broken pipe / http2 handshake), which
# otherwise kills a whole sweep at the build step -- so pull up front, with retries.
images:
	@for img in $(IMAGES); do \
	  for attempt in 1 2 3 4 5; do \
	    docker image inspect "$$img" >/dev/null 2>&1 && break; \
	    echo "pulling $$img (attempt $$attempt)"; \
	    docker pull -q "$$img" >/dev/null 2>&1 && break; \
	    [ $$attempt = 5 ] && { echo "FAILED to pull $$img"; exit 1; }; \
	    sleep $$((attempt * 5)); \
	  done; \
	done
	@echo "all base images present"

# `down` first: a previous run that failed mid-sweep leaves containers behind, and
# reusing them would both break `up` on a name conflict and leak the previous
# scenario's sidecars (envoy/opa) into this one's measurements.
up-%: images
	@if [ -f results/.sweep.lock ] && kill -0 "$$(cat results/.sweep.lock)" 2>/dev/null; then \
	  echo "REFUSING: sweep pid $$(cat results/.sweep.lock) is using this stack. Stop it first."; exit 1; fi
	@$(COMPOSE) --env-file compose/scenarios/$*.env down --remove-orphans --timeout 5 >/dev/null 2>&1 || true
	$(COMPOSE) --env-file compose/scenarios/$*.env up -d --build --remove-orphans
	scripts/wait-healthy.sh

down:
	@$(COMPOSE) --env-file compose/scenarios/S0.env down --remove-orphans --timeout 5 || true

sweep-%:
	scripts/run-sweep.sh $* "$$([ -f results/lambda_star.txt ] && cat results/lambda_star.txt || echo 220)" $(N) http://localhost:8081 $(ALG)

run-%:
	$(MAKE) up-$*
	@rc=0; $(MAKE) sweep-$* || rc=$$?; \
	 $(COMPOSE) --env-file compose/scenarios/$*.env down --remove-orphans --timeout 5; \
	 exit $$rc

# S0rl is not optional. analysis/make_tables.py takes S0rl as the baseline for
# the added-p99 column -- the no-enforcement arm carrying the SAME rate limiter
# as S3-S5 -- and silently falls back to S0 when it is absent. S0 has no limiter,
# so that fallback measures the limiter instead of the enforcement point, which
# is exactly the confound S0rl exists to remove. Omitting it here made the
# fallback fire on every run.
all-compose: tokens
	for s in S0 S0rl S1 S2 S3 S4 S5 S6 S6fo S4es S3off; do $(MAKE) run-$$s N=$(N); done
	$(MAKE) analyse

# ---- Kubernetes + Istio (variable/cloud testbed) ----
istioctl:
	scripts/get-istioctl.sh

k8s-setup: istioctl
	scripts/k8s-setup.sh

k8s-%:
	scripts/k8s-run.sh $* $(N)

# ---- calibration: measure lambda*, then derive the rate limits from it ----
# The order matters. lambda* must be MEASURED (calibrate) before it can set the
# rate limits (rate-limits) before the real sweep (all-compose) can be judged
# (check). Running the sweep first would use whatever lambda* happened to be left
# in results/ -- which is how the last run inherited a synthetic one.
#
#   make calibrate                                   # default grid
#   make calibrate LOADS="100 200 400 800" DURATION=60s
calibrate:
	scripts/calibrate.sh

rate-limits:
	python3 scripts/apply_rate_limits.py

# ---- analysis ----
analyse:
	python3 analysis/run_all.py

# One screen: MEASURED-not-synthetic, benign FPR < 2%, expected block pattern.
# Exits non-zero on FAIL so it can gate a script.
check:
	python3 analysis/run_all.py
	python3 analysis/check.py

clean:
	rm -f results/summary_*.json results/tidy_*.csv results/*.md results/*.csv results/lambda_star.txt results/lambda_star.measured.txt
	rm -rf results/figures results/calibration
	@echo "cleaned results/ (example-output/ kept)"
