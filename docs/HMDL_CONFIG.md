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
