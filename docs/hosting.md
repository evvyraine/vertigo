# Hosting Vertigo

Vertigo is a single-process Streamlit app. You can run it on a laptop for
yourself or put it behind HTTPS on a small server so your family or team can use
it from any device.

This guide covers the pieces a self-hoster needs: where data lives, how to run
it as a service, how to expose it safely over HTTPS, and how to turn on Telegram
sign-in.

- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Where your data lives](#where-your-data-lives)
- [Configuration](#configuration)
- [Run it as a service](#run-it-as-a-service)
- [Run it with Docker](#run-it-with-docker)
- [Serve it over HTTPS](#serve-it-over-https)
- [Telegram sign-in](#telegram-sign-in)
- [Security checklist](#security-checklist)
- [Updating](#updating)
- [Troubleshooting](#troubleshooting)

## Requirements

- **Python 3.11 or newer** (3.12–3.14 recommended). The repo pins a development
  interpreter in `.python-version`; any supported version works.
- [**uv**](https://docs.astral.sh/uv/) — the easiest way to install and run it.
  Plain `pip` works too.
- A **fal.ai API key** — create one at <https://fal.ai/dashboard/keys>.
- Optional: a domain name and a reverse proxy (Caddy, nginx, Traefik…) if you
  want HTTPS access from outside your network.

## Quick start

```bash
git clone https://github.com/evvyraine/vertigo.git
cd vertigo
uv sync
export FAL_KEY="your-key-here"   # or add it later on the Settings page
uv run vertigo
```

Open <http://localhost:8501>. The first run creates three profiles
(`User 1`–`User 3`) with the PIN `0000` — change the names and PINs on the
**Settings** page.

If you prefer pip:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .
vertigo
```

> **Run from the project directory.** Streamlit reads its theme, static files and
> `secrets.toml` from the working directory. Launching from elsewhere still works
> but you lose the custom theme and PWA assets.

## Where your data lives

Everything is under `~/.vertigo` by default:

```
~/.vertigo/
├── config.json        # shared settings (the fal key, cookie secret)
├── users.json         # profiles and their PIN hashes
├── sessions.json      # "remember me" session tokens (hashed)
└── users/<id>/
    ├── library.json   # that profile's media index
    ├── jobs.json      # that profile's generation queue
    └── assets/        # actual images, audio and transcripts
```

Set `VERTIGO_HOME` to move it anywhere:

```bash
VERTIGO_HOME=/srv/vertigo-data uv run vertigo
```

**Backing up** is just copying that directory (or the Docker volume). It contains
your generated media and the fal key, so store copies somewhere safe.

## Configuration

Configuration comes from environment variables first, then Streamlit secrets,
then the Settings page.

| Variable | Purpose | Default |
| --- | --- | --- |
| `FAL_KEY` | fal.ai API key (`key_id:key_secret`) | — |
| `VERTIGO_HOME` | Root data directory | `~/.vertigo` |
| `VERTIGO_PORT` | Local port used for the OIDC callback fallback | `8501` |
| `VERTIGO_SECRETS_DIR` | Where `secrets.toml` is written | `<cwd>/.streamlit` |
| `VERTIGO_OIDC_ENABLED` | `1` to require Telegram sign-in | off |
| `VERTIGO_OIDC_CLIENT_ID` | Telegram bot id from @BotFather | — |
| `VERTIGO_OIDC_CLIENT_SECRET` | Telegram client secret from @BotFather | — |
| `VERTIGO_OIDC_REDIRECT_URI` | Explicit callback URL | `<public-url>/oauth2callback` |
| `VERTIGO_PUBLIC_URL` | Public base URL, e.g. `https://vertigo.example.com` | — |

You can also keep the key in `.streamlit/secrets.toml`:

```toml
FAL_KEY = "your-key-here"
```

That file is git-ignored. When Telegram sign-in is enabled Vertigo regenerates
its own `[auth]` sections there but **preserves** any keys it does not manage, so
your `FAL_KEY` survives restarts.

Any extra command-line flags are forwarded to `streamlit run`, e.g.:

```bash
uv run vertigo --server.address 0.0.0.0 --server.port 8501
```

## Run it as a service

### systemd (Linux)

Create `/etc/systemd/system/vertigo.service`:

```ini
[Unit]
Description=Vertigo — self-hosted generative media
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=vertigo
WorkingDirectory=/opt/vertigo
Environment=VERTIGO_HOME=/var/lib/vertigo
Environment=FAL_KEY=key_id:key_secret
# Uncomment for Telegram sign-in:
# Environment=VERTIGO_OIDC_ENABLED=1
# Environment=VERTIGO_OIDC_CLIENT_ID=...
# Environment=VERTIGO_OIDC_CLIENT_SECRET=...
# Environment=VERTIGO_PUBLIC_URL=https://vertigo.example.com
ExecStart=/opt/vertigo/.venv/bin/vertigo --server.address 127.0.0.1 --server.port 8501 --server.headless true
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vertigo
sudo systemctl status vertigo
```

Keeping `--server.address 127.0.0.1` means only the reverse proxy can reach it.

### launchd (macOS)

Save `~/Library/LaunchAgents/com.example.vertigo.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.example.vertigo</string>
  <key>ProgramArguments</key>
  <array>
    <string>/opt/vertigo/.venv/bin/vertigo</string>
    <string>--server.address</string><string>127.0.0.1</string>
    <string>--server.port</string><string>8501</string>
    <string>--server.headless</string><string>true</string>
  </array>
  <key>WorkingDirectory</key><string>/opt/vertigo</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>VERTIGO_HOME</key><string>/Users/you/.vertigo</string>
    <key>FAL_KEY</key><string>key_id:key_secret</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/vertigo.log</string>
  <key>StandardErrorPath</key><string>/tmp/vertigo.err</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.example.vertigo.plist
```

## Run it with Docker

The repository ships a `Dockerfile` and a `docker-compose.yml`.

```bash
FAL_KEY="key_id:key_secret" docker compose up --build
```

The app is served on <http://localhost:8501> and its data is kept in the
`vertigo-data` named volume. To move or back it up, use `docker compose cp` or
inspect the volume directly.

To enable Telegram sign-in, uncomment the relevant variables in
`docker-compose.yml` and rebuild/restart.

## Serve it over HTTPS

Streamlit talks to the browser over a WebSocket, so the proxy must forward the
`Upgrade`/`Connection` headers and use a generous timeout.

### Caddy

Caddy gets you automatic HTTPS and handles WebSockets with no extra config:

```caddyfile
vertigo.example.com {
    encode gzip
    reverse_proxy 127.0.0.1:8501
}
```

Reload with `caddy reload --config /etc/caddy/Caddyfile`.

### nginx

```nginx
server {
    listen 443 ssl;
    server_name vertigo.example.com;

    ssl_certificate     /etc/letsencrypt/live/vertigo.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vertigo.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_buffering off;
    }
}
```

> **Progressive Web App:** Vertigo is installable (manifest + service worker).
> That requires HTTPS and serving it from the root of a domain, which the setups
> above provide.

## Telegram sign-in

By default Vertigo is protected by per-profile PINs — good enough on a trusted
LAN, but a PIN over the public internet is not a real security boundary. For an
internet-facing deployment, gate the whole app behind Telegram:

1. **Create a bot.** Talk to [@BotFather](https://t.me/BotFather), send
   `/newbot` and follow the prompts. The numeric prefix of the token is your
   **client id**.
2. **Get the client secret.** In @BotFather open *Bot Settings → Web Login* (the
   exact label depends on the current BotFather UI) to obtain the secret, and
   register your domain there so Telegram will accept the callback.
3. **Set the variables** (and restart):

   ```bash
   VERTIGO_OIDC_ENABLED=1
   VERTIGO_OIDC_CLIENT_ID=<numeric bot id>
   VERTIGO_OIDC_CLIENT_SECRET=<client secret>
   VERTIGO_PUBLIC_URL=https://vertigo.example.com
   ```

4. On startup Vertigo writes the required `.streamlit/secrets.toml`
   automatically (only the `[auth]` and `[auth.telegram]` tables). Make sure
   `${VERTIGO_PUBLIC_URL}/oauth2callback` is reachable through your proxy.

The first Telegram account to sign in becomes the admin; every account gets its
own isolated profile and library on first login.

> The exact BotFather flow for Telegram OIDC is documented by Streamlit:
> <https://docs.streamlit.io/develop/concepts/connections/authentication>.

## Security checklist

- [ ] **Never expose the app over plain HTTP.** Terminate TLS at a reverse proxy
      and bind Streamlit to `127.0.0.1`.
- [ ] **Change the default PINs.** New profiles start with `0000` and are flagged
      until changed. PINs are salted PBKDF2 hashes, but they are only profile
      separation on a trusted machine.
- [ ] **Use Telegram sign-in** (or another SSO/proxy auth layer) for anything
      reachable from the internet.
- [ ] **Protect the data directory.** `config.json` contains the fal key in plain
      text; `~/.vertigo` should be readable only by the service user.
- [ ] **Keep `secrets.toml` private.** It is git-ignored and written with mode
      `0600`, but treat it like a password file.
- [ ] **Back up `VERTIGO_HOME`** and test a restore.
- [ ] **Watch your fal.ai spend.** Usage is billed per generation; there is no
      built-in quota.

## Updating

```bash
git pull
uv sync
# restart your service (systemctl restart vertigo, docker compose up --build, …)
```

Data under `VERTIGO_HOME` is preserved across updates.

## Troubleshooting

**`FAL_KEY` not detected** — the key is read from the environment first, then
Streamlit secrets, then the saved setting. Check the Settings page for the
reported source and restart the service after exporting the variable.

**Uploads or long generations fail behind a proxy** — increase
`proxy_read_timeout` (nginx) or use `reverse_proxy` without a short timeout
(Caddy). Streamlit keeps a long-lived WebSocket open.

**The page loads but nothing updates** — WebSocket upgrades are probably blocked.
Verify the `Upgrade`/`Connection` headers are forwarded.

**Telegram login redirects to the wrong URL** — set `VERTIGO_PUBLIC_URL`
(and/or `VERTIGO_OIDC_REDIRECT_URI`) to the exact HTTPS origin, and register the
same domain in @BotFather.

**Permission denied writing `secrets.toml`** — run from a writable directory or
set `VERTIGO_SECRETS_DIR` to one.
