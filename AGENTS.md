# NBA Dream Team GM agent rules

Read `README.md` before editing. The game source is `static/index.html`; generated
`dist/` is not committed. Preserve existing user changes in a dirty worktree.

## Shared UI verification

From `C:\Users\User\claude_try`, run:

```powershell
npm run ui:shot -- nba
```

This builds with Python inside the shared container, serves port 8000, captures the
team and market pages at three mobile sizes, and writes evidence to
`artifacts/ui-lab/nba/`. Inspect every screenshot and `report.json` before declaring
a UI task complete. Use the Codex in-app Browser at `http://127.0.0.1:8000/` for
interactive checks.
