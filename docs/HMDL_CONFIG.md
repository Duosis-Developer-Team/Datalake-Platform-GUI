# HMDL Configuration Screen (Administration › Integrations › HMDL › Configuration)

Edits the **non-secret** runtime variables (`extra_vars`) of the netbox-zabbix
AWX job template, triggers runs, and toggles schedules. Secrets (DB/Zabbix/NetBox
passwords, tokens, SNMP passphrases) are NOT shown or edited here — they live in
AWX Credentials / Vault.

## Enabling

Set on the `hmdl-api` service (see `.env.example`):

- `AWX_ENABLED=true`
- `AWX_API_URL` — AWX REST root, e.g. `https://awx.example/api/v2`
- `AWX_TOKEN` — AWX personal access token (User → Tokens in the AWX UI)
- `AWX_NETBOX_ZABBIX_JT_ID` — the job template id (or name) for the netbox-zabbix sync
- `AWX_VERIFY_SSL` — `true` in production with valid certs

Until enabled, the screen renders in view-only mode with an "AWX yapılandırılmadı" banner.

## Behavior

- **Kaydet** → PATCHes the job template `extra_vars` (whitelisted keys only). Every
  subsequent scheduled/manual run uses the saved values.
- **Şimdi çalıştır** → launches the job template (optional `dry_run` override), then
  polls job status.
- **Schedule** switches enable/disable AWX schedules on the job template.
