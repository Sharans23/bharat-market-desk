# Bharat Market Desk: hosted workspace

The React frontend and Python API run together from the same repository and HTTPS origin. This is a private, single-owner workspace: all signed-in browsers see the owner's data. There is no public signup or live order execution.

## Deploy on Render

1. Connect your GitHub account to Render and grant access to the private `Sharans23/bharat-market-desk` repository.
2. Open [the Blueprint setup](https://dashboard.render.com/blueprint/new?repo=https://github.com/Sharans23/bharat-market-desk). Select the intended Render workspace and `main` branch.
3. Review the paid `0.5c-512mb` service and 1 GB persistent disk. Confirm the current price displayed by Render before applying. This configuration is not a free-tier deployment; free ephemeral storage cannot preserve this application's files.
4. Apply the Blueprint. Render builds React and the Python image from the Dockerfile, generates three secrets and mounts the data disk at `/var/data`.
5. Wait for the deploy to become Live and `/healthz` to return `status: ok`. Open the service's HTTPS address. In the service's Environment settings, copy `APP_ACCESS_KEY` directly into the application's sign-in form. Never put it in GitHub or chat.
6. In Connections, register the displayed HTTPS `/kite/callback` address in your Kite developer app. Enter the broker key and secret in the UI and complete Zerodha login. Dhan and Groww tokens can also be entered in Connections.

`RENDER_EXTERNAL_URL` supplies the origin automatically. If using a custom domain, set `PUBLIC_ORIGIN` to that exact HTTPS origin and update the broker redirect URL. Open the UI at the configured origin; requests from other origins are rejected.

## Storage and secrets

`APP_DATA_DIR=/var/data/bharat-market-desk` stores uploads, paper workspaces, broker snapshots and encrypted credential files. Broker tokens use authenticated Fernet encryption with `CREDENTIAL_ENCRYPTION_KEY`. API secrets used during Kite login remain only in memory for up to ten minutes. Snapshots and uploaded files are ordinary files on Render's encrypted disk, not individually encrypted by the application.

Keep `CREDENTIAL_ENCRYPTION_KEY` stable across redeploys. Losing or changing it makes saved broker tokens unreadable; reconnect the broker to replace them. Keep a secure copy separate from disk backups. Rotate `APP_ACCESS_KEY` to change the sign-in key and redeploy to invalidate active sessions. `SESSION_SIGNING_KEY` protects cookies; rotating it also requires everyone to sign in again.

Sessions last up to twelve hours and are invalidated by sign-out or server restart. Login attempts have a workspace-wide limit of twenty failed attempts per fifteen minutes. This is for an owner workspace, not an internet-scale multiuser service. Do not share the access key with people who should not see or modify your financial inputs.

Render disk snapshots provide a short recovery window. Also export important inputs and reports from Data workspace and result panels. Never commit real account files or credentials. The local Windows application's existing data is not automatically uploaded: export selected inputs from its UI and import them through the hosted UI when desired.

## Deployment operation

Run exactly one Gunicorn worker and one Render instance. In-process locking serializes financial writes and login-state changes. Horizontal scaling or multiple workers require a shared database and session store first. Persistent disks cause brief downtime during redeploys. GitHub checks build the UI and run Python tests; the Blueprint waits for passing checks before automatic deployment.

The container serves both `/` and `/api/*`; there is no separate Vercel project or cross-origin API configuration. Gunicorn access logging is disabled to keep callback query tokens out of application access logs. Hosting-provider request metadata may still exist under its logging policy.

## Local verification

Install Python 3.12 and Node 22. Run `pip install -r requirements.txt`, then `npm ci` and `npm run build` inside `ui`, followed by `python -m unittest discover -s tests` at the repository root. The original local launcher remains supported. Hosted deployments must use the Dockerfile/Gunicorn entrypoint, not the loopback development server.

References: [Blueprint fields](https://render.com/docs/blueprint-spec), [persistent disks](https://render.com/docs/disks), [pricing](https://render.com/pricing).
