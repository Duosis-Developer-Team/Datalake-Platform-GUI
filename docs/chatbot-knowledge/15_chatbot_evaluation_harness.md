# Chatbot Evaluation Harness

Golden and adversarial YAML cases live under `services/chatbot-api/app/tests/golden/`.

## Running tests

```bash
cd services/chatbot-api
pip install -r requirements.txt
pip install ../datalake-tools-core
pytest app/tests/test_golden_chatbot.py -m "not integration"
pytest app/tests/test_format_dashboard.py
pytest app/tests/test_mcp_tool_parity.py
```

## Case schema

Each YAML entry includes:

- `id` — stable case identifier
- `user_message` — user prompt
- `conversation` — optional prior turns
- `expect` — assertions (`plan_profile`, `plan_tools_contain`, `response_type`, `answer_contains`, `tools_contain`)

## CI

Run golden tests on every PR with mock LLM / deterministic planner path. Integration mode (`@pytest.mark.integration`) can target the test-server chatbot-api when credentials are available.

## Related

- [[10_examples.md]]
- [[09_known_limitations.md]]
- Admin log viewer: `/administration/integrations/chatbot/logs`
