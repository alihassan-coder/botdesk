# Orgo API (from https://www.orgo.ai/openapi.json, fetched 2026-11-27)

Servers: [{"url": "https://www.orgo.ai", "description": "Production"}] 

Security schemes: {"bearerApiKey": {"type": "http", "scheme": "bearer", "bearerFormat": "Orgo API key", "description": "Create a key in the dashboard or via POST /api/keys, then send `Authorization: Bearer <key>`."}} 

## GET /api/me
Current authenticated account — 
resp 200 Account profile and tier.
resp 401 Unauthenticated.
resp 429 

## GET /api/computers
List cloud computers (virtual desktops) — 
resp 200 Array of computers.
resp 401 Unauthenticated.
resp 429 

## POST /api/computers
Provision a new cloud computer (optionally from a template via template_ref) — With no size the computer is 4 GB RAM and 1 vCPU. A ram with no cpu gets that size’s vCPU (8 GB: 2, 16 GB: 4, 32 GB: 6, 64 GB: 8). An explicit cpu is used as given; cpu 16 passes the value check and is refused with 403 PER_COMPUTER_CPU_CAP (8 is the most one computer runs). With template_ref and no cpu/ram the template’s own size applies, with at least the vCPU of its RAM’s size (an 8 GB template launches with 2). vCPU is an account pool shared by the owner’s computers. A computer past XL (more than 6 vCPU or 32 GB, so 2XL: 8 vCPU, 64 GB), asked for or brought by a template, is set up on reque
params: [{"name": "Idempotency-Key", "in": "header", "required": false, "schema": {"type": "string", "minLength": 1, "maxLength": 255}, "description": null}]
body application/json {"$ref": "CreateComputer", "type": "object", "required": ["workspace_id", "name"], "properties": {"workspace_id": {"type": "string"}, "name": {"type": "string"}, "os": {"type": "string", "enum": ["linux", "windows", "macos", "android", "ios"], "default": "linux"}, "ram": {"type": "integer", "enum": [4, 8, 10, 16, 32, 64], "default": 4}, "cpu": {"type": "number", "enum": [0.5, 1, 2, 4, 6, 8, 16]}, "disk_size_gb": {"type": "integer", "minimum": 1}, "region": {"type": ["string", "null"], "enum": ["us", "eu", "apac", "nyc", "ash", "mia", "chi", "dal", "lax", "sjc", "lon", "syd", null], "default": "us"}, "template_ref": {"type": "string"}, "gpu": {"oneOf": [{"type": "object", "required": ["model"], "additionalProperties": false, "properties": {"model": {"type": "string", "enum": ["v710", "b50", "rtx-pro-4500", "rtx-pro-6000"]}, "slices": {"type": "integer", "enum": [1]}}}, {"type": "string", "enum": ["2q", "4q", "rtx-pro-4500", "rtx-pro-6000"]}]}, "resolution": {"type": "string"}, "ends_in_hours": {"type": ["integer", "null"], "minimum": 1, "maximum": 720}, "on_end": {"$ref": "OnEnd", "type": ["string", "null"], "enum": ["delete", null]}, "billing_mode": {"type": "string", "enum": ["hourly", "plan", "monthly"]}, "compute_request_id": {"type": "string", "format": "uuid"}}}
resp 201 Created computer.
resp 400 MISSING_FIELDS: workspace_id (or project_id) or name is missing; missing lists which, and by the hour (billing_mode hourly, or any agent account) next points at GET /api/workspaces. A value outside th
resp 401 Unauthenticated.
resp 402 An hourly launch the account’s credit cannot fund (insufficient_credit). For an hourly computer with an end, the prepay it needs: error ("This needs $0.22 of credit for 4 hours. You have $0.10." for a
resp 403 application/json {"$ref": "Error", "type": "object", "required": ["error"], "properties": {"error": {"type": "string"}, "code": {"type": "string"}, "retryable": {"type": "boolean"}, "next": {"type": "object", "required": ["method", "url", "why"], "properties": {"method": {"type": "string", "enum": ["GET", "POST"]}, "url": {"type": "string", "format": "uri"}, "body": {"type": "object", "description": "What to send, when the fix is the same call with a change."}, "why": {"type": "string"}}}, "docs_url": {"type": "string", "format": "uri"}, "add_credit_url": {"type": "string", "format": "uri"}}}
resp 409 template_ref given but the template golden is not built, the name is taken (NAME_TAKEN), or an Idempotency-Key already used for a different hourly launch (HOURLY_REQUEST_CONFLICT).
resp 429 
resp 503 REGION_UNAVAILABLE: no server where it was asked to run has room right now; nothing was made. Carries region, locations (each city and its stock: available or full) and Retry-After. ENDS_UNAVAILABLE: 

## GET /api/computers/{id}
Get a computer — Its status, hardware and connection details, and when it ends: ends_at (null: never), on_end (read only, what happens then: "delete", or "stop" for a computer whose end was set before every end deleted it; null with no end) and deletes_at (its end for on_end delete; for a computer stopped when its time ran out, ended_at, and deletes_at the day it is deleted unless it is started). An hourly computer running out a prepaid end has prepaid_until (when the prepaid run ends) and prepaid_cents (what is held for it); both are null for a computer billed by the hour and for a plan computer. out_of_memor
params: [{"name": "id", "in": "path", "required": true, "schema": {"type": "string"}, "description": null}]
resp 200 The computer.
resp 401 Unauthenticated.
resp 404 No such computer.
resp 429 

## PATCH /api/computers/{id}
Rename a computer, or set when it ends — Body: name, bot_mascot, and the end: ends_at (ISO 8601, in the future, at most 720 hours away), ends_in_hours (1 to 720), or ends_at null to keep it forever (send one of the two). When the end is up the computer is deleted: every end set or moved here deletes it, on a computer whose end was set before this rule (on_end "stop") too. on_end is not a choice: "delete" is accepted and changes nothing (alone, it needs a computer with an end: 400 INVALID_ENDS when there is none), and any other value ("stop" included) is 400 INVALID_ENDS. Changing the end needs write access to the workspace and clears
params: [{"name": "id", "in": "path", "required": true, "schema": {"type": "string"}, "description": null}]
body application/json {"type": "object", "properties": {"name": {"type": "string", "maxLength": 80}, "ends_at": {"type": ["string", "null"], "format": "date-time"}, "ends_in_hours": {"type": ["integer", "null"], "minimum": 1, "maximum": 720}, "on_end": {"$ref": "OnEnd", "type": ["string", "null"], "enum": ["delete", null]}}}
resp 200 The computer’s id and name, and ends_at, ended_at, deletes_at and on_end (read only) when the end changed or only the end was sent (an hourly computer: prepaid_until, prepaid_cents, prepay_returned_ce
resp 400 INVALID_ENDS (a time in the past, past 720 hours, both fields, an on_end other than "delete", or on_end alone for a computer with no end) or ENDS_NOT_SUPPORTED (not a Linux or Windows computer).
resp 402 insufficient_credit: a later end on an hourly computer needs more credit than there is: error, needed_cents (the extra, plus keep_cents for an hour of the owner’s other hourly computers) and available
resp 403 View only access (workspace_read_only).
resp 409 COMPUTER_BUSY (retryable): an operation (a Stop, a Start, or the end itself) holds the computer, so its end did not change.
resp 429 
resp 503 ENDS_UNAVAILABLE: ends are not set up yet, or on_end was sent where an end still stops the computer.

## DELETE /api/computers/{id}
Delete a computer and everything on it — An RTX PRO rented by the hour is given back: its billing stops this second, the card is returned and the computer deleted (the workspace owner only, 403 OWNER_ONLY). 202 RTX_HOURLY_ENDING when billing has stopped and the card is still being returned (it disappears in a minute or two); 409 RTX_HOURLY_BUSY while it is being set up or given back.
params: [{"name": "id", "in": "path", "required": true, "schema": {"type": "string"}, "description": null}]
resp 200 Deleted.
resp 202 RTX_HOURLY_ENDING: billing stopped, the card still being returned.
resp 409 The computer cannot be deleted now (its code says why; RTX_HOURLY_BUSY for a rental mid-step).
resp 429 

## POST /api/computers/{id}/start
Start a computer, optionally for a set number of hours — Starts a stopped computer (a running one answers success). Body, all optional: async (true answers 202 at once with an operation to poll), and when it ends: ends_in_hours (1 to 720, counted from when it is running) or ends_at (ISO 8601, in the future, at most 720 hours away), not both; null for either keeps it forever. When the end is up the computer is deleted, with everything on it. on_end is not a choice: "delete" is accepted with an end and changes nothing, alone it is a 400 (a Start never touches the end a computer already has), and any other value ("stop" included) is a 400. The end is c
params: [{"name": "id", "in": "path", "required": true, "schema": {"type": "string"}, "description": null}]
body application/json {"type": "object", "properties": {"async": {"type": "boolean"}, "billing_mode": {"type": "string", "enum": ["hourly"]}, "ends_in_hours": {"type": ["integer", "null"], "minimum": 1, "maximum": 720}, "ends_at": {"type": ["string", "null"], "format": "date-time"}, "on_end": {"$ref": "OnEnd", "type": ["string", "null"], "enum": ["delete", null]}}}
resp 200 Started: success, and with an end ends_at, on_end (read only), ended_at and deletes_at, and for an hourly computer prepaid_until, prepaid_cents and prepay_warning when it was not prepaid. end_not_set 
resp 202 async: the operation to poll (operation_id, poll_url), and end_pending with the end it gets once it is running.
resp 400 INVALID_ENDS (a time in the past, past 720 hours, both fields, an on_end other than "delete", or on_end without ends_in_hours or ends_at) or ENDS_NOT_SUPPORTED (not a Linux or Windows computer). Nothi
resp 402 application/json {"$ref": "Error", "type": "object", "required": ["error"], "properties": {"error": {"type": "string"}, "code": {"type": "string"}, "retryable": {"type": "boolean"}, "next": {"type": "object", "required": ["method", "url", "why"], "properties": {"method": {"type": "string", "enum": ["GET", "POST"]}, "url": {"type": "string", "format": "uri"}, "body": {"type": "object", "description": "What to send, when the fix is the same call with a change."}, "why": {"type": "string"}}}, "docs_url": {"type": "string", "format": "uri"}, "add_credit_url": {"type": "string", "format": "uri"}}}
resp 403 View only access (workspace_read_only), an end asked for by a caller PATCH refuses: computer_key (the computer’s own key or identity token) or computer_scope (a key for one computer), billing_mode "ho
resp 409 The computer cannot start now (its code says why), or OPERATION_IN_PROGRESS: another Start without this end is under way.
resp 429 
resp 503 ENDS_UNAVAILABLE: an end, or on_end, was asked for where they are not set up yet; HOURLY_WORKER_UNAVAILABLE or FREE_HOURLY_BUSY on billing_mode "hourly": try again. Nothing started.

## POST /api/computers/{id}/stop
Stop a computer — Stops a running computer; its disk is kept (a stopped computer bills storage only). By default the answer waits until it is stopped (up to 5 minutes). Send {"async": true}, ?async=true or Prefer: respond-async to get 202 at once with an operation to poll at poll_url. A Stop already under way is joined, never repeated. Stop takes no end.
params: [{"name": "id", "in": "path", "required": true, "schema": {"type": "string"}, "description": null}]
body application/json {"type": "object", "properties": {"async": {"type": "boolean"}}}
resp 200 Stopped: the operation’s result ({ success: true, ... }).
resp 202 application/json {"$ref": "OperationAccepted", "type": "object", "required": ["operation_id", "poll_url"], "properties": {"id": {"type": "string"}, "status": {"type": "string", "enum": ["starting", "stopping", "restarting"]}, "operation_id": {"type": "string", "format": "uuid"}, "operation": {"$ref": "ComputerOperation", "type": "object", "required": ["id", "desktop_id", "action", "status", "poll_url"], "properties": {"id": {"type": "string", "format": "uuid"}, "desktop_id": {"type": "string"}, "action": {"type": "string", "enum": ["start", "stop", "restore", "clear_restart", "copy"], "description": "copy: a copy of a computer billed by the hour, polled on its source (source_desktop_id)."}, "status": {"type": "string", "enum": ["queued", "running", "succeeded", "failed", "needs_review"]}, "result": {"type": ["object", "null"]}, "error": {"type": ["object", "null"], "properties": {"error": {"type": "string"}, "code": {"type": "string"}, "status": {"type": "integer"}, "retry_after": {"type": "number"}}}, "created_at": {"type": "string", "format": "date-time"}, "poll_url": {"type": "string"}}}, "poll_url": {"type": "string"}}}
resp 400 Not a JSON object, an async that is not a boolean, an end (INVALID_ENDS), or a computer this OS cannot stop (its code says why).
resp 402 TRIAL_ARCHIVE_UNAVAILABLE: a trial computer is kept by choosing a plan.
resp 403 View only access (workspace_read_only).
resp 409 The computer cannot stop now (its code says why; suspend_in_progress while its memory is being saved).
resp 429 

## POST /api/computers/{id}/bash
Run a shell command on the computer — Runs command in the computer’s shell and answers when it ends. timeout is in seconds (1 to 300, default 200). ?screen= runs it with that screen’s DISPLAY. A computer asleep is woken first.
params: [{"name": "id", "in": "path", "required": true, "schema": {"type": "string"}, "description": null}, {"name": "screen", "in": "query", "required": false, "schema": {"type": "string"}, "description": null}]
body application/json {"type": "object", "required": ["command"], "properties": {"command": {"type": "string", "minLength": 1}, "timeout": {"type": "integer", "minimum": 1, "maximum": 300}}}
resp 200 application/json {"type": "object", "properties": {"output": {"type": "string"}, "success": {"type": "boolean"}, "exit_code": {"type": "integer"}, "command": {"type": "string"}}}
resp 400 command missing or empty, the body not a JSON object, or the computer has no VM.
resp 404 No such computer (with a hint: ids change only when a computer is made again).
resp 429 

## GET /api/computers/{id}/screenshot
Capture the screen — response_format url (default) stores the image and answers its path; base64 answers it inline with mime_type, width and height; binary answers the image bytes. With no response_format, an Accept header that puts an image type first (image/*) answers the bytes too. format (png, jpeg, webp), quality (1 to 100, default 80) and scale (above 0, at most 1) shrink it. image_encoding=data_url (base64 only) prefixes the data URL header.
params: [{"name": "id", "in": "path", "required": true, "schema": {"type": "string"}, "description": null}, {"name": "response_format", "in": "query", "required": false, "schema": {"type": "string", "enum": ["url", "base64", "binary"]}, "description": null}, {"name": "format", "in": "query", "required": false, "schema": {"type": "string", "enum": ["png", "jpeg", "webp"]}, "description": null}, {"name": "quality", "in": "query", "required": false, "schema": {"type": "integer", "minimum": 1, "maximum": 100}, "description": null}, {"name": "scale", "in": "query", "required": false, "schema": {"type": "number", "exclusiveMinimum": 0, "maximum": 1}, "description": null}, {"name": "image_encoding", "in": "query", "required": false, "schema": {"type": "string", "enum": ["data_url"]}, "description": null}, {"name": "screen", "in": "query", "required": false, "schema": {"type": "string"}, "description": null}]
resp 200 application/json {"type": "object", "properties": {"success": {"type": "boolean"}, "image": {"type": "string"}, "mime_type": {"type": "string"}, "width": {"type": "integer"}, "height": {"type": "integer"}, "metadata": {"type": "object"}}}
resp 200 image/png {"type": "string", "format": "binary"}
resp 200 image/jpeg {"type": "string", "format": "binary"}
resp 200 image/webp {"type": "string", "format": "binary"}
resp 400 A query value out of range, or the computer has no VM.
resp 429 

## POST /api/computers/{id}/click
Click at a point on the screen — 
params: [{"name": "id", "in": "path", "required": true, "schema": {"type": "string"}, "description": null}, {"name": "screen", "in": "query", "required": false, "schema": {"type": "string"}, "description": null}]
body application/json {"type": "object", "required": ["x", "y"], "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "button": {"type": "string", "enum": ["left", "right"]}, "double": {"type": "boolean"}}}
resp 200 Clicked: { success: true }.
resp 400 The computer has no VM.
resp 429 

## POST /api/computers/{id}/type
Type text into whatever has focus — 
params: [{"name": "id", "in": "path", "required": true, "schema": {"type": "string"}, "description": null}, {"name": "screen", "in": "query", "required": false, "schema": {"type": "string"}, "description": null}]
body application/json {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}}
resp 200 Typed: { success: true }.
resp 400 The computer has no VM.
resp 429 

## GET /api/computers/{id}/public-urls
List a computer’s public URLs — A public URL is https://<label>.<base_domain> (web.orgo.dev) serving a port inside the computer to anyone with the link; a new one’s label is <name>-<tail> (POST). base_domain is where new ones are made; one made before it keeps its own hostname under orgo.dev and keeps working. The app must listen on 0.0.0.0:<port>, not 127.0.0.1. Answers { enabled: false, public_urls: [] } where the feature is off or the computer cannot have one (only Linux and Windows computers can). Public URLs are on every account, a free one too: `limit` is how many this computer may have (10, the same on every plan; the
params: [{"name": null, "in": null, "required": null, "schema": null, "description": null}]
resp 200 application/json {"$ref": "PublicUrlList", "type": "object", "required": ["enabled", "public_urls"], "properties": {"enabled": {"type": "boolean"}, "reason": {"type": "string"}, "base_domain": {"type": "string"}, "limit": {"type": "integer"}, "account_limit": {"type": "integer"}, "account_used": {"type": "integer"}, "can_publish": {"type": "boolean"}, "can_share": {"type": "boolean"}, "publish_refusal": {"$ref": "PublishRefusal", "type": "object", "required": ["code", "error"], "properties": {"code": {"type": "string", "enum": ["UPGRADE_REQUIRED", "HOSTING_BLOCKED", "agent_account_unclaimed", "agent_account_expired"], "description": "UPGRADE_REQUIRED: a paid plan or bought credit lifts it. HOSTING_BLOCKED: Orgo support stopped the account from publishing. agent_account_unclaimed: an agent account no person has claimed, which makes no public URL and imports no repository whatever it has bought; claiming it lifts it (POST /api/v1/agents/claim sends a new claim link). agent_account_expired: an agent account that expired before anyone claimed it. Only publish_refusal and deploy_refusal carry the two agent codes."}, "error": {"type": "string"}}}, "share_refusal": {"$ref": "PublishRefusal", "type": "object", "required": ["code", "error"], "properties": {"code": {"type": "string", "enum": ["UPGRADE_REQUIRED", "HOSTING_BLOCKED", "agent_account_unclaimed", "agent_account_expired"], "description": "UPGRADE_REQUIRED: a paid plan or bought credit lifts it. HOSTING_BLOCKED: Orgo support stopped the account from publishing. agent_account_unclaimed: an agent account no person has claimed, which makes no public URL and imports no repository whatever it has bought; claiming it lifts it (POST /api/v1/agents/claim sends a new claim link). agent_account_expired: an agent account that expired before anyone 
resp 401 Unauthenticated.
resp 403 No access to this computer, view-only access, or a share-link guest.
resp 404 Computer not found.
resp 429 

## POST /api/computers/{id}/public-urls
Make a public URL for a port on the computer — Body: { "port": 1 to 65535, "name"?: string }. A new URL is private: access team (people in the workspace, who sign in to Orgo first), protected true, until the workspace owner or an admin opens it with PATCH { access }. A free account may make one too, but only a paid one can open it wider. The URL is https://<name>-<tail>.<base_domain>: the tail is 4 characters Orgo adds (a to z and 2 to 9, no i, l or o), so read the address from the answer (url, hostname, label). The name is lowercased; 2 to 16 letters, digits and hyphens, starting and ending with a letter or digit, never two hyphens in a r
params: [{"name": null, "in": null, "required": null, "schema": null, "description": null}]
body application/json {"$ref": "CreatePublicUrl", "type": "object", "required": ["port"], "properties": {"port": {"$ref": "AppPort", "type": "integer", "minimum": 1, "maximum": 65535, "not": {"anyOf": [{"enum": [22, 3389, 8080, 9000]}, {"minimum": 5900, "maximum": 5999}, {"minimum": 6080, "maximum": 6099}]}}, "name": {"type": "string", "minLength": 2, "maxLength": 16}, "label": {"type": "string"}}}
resp 201 application/json {"$ref": "PublicUrl", "type": "object", "required": ["id", "url", "hostname", "label", "port", "created_at", "protected"], "properties": {"id": {"type": "string", "format": "uuid"}, "url": {"type": "string", "format": "uri"}, "hostname": {"type": "string"}, "label": {"type": "string"}, "port": {"type": "integer", "minimum": 1, "maximum": 65535}, "created_at": {"type": "string", "format": "date-time"}, "disabled": {"type": "boolean"}, "protected": {"type": "boolean"}, "has_password": {"type": "boolean"}, "access": {"type": "string", "enum": ["team", "people", "link"]}}}
resp 400 application/json {"$ref": "Error", "type": "object", "required": ["error"], "properties": {"error": {"type": "string"}, "code": {"type": "string"}, "retryable": {"type": "boolean"}, "next": {"type": "object", "required": ["method", "url", "why"], "properties": {"method": {"type": "string", "enum": ["GET", "POST"]}, "url": {"type": "string", "format": "uri"}, "body": {"type": "object", "description": "What to send, when the fix is the same call with a change."}, "why": {"type": "string"}}}, "docs_url": {"type": "string", "format": "uri"}, "add_credit_url": {"type": "string", "format": "uri"}}}
resp 401 Unauthenticated.
resp 403 application/json {"$ref": "Error", "type": "object", "required": ["error"], "properties": {"error": {"type": "string"}, "code": {"type": "string"}, "retryable": {"type": "boolean"}, "next": {"type": "object", "required": ["method", "url", "why"], "properties": {"method": {"type": "string", "enum": ["GET", "POST"]}, "url": {"type": "string", "format": "uri"}, "body": {"type": "object", "description": "What to send, when the fix is the same call with a change."}, "why": {"type": "string"}}}, "docs_url": {"type": "string", "format": "uri"}, "add_credit_url": {"type": "string", "format": "uri"}}}
resp 404 application/json {"$ref": "Error", "type": "object", "required": ["error"], "properties": {"error": {"type": "string"}, "code": {"type": "string"}, "retryable": {"type": "boolean"}, "next": {"type": "object", "required": ["method", "url", "why"], "properties": {"method": {"type": "string", "enum": ["GET", "POST"]}, "url": {"type": "string", "format": "uri"}, "body": {"type": "object", "description": "What to send, when the fix is the same call with a change."}, "why": {"type": "string"}}}, "docs_url": {"type": "string", "format": "uri"}, "add_credit_url": {"type": "string", "format": "uri"}}}
resp 409 application/json {"$ref": "Error", "type": "object", "required": ["error"], "properties": {"error": {"type": "string"}, "code": {"type": "string"}, "retryable": {"type": "boolean"}, "next": {"type": "object", "required": ["method", "url", "why"], "properties": {"method": {"type": "string", "enum": ["GET", "POST"]}, "url": {"type": "string", "format": "uri"}, "body": {"type": "object", "description": "What to send, when the fix is the same call with a change."}, "why": {"type": "string"}}}, "docs_url": {"type": "string", "format": "uri"}, "add_credit_url": {"type": "string", "format": "uri"}}}
resp 429 application/json {"$ref": "Error", "type": "object", "required": ["error"], "properties": {"error": {"type": "string"}, "code": {"type": "string"}, "retryable": {"type": "boolean"}, "next": {"type": "object", "required": ["method", "url", "why"], "properties": {"method": {"type": "string", "enum": ["GET", "POST"]}, "url": {"type": "string", "format": "uri"}, "body": {"type": "object", "description": "What to send, when the fix is the same call with a change."}, "why": {"type": "string"}}}, "docs_url": {"type": "string", "format": "uri"}, "add_credit_url": {"type": "string", "format": "uri"}}}
resp 503 No free tail was found for the name. Try again.

## PATCH /api/computers/{id}/public-urls/{urlId}
Point a public URL at another port, set or remove its password, or change who can open it — Body: { "port"?: number, "password"?: string or null, "access"?: "team", "people" or "link" }, at least one. access is who can open it: team (people in the workspace, who sign in to Orgo first; every new URL starts so), people (also the people it is shared with, through Apps) or link (anyone with the link). Only the workspace owner or an admin can change it (403 OWNER_OR_ADMIN_ONLY), and opening it wider needs a paid plan or at least $5 of credits bought (403 UPGRADE_REQUIRED; GET .../public-urls says can_share first). Narrowing it signs everyone out at once. A URL in a Bops workspace cannot c
params: [{"name": null, "in": null, "required": null, "schema": null, "description": null}, {"name": null, "in": null, "required": null, "schema": null, "description": null}]
body application/json {"$ref": "UpdatePublicUrl", "type": "object", "minProperties": 1, "description": "At least one of port, password and access.", "properties": {"port": {"$ref": "AppPort", "type": "integer", "minimum": 1, "maximum": 65535, "not": {"anyOf": [{"enum": [22, 3389, 8080, 9000]}, {"minimum": 5900, "maximum": 5999}, {"minimum": 6080, "maximum": 6099}]}}, "access": {"type": "string", "enum": ["team", "people", "link"]}, "password": {"type": ["string", "null"], "minLength": 8, "maxLength": 64, "pattern": "^[!-~]([ -~]*[!-~])?$"}}}
resp 200 application/json {"$ref": "PublicUrl", "type": "object", "required": ["id", "url", "hostname", "label", "port", "created_at", "protected"], "properties": {"id": {"type": "string", "format": "uuid"}, "url": {"type": "string", "format": "uri"}, "hostname": {"type": "string"}, "label": {"type": "string"}, "port": {"type": "integer", "minimum": 1, "maximum": 65535}, "created_at": {"type": "string", "format": "date-time"}, "disabled": {"type": "boolean"}, "protected": {"type": "boolean"}, "has_password": {"type": "boolean"}, "access": {"type": "string", "enum": ["team", "people", "link"]}}}
resp 400 application/json {"$ref": "Error", "type": "object", "required": ["error"], "properties": {"error": {"type": "string"}, "code": {"type": "string"}, "retryable": {"type": "boolean"}, "next": {"type": "object", "required": ["method", "url", "why"], "properties": {"method": {"type": "string", "enum": ["GET", "POST"]}, "url": {"type": "string", "format": "uri"}, "body": {"type": "object", "description": "What to send, when the fix is the same call with a change."}, "why": {"type": "string"}}}, "docs_url": {"type": "string", "format": "uri"}, "add_credit_url": {"type": "string", "format": "uri"}}}
resp 401 Unauthenticated.
resp 403 application/json {"$ref": "Error", "type": "object", "required": ["error"], "properties": {"error": {"type": "string"}, "code": {"type": "string"}, "retryable": {"type": "boolean"}, "next": {"type": "object", "required": ["method", "url", "why"], "properties": {"method": {"type": "string", "enum": ["GET", "POST"]}, "url": {"type": "string", "format": "uri"}, "body": {"type": "object", "description": "What to send, when the fix is the same call with a change."}, "why": {"type": "string"}}}, "docs_url": {"type": "string", "format": "uri"}, "add_credit_url": {"type": "string", "format": "uri"}}}
resp 404 Not found on this computer, or public URLs are not enabled for this account.
resp 409 application/json {"$ref": "Error", "type": "object", "required": ["error"], "properties": {"error": {"type": "string"}, "code": {"type": "string"}, "retryable": {"type": "boolean"}, "next": {"type": "object", "required": ["method", "url", "why"], "properties": {"method": {"type": "string", "enum": ["GET", "POST"]}, "url": {"type": "string", "format": "uri"}, "body": {"type": "object", "description": "What to send, when the fix is the same call with a change."}, "why": {"type": "string"}}}, "docs_url": {"type": "string", "format": "uri"}, "add_credit_url": {"type": "string", "format": "uri"}}}
resp 429 
resp 503 application/json {"$ref": "Error", "type": "object", "required": ["error"], "properties": {"error": {"type": "string"}, "code": {"type": "string"}, "retryable": {"type": "boolean"}, "next": {"type": "object", "required": ["method", "url", "why"], "properties": {"method": {"type": "string", "enum": ["GET", "POST"]}, "url": {"type": "string", "format": "uri"}, "body": {"type": "object", "description": "What to send, when the fix is the same call with a change."}, "why": {"type": "string"}}}, "docs_url": {"type": "string", "format": "uri"}, "add_credit_url": {"type": "string", "format": "uri"}}}

## DELETE /api/computers/{id}/public-urls/{urlId}
Remove a public URL (the app keeps running) — 
params: [{"name": null, "in": null, "required": null, "schema": null, "description": null}, {"name": null, "in": null, "required": null, "schema": null, "description": null}]
resp 204 Removed.
resp 401 Unauthenticated.
resp 403 No access to this computer, view-only access, or a share-link guest.
resp 404 Not found on this computer, or public URLs are not enabled for this account.
resp 409 application/json {"$ref": "Error", "type": "object", "required": ["error"], "properties": {"error": {"type": "string"}, "code": {"type": "string"}, "retryable": {"type": "boolean"}, "next": {"type": "object", "required": ["method", "url", "why"], "properties": {"method": {"type": "string", "enum": ["GET", "POST"]}, "url": {"type": "string", "format": "uri"}, "body": {"type": "object", "description": "What to send, when the fix is the same call with a change."}, "why": {"type": "string"}}}, "docs_url": {"type": "string", "format": "uri"}, "add_credit_url": {"type": "string", "format": "uri"}}}
resp 429 

## GET /api/computers/{id}/services
List the apps that run on a computer, with their state — An app is a command a Linux computer keeps running under its own process manager (supervisord): started at boot, started again when it exits (by its restart policy), and back by itself after a reboot, a crash, a host reboot, a restore or a wake. A running computer is asked for each app’s state (one command on the computer; never a wake). Any other computer, or any computer with live=0, is answered from the last state on file, with live: false. Answers { supported: false, services: [] } for a computer that cannot have apps (only Linux computers on Orgo’s hosts can).
params: [{"name": null, "in": null, "required": null, "schema": null, "description": null}, {"name": "live", "in": "query", "required": false, "schema": {"type": "string", "enum": ["0"]}, "description": null}]
resp 200 application/json {"$ref": "ComputerAppList", "type": "object", "required": ["supported", "services"], "properties": {"supported": {"type": "boolean"}, "reason": {"type": "string"}, "computer": {"type": "string", "enum": ["running", "asleep", "stopped", "starting"]}, "live": {"type": "boolean"}, "limit": {"type": "integer"}, "services": {"type": "array", "items": {"$ref": "ComputerApp", "type": "object", "required": ["id", "name", "kind", "command", "env", "secret_env_keys", "restart", "run_as", "enabled", "status", "applied"], "properties": {"id": {"type": "string", "format": "uuid"}, "name": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,31}$"}, "kind": {"type": "string", "enum": ["command", "deploy"], "description": "deploy: the app of a deploy, changed from the deploy."}, "deploy_project_id": {"type": ["string", "null"], "format": "uuid"}, "command": {"type": "string"}, "cwd": {"type": ["string", "null"]}, "env": {"type": "object", "additionalProperties": {"type": "string"}}, "secret_env_keys": {"type": "array", "items": {"type": "string"}, "description": "Names of the secret variables. Their values are never returned."}, "port": {"type": ["integer", "null"]}, "restart": {"type": "string", "enum": ["always", "on-failure", "no"]}, "run_as": {"type": "string"}, "enabled": {"type": "boolean"}, "status": {"type": "string", "enum": ["running", "starting", "crashing", "stopped", "exited", "failed", "pending", "off", "unknown"], "description": "pending: saved, not on the computer yet. crashing: it keeps exiting soon after it starts. failed: it could not be started."}, "status_detail": {"type": ["string", "null"], "description": "The process manager\u2019s own words, e.g. \"pid 812, uptime 2:14:09\"."}, "status_at": {"type": ["string", "null"], "format": "date-time"}, "listening": {"typ
resp 401 Unauthenticated.
resp 403 No access to this computer, view-only access, or a share-link guest.
resp 404 Computer not found.
resp 429 

## POST /api/computers/{id}/services
Add an app to a computer — Body: { name, command, cwd?, port?, restart?, run_as?, enabled?, env?, secret_env? }. name: 1-32 lowercase letters, digits and hyphens, unique on the computer. command runs with bash in cwd (default the user’s home), after /root/.env and the app’s variables are loaded; values are used as typed. restart: always (default), on-failure (started again after a non-zero exit; an exit in its first 3 seconds counts as a failed start and is retried) or no (once per boot). run_as: root by default. port: what the app listens on, unique on the computer; the computer’s own ports (22, 3389, 5900-5999, 6080-6
params: [{"name": null, "in": null, "required": null, "schema": null, "description": null}]
body application/json {"$ref": "CreateComputerApp", "type": "object", "required": ["name", "command"], "properties": {"name": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,31}$"}, "command": {"type": "string", "maxLength": 4000}, "cwd": {"type": ["string", "null"]}, "port": {"type": ["integer", "null"], "minimum": 1, "maximum": 65535}, "restart": {"type": "string", "enum": ["always", "on-failure", "no"], "default": "always"}, "run_as": {"type": "string", "default": "root"}, "enabled": {"type": "boolean", "default": true}, "env": {"type": "object", "additionalProperties": {"type": "string"}}, "secret_env": {"type": "object", "additionalProperties": {"type": "string"}}}}
resp 201 application/json {"$ref": "ComputerAppWrite", "allOf": [{"$ref": "ComputerApp", "type": "object", "required": ["id", "name", "kind", "command", "env", "secret_env_keys", "restart", "run_as", "enabled", "status", "applied"], "properties": {"id": {"type": "string", "format": "uuid"}, "name": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,31}$"}, "kind": {"type": "string", "enum": ["command", "deploy"], "description": "deploy: the app of a deploy, changed from the deploy."}, "deploy_project_id": {"type": ["string", "null"], "format": "uuid"}, "command": {"type": "string"}, "cwd": {"type": ["string", "null"]}, "env": {"type": "object", "additionalProperties": {"type": "string"}}, "secret_env_keys": {"type": "array", "items": {"type": "string"}, "description": "Names of the secret variables. Their values are never returned."}, "port": {"type": ["integer", "null"]}, "restart": {"type": "string", "enum": ["always", "on-failure", "no"]}, "run_as": {"type": "string"}, "enabled": {"type": "boolean"}, "status": {"type": "string", "enum": ["running", "starting", "crashing", "stopped", "exited", "failed", "pending", "off", "unknown"], "description": "pending: saved, not on the computer yet. crashing: it keeps exiting soon after it starts. failed: it could not be started."}, "status_detail": {"type": ["string", "null"], "description": "The process manager\u2019s own words, e.g. \"pid 812, uptime 2:14:09\"."}, "status_at": {"type": ["string", "null"], "format": "date-time"}, "listening": {"type": ["boolean", "null"], "description": "Something listens on port (null: no port, or the computer was not asked)."}, "listening_publicly": {"type": ["boolean", "null"], "description": "It listens beyond 127.0.0.1, so a public URL reaches it."}, "applied": {"type": "boolean", "description": "The computer has
resp 400 application/json {"$ref": "Error", "type": "object", "required": ["error"], "properties": {"error": {"type": "string"}, "code": {"type": "string"}, "retryable": {"type": "boolean"}, "next": {"type": "object", "required": ["method", "url", "why"], "properties": {"method": {"type": "string", "enum": ["GET", "POST"]}, "url": {"type": "string", "format": "uri"}, "body": {"type": "object", "description": "What to send, when the fix is the same call with a change."}, "why": {"type": "string"}}}, "docs_url": {"type": "string", "format": "uri"}, "add_credit_url": {"type": "string", "format": "uri"}}}
resp 401 Unauthenticated.
resp 403 No access to this computer, view-only access, or a share-link guest.
resp 409 application/json {"$ref": "Error", "type": "object", "required": ["error"], "properties": {"error": {"type": "string"}, "code": {"type": "string"}, "retryable": {"type": "boolean"}, "next": {"type": "object", "required": ["method", "url", "why"], "properties": {"method": {"type": "string", "enum": ["GET", "POST"]}, "url": {"type": "string", "format": "uri"}, "body": {"type": "object", "description": "What to send, when the fix is the same call with a change."}, "why": {"type": "string"}}}, "docs_url": {"type": "string", "format": "uri"}, "add_credit_url": {"type": "string", "format": "uri"}}}
resp 429 

## PATCH /api/computers/{id}/services/{serviceId}
Change an app — Any of the create fields. env replaces the app’s variables; secret_env changes single secrets: a value sets one, null removes one, and secrets left out are kept. Applied like a create. An app that belongs to a deploy is changed from its deploy (409 MANAGED_BY_DEPLOY).
params: [{"name": null, "in": null, "required": null, "schema": null, "description": null}, {"name": null, "in": null, "required": null, "schema": null, "description": null}]
body application/json {"$ref": "UpdateComputerApp", "type": "object", "properties": {"name": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,31}$"}, "command": {"type": "string", "maxLength": 4000}, "cwd": {"type": ["string", "null"]}, "port": {"type": ["integer", "null"], "minimum": 1, "maximum": 65535}, "restart": {"type": "string", "enum": ["always", "on-failure", "no"]}, "run_as": {"type": "string"}, "enabled": {"type": "boolean"}, "env": {"type": "object", "additionalProperties": {"type": "string"}}, "secret_env": {"type": "object", "additionalProperties": {"type": ["string", "null"]}}}}
resp 200 application/json {"$ref": "ComputerAppWrite", "allOf": [{"$ref": "ComputerApp", "type": "object", "required": ["id", "name", "kind", "command", "env", "secret_env_keys", "restart", "run_as", "enabled", "status", "applied"], "properties": {"id": {"type": "string", "format": "uuid"}, "name": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{0,31}$"}, "kind": {"type": "string", "enum": ["command", "deploy"], "description": "deploy: the app of a deploy, changed from the deploy."}, "deploy_project_id": {"type": ["string", "null"], "format": "uuid"}, "command": {"type": "string"}, "cwd": {"type": ["string", "null"]}, "env": {"type": "object", "additionalProperties": {"type": "string"}}, "secret_env_keys": {"type": "array", "items": {"type": "string"}, "description": "Names of the secret variables. Their values are never returned."}, "port": {"type": ["integer", "null"]}, "restart": {"type": "string", "enum": ["always", "on-failure", "no"]}, "run_as": {"type": "string"}, "enabled": {"type": "boolean"}, "status": {"type": "string", "enum": ["running", "starting", "crashing", "stopped", "exited", "failed", "pending", "off", "unknown"], "description": "pending: saved, not on the computer yet. crashing: it keeps exiting soon after it starts. failed: it could not be started."}, "status_detail": {"type": ["string", "null"], "description": "The process manager\u2019s own words, e.g. \"pid 812, uptime 2:14:09\"."}, "status_at": {"type": ["string", "null"], "format": "date-time"}, "listening": {"type": ["boolean", "null"], "description": "Something listens on port (null: no port, or the computer was not asked)."}, "listening_publicly": {"type": ["boolean", "null"], "description": "It listens beyond 127.0.0.1, so a public URL reaches it."}, "applied": {"type": "boolean", "description": "The computer has
resp 400 application/json {"$ref": "Error", "type": "object", "required": ["error"], "properties": {"error": {"type": "string"}, "code": {"type": "string"}, "retryable": {"type": "boolean"}, "next": {"type": "object", "required": ["method", "url", "why"], "properties": {"method": {"type": "string", "enum": ["GET", "POST"]}, "url": {"type": "string", "format": "uri"}, "body": {"type": "object", "description": "What to send, when the fix is the same call with a change."}, "why": {"type": "string"}}}, "docs_url": {"type": "string", "format": "uri"}, "add_credit_url": {"type": "string", "format": "uri"}}}
resp 404 Not found on this computer.
resp 409 Name or port taken, changed meanwhile (CHANGED), or a deploy’s app (MANAGED_BY_DEPLOY).
resp 429 

## DELETE /api/computers/{id}/services/{serviceId}
Remove an app (it is stopped, and its files and log are removed) — 
params: [{"name": null, "in": null, "required": null, "schema": null, "description": null}, {"name": null, "in": null, "required": null, "schema": null, "description": null}]
resp 200 application/json {"type": "object", "properties": {"deleted": {"type": "boolean"}, "apply": {"$ref": "ComputerAppApply", "type": "object", "required": ["state"], "properties": {"state": {"type": "string", "enum": ["applied", "pending", "failed"], "description": "pending: applied when the computer next runs, or on Orgo\u2019s next try."}, "error": {"type": "string"}}}}}
resp 404 Not found on this computer.
resp 409 A deploy’s app (MANAGED_BY_DEPLOY).
resp 429 

## GET /api/computers/{id}/services/{serviceId}/logs
The last lines of an app’s output (stdout and stderr together) — 
params: [{"name": null, "in": null, "required": null, "schema": null, "description": null}, {"name": null, "in": null, "required": null, "schema": null, "description": null}, {"name": "lines", "in": "query", "required": false, "schema": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 200}, "description": null}]
resp 200 application/json {"type": "object", "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "lines": {"type": "integer"}, "found": {"type": "boolean"}, "log": {"type": "string"}}}
resp 404 Not found on this computer.
resp 409 The computer is not running (COMPUTER_NOT_RUNNING).
resp 429 

## GET /api/computers/{id}/operations/{operationId}
Poll a Start, Stop, restore or Clear and restart — The poll_url a 202 gave. Poll every Retry-After seconds (2) until status is succeeded, failed or needs_review. succeeded carries result; failed carries error ({ error, code, status, retry_after? }).
params: [{"name": "id", "in": "path", "required": true, "schema": {"type": "string"}, "description": null}, {"name": "operationId", "in": "path", "required": true, "schema": {"type": "string", "format": "uuid"}, "description": null}]
resp 200 application/json {"$ref": "ComputerOperation", "type": "object", "required": ["id", "desktop_id", "action", "status", "poll_url"], "properties": {"id": {"type": "string", "format": "uuid"}, "desktop_id": {"type": "string"}, "action": {"type": "string", "enum": ["start", "stop", "restore", "clear_restart", "copy"]}, "status": {"type": "string", "enum": ["queued", "running", "succeeded", "failed", "needs_review"]}, "result": {"type": ["object", "null"]}, "error": {"type": ["object", "null"], "properties": {"error": {"type": "string"}, "code": {"type": "string"}, "status": {"type": "integer"}, "retry_after": {"type": "number"}}}, "created_at": {"type": "string", "format": "date-time"}, "poll_url": {"type": "string"}}}
resp 404 No such operation on this computer.
resp 429 

## POST /api/computers/{id}/restart
Restart a computer — Reboots the computer in place; the disk is kept. A GPU computer is restarted by clearing its disk, which needs an explicit {"clear_disk": true} (409 RESTART_CLEARS_DISK without it): a copy of /root is saved first, and the answer is 202 with an operation to poll.
params: [{"name": "id", "in": "path", "required": true, "schema": {"type": "string"}, "description": null}]
body application/json {"type": "object", "properties": {"clear_disk": {"type": "boolean"}}}
resp 200 Restarted: { success: true }.
resp 202 application/json {"$ref": "OperationAccepted", "type": "object", "required": ["operation_id", "poll_url"], "properties": {"id": {"type": "string"}, "status": {"type": "string", "enum": ["starting", "stopping", "restarting"]}, "operation_id": {"type": "string", "format": "uuid"}, "operation": {"$ref": "ComputerOperation", "type": "object", "required": ["id", "desktop_id", "action", "status", "poll_url"], "properties": {"id": {"type": "string", "format": "uuid"}, "desktop_id": {"type": "string"}, "action": {"type": "string", "enum": ["start", "stop", "restore", "clear_restart", "copy"], "description": "copy: a copy of a computer billed by the hour, polled on its source (source_desktop_id)."}, "status": {"type": "string", "enum": ["queued", "running", "succeeded", "failed", "needs_review"]}, "result": {"type": ["object", "null"]}, "error": {"type": ["object", "null"], "properties": {"error": {"type": "string"}, "code": {"type": "string"}, "status": {"type": "integer"}, "retry_after": {"type": "number"}}}, "created_at": {"type": "string", "format": "date-time"}, "poll_url": {"type": "string"}}}, "poll_url": {"type": "string"}}}
resp 403 View only access (workspace_read_only).
resp 409 RESTART_CLEARS_DISK (a GPU computer, sent without clear_disk), insufficient_space, or another operation holds the computer.
resp 429 

## POST /api/computers/{id}/key
Press a key or a shortcut — key is a key name or a shortcut joined with +, for example Enter, Escape or ctrl+c.
params: [{"name": "id", "in": "path", "required": true, "schema": {"type": "string"}, "description": null}, {"name": "screen", "in": "query", "required": false, "schema": {"type": "string"}, "description": null}]
body application/json {"type": "object", "required": ["key"], "properties": {"key": {"type": "string"}}}
resp 200 Pressed: { success: true }.
resp 400 The computer has no VM.
resp 429 

