# Chatbot Log Analysis — prod-251 (pending SSH)

Prod GUI host: `10.134.52.251` (same credentials as test `10.134.52.250`, SSH public key not installed yet).

## Status

- Local analyzer script: `scripts/analyze_chatbot_logs.py`
- Test server report: `log_analysis_test-250_2026-06-15.md` (41 turns)
- Prod fetch blocked: `Permission denied (publickey,password)`

## Next step (ops)

```bash
# From workstation with SSH access to 251:
ssh-copy-id root@10.134.52.251

# Then run:
cd /Users/duosis-can/datalake-platform/Datalake-Platform-GUI
python3 scripts/analyze_chatbot_logs.py --ssh-host root@10.134.52.251 --label prod-251 --days 30
```

Expected focus filters: `--focus customer,crm,sales`
