# Monitoring (Istio testbed)

Use the Istio addons for Prometheus + Grafana:

```bash
kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.23/samples/addons/prometheus.yaml
kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.23/samples/addons/grafana.yaml
istioctl dashboard grafana        # CPU steal, p99, Envoy ext_authz timeouts
```

Key panels for the study:
- `istio_request_duration_milliseconds` p99 by `destination_workload` (RQ1)
- `envoy_cluster_upstream_rq_timeout{cluster_name="opa"}` — ext_authz timeouts feeding A10
- container CPU (`container_cpu_usage_seconds_total`) app vs istio-proxy — where the work moves (RQ1)
- `app_fail_open_total` scraped from the app — direct fail-open evidence (RQ5)
