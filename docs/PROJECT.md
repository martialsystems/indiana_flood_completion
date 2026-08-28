# Upper White flood (git project)

Two trees, one basin (HUC-8 05120201).

| Tree | GitHub | Role |
|------|--------|------|
| `indiana_flood_completion` | public `martialsystems/indiana_flood_completion` | Map completion: `P(sfha \| hydro)` on the HUC |
| `white_river_stage_inundation` | private `martialsystems/white_river_stage_inundation` | Nora reach stage inundation: USGS 03351000, two Delta values |

Interview notes are merged in [interview_note.pdf](interview_note.pdf). Do not reopen D, B, or HAND. No third Delta. No second HUC.

GitHub Projects (board) needs a token with the `project` scope. From a machine that can complete the browser prompt:

```bash
gh auth refresh -h github.com -s project,read:project
gh project create --owner martialsystems --title "Indiana flood"
gh project link --owner martialsystems --repo martialsystems/indiana_flood_completion
gh project link --owner martialsystems --repo martialsystems/white_river_stage_inundation
```

This checkout cannot mint that scope. The two repositories are linked here in git instead.
