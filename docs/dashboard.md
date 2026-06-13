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
seconds. When you are near the top overview it applies updates automatically;
when you are reading lower content it pauses automatic updates and shows a
"new data available" banner, so the page does not jump while you read.
Dashboard failures are reported to stderr and do not stop result generation.
