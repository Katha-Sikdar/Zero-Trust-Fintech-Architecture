# Object- and function-level authorization for the FinTech API, evaluated by
# OPA as an Envoy ext_authz backend (OPA-Envoy plugin input schema).
#
# Ground truth: account aNNN is owned by user uNNN (see app/src/data.js). OPA
# derives the owner from the path, decodes the forwarded JWT for sub/role, and
# returns allow/deny. This is the sidecar-layer equivalent of the app's
# in-process middleware (S5/S6), letting the study compare the two placements.
package envoy.authz

import future.keywords.if
import future.keywords.in

default allow := false

# --- request decomposition -------------------------------------------------
http := input.attributes.request.http
method := http.method
path := http.path

# Bearer token from the Authorization header (Envoy lowercases header names).
bearer := t if {
	auth := http.headers.authorization
	startswith(auth, "Bearer ")
	t := substring(auth, 7, -1)
}

claims := payload if {
	[_, payload, _] := io.jwt.decode(bearer)
}

sub := claims.sub
role := claims.role

# path segments, e.g. "/accounts/a007/transactions" -> ["accounts","a007",...]
segs := split(trim_left(path, "/"), "/")

# owner derived from the account id in the path: a007 -> u007
account_owner := replace(segs[1], "a", "u") if {
	segs[0] == "accounts"
}

# --- rules -----------------------------------------------------------------

# API1/API5 object level: a customer may act only on their own account; admin
# overrides.
allow if {
	segs[0] == "accounts"
	role == "admin"
}

allow if {
	segs[0] == "accounts"
	sub == account_owner
}

# Transfers: the source account must belong to the caller (API1 + API6 flow).
allow if {
	method == "POST"
	path == "/transfers"
	# body is forwarded by Envoy as raw bytes; decode if present
	body := json.unmarshal(base64.decode(input.attributes.request.http.body))
	from_owner := replace(body.from, "a", "u")
	sub == from_owner
}

# API5 function level: admin routes require the admin role.
allow if {
	startswith(path, "/admin/")
	role == "admin"
}

# Health/metrics are open.
allow if path == "/health"

# Decision object Envoy consumes.
decision := {
	"allowed": allow,
	"headers": {"x-authz-by": "opa"},
}
