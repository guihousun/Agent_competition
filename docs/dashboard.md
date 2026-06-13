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

- `dashboard.html`: local question, answer, timing, error, LLM-call,
  and tool-call view.
- `dashboard-state.json`: live state used by the dashboard page.
- `traces.json`: structured trace data for the same run.

Open `dashboard.html` in a browser while the run is active. Each question is
shown as running when it starts. The page polls `dashboard-state.json` every 3
seconds and updates the page content without a full browser refresh, so scroll
position and expanded sections are preserved while reading. Dashboard failures
are reported to stderr and do not stop result generation.
