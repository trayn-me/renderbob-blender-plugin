# RenderBob Blender Plugin

Blender extension for RenderBob: account setup, upload + estimate, start render (credits or Stripe in the browser), silent monitoring, and downloads.

## Install

1. Open Blender (`4.2+`).
2. Go to `Edit -> Preferences -> Add-ons`.
3. Click `Install from Disk...` and select the packaged `renderbob-addon.zip`.
4. Enable the addon.
5. Open `View3D -> Sidebar -> RenderBob`.

## Preferences

Under the addon preferences:

- **RenderBob API URL** — backend base URL (same as the web app’s API).
- **RenderBob web app URL** — frontend origin used for **Setup RenderBob account** (`/user-management`) and unchanged Stripe checkout links from the API.
- **Output download folder** — default directory for **Download** in the results dialog.
- Click **Save connection settings** to persist URLs (tokens are saved when you **Verify**).

## First run

1. In the sidebar, click **Setup RenderBob account** (opens User Management in the browser). Create or regenerate an API key there.
2. In **Authentication**, paste the token, click **Verify**, then **Refresh Account** if needed.

## Submit workflow

1. Save your `.blend` file.
2. Under **Render Setup**, set frames and output format. The addon uses the **middle** GPU tier (`g6.12xlarge`) for pricing and server selection, matching the web middle tier.
3. Click **Upload and Estimate** (uploads the scene, creates a draft, requests a quote). Wait until cost and duration estimates appear in the header.
4. Click **Start render** (publishes the job and pays with the current quote). If credits cover the job, payment completes in the addon. If Stripe is required, your browser opens checkout (same behavior as the web app); return to Blender when you like — the sidebar keeps polling until the job state updates.
5. After **payment is paid** and the job is no longer in `draft`, **Render Setup** is replaced by **Render Status**: **Terminate** while the job is running; **See results** when it completes successfully (dialog lists outputs; use **Refresh outputs** as frames land).

## Monitoring

The **Monitoring** panel shows progress and log phase only (no manual poll buttons). A background timer refreshes job state, progress, and `logs/status` every few seconds while a job id exists.

## Packaging

```bash
./scripts/package-addon.sh
```

Creates `dist/renderbob-addon.zip`.

## Security

- API tokens are stored in `~/.config/renderbob/settings.json` (merged with URL preferences).
- Logs are written to `~/.config/renderbob/renderbob-plugin.log`.
- TLS uses the default `urllib` certificate verification.

## Known limitations

- Upload progress reflects multipart part completion, not byte-accurate throughput.
- Background polling is HTTP-based (no WebSocket yet).
- Focusing the API token field automatically after returning from the browser is best-effort in Blender.
