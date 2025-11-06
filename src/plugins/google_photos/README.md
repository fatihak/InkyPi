# Load image from Google Photos album

Display a random photo from a shared Google Photos album on your InkyPi.

No API key is required. The plugin fetches the shared album page and extracts image URLs, then downloads a photo sized to your device's resolution.

## Requirements
- A Google Photos album with sharing enabled ("Anyone with the link").
- The album share link URL (looks like `https://photos.app.goo.gl/XXXXXXXXXXXX`).
- Network access from the InkyPi host.

## Setup
1. Create or open an album in Google Photos and add the photos you want to display.
2. Click Share → Create link, then copy the album share link.
3. In InkyPi, add the "Google Photos Album" plugin.
4. Paste the album share link into the plugin settings under "Google Photos album share link URL" and save.

## How it works (brief)
- The plugin loads the album's shared page and parses the embedded data to find image entries.
- One image is selected at random on each render.
- The image URL is adjusted to request a size close to your device resolution for best quality and performance.

## Notes & limitations
- Google may change the shared page format at any time; if parsing fails, check logs and update InkyPi.
- Very large albums can take longer to parse on first load.
- Only photos are supported; videos (if present in the album) are ignored.
- The selected image is random per render; frequent refreshes may repeat images.
- If your device is configured for vertical orientation, the plugin will request swapped width/height to match.

## Troubleshooting
- "Failed to load image" or empty screen:
  - Ensure the album is shared with "Anyone with the link" and the URL is correct.
  - Try opening the link in a browser where you are not logged in to confirm access.
  - Check your network connectivity and DNS on the InkyPi host.
- HTTP 403/429 errors:
  - Wait and retry; Google may temporarily rate-limit access.
- Look at the InkyPi logs for messages starting with `google_photos` for detailed errors.

## Security & privacy
- Shared album links are unlisted but not secret; anyone with the link can view the album.
- The plugin downloads images directly from Google Photos for rendering and does not upload your images elsewhere.

