# HMDL Configuration Screen (Administration › Integrations › HMDL › Configuration)

Edits the **non-secret** runtime variables (`extra_vars`) of the netbox-zabbix
AWX job template, triggers runs, and toggles schedules. Secrets (DB/Zabbix/NetBox
passwords, tokens, SNMP passphrases) are NOT shown or edited here — they live in
AWX Credentials / Vault.

## Enabling

Set on the `hmdl-api` service (see `.env.example`):

- `API_AUTH_REQUIRED=true` — **prerequisite.** The AWX routes are remote execution
  (launch a job, write `extra_vars`, toggle schedules) and `verify_api_user` is a
  no-op while this is `false`, so AWX control would be unauthenticated-writable on
  the published host port. hmdl-api therefore reports AWX as *not configured* when
  `AWX_ENABLED=true` and `API_AUTH_REQUIRED=false`.

  > **⚠️ `API_AUTH_REQUIRED` is a single SHARED variable, not an hmdl-api-only
  > setting.** It comes from the one `.env` loaded by every service via
  > `env_file:` in `docker-compose.yml` and is independently read by
  > **hmdl-api, admin-api, chatbot-api, datacenter-api, customer-api and
  > query-api**. Flipping it to `true` to unlock this screen enforces JWT
  > auth on ALL of those services at once — not just hmdl-api — in whatever
  > environment shares that `.env` (see risk **R-02** in
  > `task/architecture-audit-2026-05-12/ARCHITECTURE.md`).
  >
  > In particular, `src/services/api_client.py::_auth_headers()` only
  > attaches a JWT when called from inside an active Flask request context
  > (it returns `{}` otherwise). The GUI's background cache-warm threads
  > (`src/services/app_background_warm.py`, and the scheduler jobs described
  > in ARCHITECTURE.md §9.4) call the same backend APIs from a daemon thread
  > with no request context, so once `API_AUTH_REQUIRED=true` those warm
  > requests send no `Authorization` header and start failing with 401 —
  > silently, since warm failures are logged at `debug`/`warning` and
  > swallowed, not surfaced to an operator. Before flipping this on in any
  > shared environment, give the warm/scheduler path a service-account token
  > (or equivalent non-request-context credential) so it keeps authenticating
  > once enforcement is on.
- `AWX_ENABLED=true`
- `AWX_API_URL` — AWX REST root, e.g. `https://awx.example/api/v2`
- `AWX_TOKEN` — AWX personal access token (User → Tokens in the AWX UI)
- `AWX_NETBOX_ZABBIX_JT_ID` — the job template id (or name) for the netbox-zabbix sync
- `AWX_VERIFY_SSL` — `true` in production with valid certs. `AWX_VERIFY_SSL=false`
  disables certificate validation and the AWX bearer token is still sent over that
  unverified connection; set a CA bundle path or `true` in production.

On the AWX job template itself, check **Prompt on launch** for *Variables*
(`ask_variables_on_launch`). Without it AWX silently discards launch-time
`extra_vars`, so the **dry_run override** has no effect; the screen then shows a
yellow "override YOKSAYILDI" warning instead of the plain run confirmation.

Until enabled, the screen renders in view-only mode with an "AWX yapılandırılmadı" banner.
When AWX *is* configured but the call fails (expired token, DNS, wrong JT id, timeout),
the banner turns red and shows the reason reported by `hmdl-api`.

## Behavior

- **Kaydet** → PATCHes the job template `extra_vars` (whitelisted keys only). Every
  subsequent scheduled/manual run uses the saved values.
  Only two kinds of key are written: keys the job template already defines (so they
  stay editable *and* clearable), and keys the operator actually changed away from the
  Ansible role default. Fields marked *rol varsayılanı* are absent from the job template
  and are rendered at the role's own default
  (`roles/netbox_zabbix_sync/defaults/main.yml`); leaving them untouched writes nothing,
  so the role default keeps applying instead of being overwritten with `false`/`0`.
- **Şimdi çalıştır** → launches the job template (optional `dry_run` override), then
  polls job status.
- **Schedule** switches enable/disable AWX schedules on the job template.
