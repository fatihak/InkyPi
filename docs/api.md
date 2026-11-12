# InkyPi HTTP API

InkyPi's web server exposes a few endpoints that other software (Home Assistant, scripts, webhooks) can call.

## Refresh the display now

`POST /api/refresh`

Regenerates whatever the display is currently showing, right away, instead of waiting for the next scheduled refresh. Use it when something outside InkyPi changes and the display should follow, for example an Image URL plugin that points to a dashboard.

- No request body or parameters are needed.
- The item to refresh is the one that was last displayed from a playlist. Playlist and plugin names do not have to be known by the caller.
- The refresh interval of the plugin instance is ignored: the image is always generated again. If the new image is identical to the one on screen, the e-ink panel is not redrawn.
- The request returns after the display has been updated. A refresh can take several seconds, so use a generous timeout.
- Only `POST` is accepted.

### Responses

| Status | When |
|---|---|
| `200` | The display was refreshed. The body names the playlist, plugin and instance that were refreshed. |
| `409` | There is nothing to refresh: nothing has been displayed yet, the current image comes from a manual "Update now" (it is not part of a playlist, so its settings are not stored), or the displayed instance was deleted. |
| `500` | The plugin failed while generating the image. `error` contains the message. |
| `503` | The background refresh task is not running. |

Example response:

```json
{
  "success": true,
  "message": "Display refreshed",
  "playlist": "Default",
  "plugin_id": "image_url",
  "plugin_instance": "Dashboard"
}
```

Errors have the form `{"success": false, "error": "..."}`.

### Examples

```bash
curl -X POST http://inkypi.local/api/refresh
```

Home Assistant (`configuration.yaml`):

```yaml
rest_command:
  inkypi_refresh:
    url: "http://inkypi.local/api/refresh"
    method: POST
    timeout: 60
```

Then call `rest_command.inkypi_refresh` from any automation, for example when a person leaves home or a to-do item is completed.
