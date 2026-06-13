# Local Dashboard

The dashboard is disabled by default and is not enabled by `start.sh`.

For a local diagnostic run:

```bash
python -u -m source.main \
  --question /path/to/questions.json \
  --output /path/to/results.json \
  --dashboard
```

The runner creates these files next to `results.json`:

- `dashboard.html`: auto-refreshing question, answer, timing, error, LLM-call,
  and tool-call view.
- `traces.json`: structured trace data for the same run.

Open `dashboard.html` in a browser while the run is active. Each question is
shown as running when it starts. The page is refreshed after every completed
LLM call and tool call, and again after the result has been written. Dashboard
failures are reported to stderr and do not stop result generation.
