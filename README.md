# RenderBob Blender Plugin

Blender extension for RenderBob: account setup, **Bob** as the **3D Viewport sidebar** interface (chat drives preflight, quotes, starting renders, and job status), plus authentication and downloads.

## Install

1. Open Blender (`4.2+`).
2. Go to `Edit -> Preferences -> Add-ons`.
3. Click `Install from Disk...` and select the packaged `renderbob-addon.zip`.
4. Enable the addon.
5. In the **3D Viewport**, press **N** to open the sidebar (if hidden), then open the **RenderBob** tab.

## Preferences

Under the addon preferences:

- **RenderBob API URL** — backend base URL (same as the web app’s API).
- **RenderBob web app URL** — frontend origin used for **Setup RenderBob account** (`/user-management`) and unchanged Stripe checkout links from the API.
- **Output download folder** — default directory for **Download** in the results dialog.
- Click **Save connection settings** to persist URLs (tokens are saved when you **Verify**).

## First run

1. In the **RenderBob** sidebar tab, click **Setup RenderBob account** (opens User Management in the browser). Create or regenerate an API key there.
2. Expand **Authentication**, paste the token, click **Verify**, then **Refresh Account** if needed.

## Bob (chat) workflow

The main **RenderBob** sidebar tab is the chat. Ask in natural language (for example: “preflight this scene”, “what’s my render config?”, “get a quote”, “start the render”, “job status”, “open outputs”). Bob may run local checks, show your current frame range and engine settings, or ask you to confirm **upload/estimate** or **start render** — use **Yes** / **No** on those prompts (same credit and Stripe checkout behavior as the web app).

1. Save your `.blend` file before uploading.
2. Set frames and output format on the scene as usual; Bob’s “present config” reply reflects current settings. The addon uses the **middle** GPU tier (`g6.12xlarge`) for pricing and server selection, matching the web middle tier.
3. While a job exists, the same panel shows progress, terminate, logs, and **See results** when the job completes.

A background timer still refreshes job state, progress, and `logs/status` every few seconds while a job id exists.

## Packaging

```bash
./scripts/package-addon.sh
```

Creates `dist/renderbob-addon.zip` (source `.py` files only; safe for Blender’s bundled Python).

### “bad magic number” after install

That error means Blender tried to load **`.pyc` bytecode** built with a **different Python** than the one inside Blender (e.g. zip built with macOS `python3.13` while Blender 4.2 uses 3.11). Fix: rebuild the zip with this script (source-only), remove the broken add-on in **Preferences → Get Extensions / Legacy Add-ons**, then install again. If it persists, delete any leftover `renderbob` folder under Blender’s extensions directory and reinstall.

## Security

- API tokens are stored in `~/.config/renderbob/settings.json` (merged with URL preferences).
- Logs are written to `~/.config/renderbob/renderbob-plugin.log`.
- TLS uses the default `urllib` certificate verification.

## Known limitations

- Upload progress reflects multipart part completion, not byte-accurate throughput.
- Background polling is HTTP-based (no WebSocket yet).
- Focusing the API token field automatically after returning from the browser is best-effort in Blender.
