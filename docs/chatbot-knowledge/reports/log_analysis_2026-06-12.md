# Chatbot Log Analysis — 2026-06-12

Source: `http://localhost:8000` (chatbot-log-api)

Turns analyzed: **0** (log-api unavailable in local run — run `scripts/analyze_chatbot_logs.py --url <log-api> --key <key>` on test server)

## Status distribution

- No turns fetched in this baseline run.

## Averages

- Latency (ms): n/a
- Tool calls: n/a
- LLM rounds: n/a

## Top tools

- n/a

## Quality signals

- Answers containing markdown tables: n/a
- Success turns with empty investigation_trace: n/a

## Manual review checklist

- [ ] Table readability in narrow vs expanded panel
- [ ] Wrong tool selection / unnecessary clarification
- [ ] Generic denial phrases in executive answers
- [ ] Multi-turn context carry-over

## Notes

Re-run after deploy with:

```bash
python scripts/analyze_chatbot_logs.py --url http://10.134.52.250:<log-api-port> --key "$CHATBOT_LOG_API_KEY" --days 30
```
