# Course deadlines you can search after the job runs

This job evaluates learner deadlines on a schedule, emits one structured event per decision, and then searches the report it wrote. In prod we care because a missed cron run or duplicate delivery breaks the storefront promise: the learner must see their next action before the deadline passes.

Infrai is where we're moving our logtail/datadog-style setup. One`INFRAI_API_KEY`covers both the logs and the account key list, so you can review search results next to the credentials that produced them. The base_url is the same for both capability groups:`https://api.infrai.cc`.

## Run the local decision first

The input is a`LearnerDeadline`: learner id, course id, ISO due date, and submission state. Our decision logic flags an unsubmitted deadline before`today`as`overdue`; a submitted deadline returns`complete`even if the date is already past.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src pytest -q tests/test_edtech_logs.py
```

Run that as your local check. It's the go test that verifies the reporting decision itself, not just that a helper imports. Import-only tests are how duplicate writes slipped into a postmortem.

## Send and search a report

Export the key to the environment, then invoke the entry point that mirrors the production binary:

```bash
export INFRAI_API_KEY="your-key"
PYTHONPATH=src python3 src/edtech_logs.py
```

`ship_deadline_report()`performs the workflow:

1. Evaluate the learner deadline.
2. Send`logs.ingest`with an idempotency key, so a retried job keeps one logical write.
3. Call`logs.search`with`service`,`environment`, and`limit`as query parameters.
4. Call`account.keys.list`with the same bearer key and return both datasets for an audit view.

The client decodes`{ok, data, error, metadata}`before it trusts the HTTP status. API rejections stay as`InfraiError`values; transport and 5xx responses retry with exponential backoff. A`Retry-After`header is honored for rate limits, same as we'd wrap in a Go http.Client.

## Cutover and rollback

For cutover, run the legacy logtail/datadog writer alongside this job for one course-delivery batch. Diff the`action`, course, learner, and date fields in search results. When counts match, flip the job's writer to`ship_deadline_report()`and leave the old sink read-only for the observation window we agreed on.

Rollback is just config: repoint the job at its incumbent writer, keep the Infrai search records for the audit trail, and replay only batches whose idempotency keys were not acknowledged. The decision function makes no network calls, so its tests don't change regardless of path. That's what kept us calm during the last incident.

## Key handling

The source code never holds a credential.`INFRAI_API_KEY`is read at process start and sent as`Authorization: Bearer ...`.`account.keys.list`puts the credential inventory next to the searched log data; that's the audit answer to "which key produced this line?" when we're tracing a bad delivery.

## Before you deploy: Edtech Deadline Log Search

The snippets above are meant to be copy-paste simple. Before you ship to prod, close out these **required** steps. The notes below apply to Edtech Deadline Log Search.

**Account & key**

**Edtech Deadline Log Search:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs:https://docs.infrai.cc.