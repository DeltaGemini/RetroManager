# Homepage dashboard tile

RetroManager exposes library stats for a [Homepage](https://gethomepage.dev/) dashboard.

## The endpoint

```
GET http://<host>:5000/api/stats
```

```json
{
  "systems_with_roms": 22,
  "total_games": 777,
  "games_missing_metadata": 73
}
```

| Field | Meaning |
|---|---|
| `systems_with_roms` | Systems with at least one game |
| `total_games` | Games across all systems (gamelist entries plus ROMs without one) |
| `games_missing_metadata` | ROMs with no `gamelist.xml` entry |

Each call walks every system with no cache, so keep the refresh interval at a minute or more.

On error it returns HTTP 500 with `{"error": "..."}`.

## Recommended: Homepage's built-in `customapi` widget

This needs no code and no Homepage rebuild. Add this to `services.yaml`:

```yaml
- Games:
    - RetroManager:
        icon: mdi-gamepad-variant
        href: http://<server-ip>:5000
        widget:
          type: customapi
          url: http://<server-ip>:5000/api/stats
          refreshInterval: 60000
          mappings:
            - field: systems_with_roms
              label: Systems
              format: number
            - field: total_games
              label: Games
              format: number
            - field: games_missing_metadata
              label: Missing metadata
              format: number
```

If Homepage runs in Docker on the same Compose network as RetroManager, `http://retromanager:5000` also works. RetroManager's Compose file defines its own `retromanager-net` network, so this needs both containers attached to a shared network.

Check the URL works from where Homepage runs:

```bash
curl http://<server-ip>:5000/api/stats
```
