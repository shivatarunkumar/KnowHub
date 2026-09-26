# Run KnowHub on your Mac

This guide sets KnowHub up on a Mac so that it **runs all the time**: it starts by itself
when the Mac starts, and comes back by itself if it ever stops. You don't need to be a
developer. Copy each command exactly, one at a time, and check you see what the step says.

You do **steps 1–8 once**. After that there's nothing to do; the
[everyday](#everyday-use) and [updating](#updating-to-a-new-version) sections are for later.

It takes about 30–45 minutes, most of it waiting for downloads.

---

## Before you start

You need:

- **A Mac** (Apple chip or Intel) with macOS 13 or newer, and the password you use to log in.
- **A Google Cloud project** where your data will live. Ask whoever runs KnowHub for:
  - the **project ID** (looks like `my-team-project`, not the display name)
  - access for your Google account. The one-time setup creates things, so it needs:
    *BigQuery Admin*, *Storage Admin* and *Pub/Sub Editor* on that project.
    Day to day, *BigQuery Data Editor*, *BigQuery Job User* and
    *Storage Object Admin* are enough.
- **An internet connection.** KnowHub keeps its data in Google Cloud (BigQuery for
  accounts, videos and comments; Cloud Storage for the video files).

### How to open Terminal

Everything below is typed into **Terminal**. Press **⌘ Space**, type `Terminal`, press
**Enter**. A window with a blinking cursor opens. To run a command, paste it (⌘ V) and
press **Enter**. Wait until the cursor comes back before the next one.

> Lines starting with `#` inside the boxes are notes for you. They're harmless if you paste them too.

---

## Step 1 — Install the tools KnowHub needs

**1a. Homebrew** (the installer the other tools come from). Skip this if `brew --version`
already prints a version.

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

It asks for your Mac password (nothing appears as you type; that's normal) and takes a few
minutes. **When it finishes it prints "Next steps" with two or three commands: run
those too.** They make `brew` available in every new Terminal window.

**1b. The tools themselves:**

```bash
brew install git python node terraform
brew install --cask gcloud-cli
```

**Check:** close Terminal, open it again, then run:

```bash
git --version && python3 --version && node --version && terraform --version && gcloud --version
```

You should see five version lines and no "command not found". Python must be 3.12 or
newer, Node 20 or newer, Terraform 1.5 or newer.

---

## Step 2 — Download KnowHub

This puts KnowHub in a folder called `KnowHub` inside your **Documents** folder:

```bash
cd ~/Documents
git clone https://github.com/shivatarunkumar/KnowHub.git
cd KnowHub
```

> From now on, **every command is run inside this folder**. If you open a new Terminal
> window, first run `cd ~/Documents/KnowHub`.

---

## Step 3 — Create your settings file

KnowHub reads its settings from a file called `.env`. Make it from the example and open it
in TextEdit:

```bash
cp .env.example .env
open -e .env
```

Each setting is one line, `NAME=value`. Use **⌘ F** in TextEdit to find each name below and
change the part after `=`. Leave everything else as it is.

| Find | Change it to | What it's for |
|---|---|---|
| `RUN_ON=` | `RUN_ON=BQ` | use BigQuery as the database (no database to install) |
| `GCP_PROJECT_ID=` | `GCP_PROJECT_ID=your-project-id` | your Google Cloud project, from "Before you start" |
| `GCP_REGION=` | `GCP_REGION=europe-west2` | where new Google Cloud resources are created |
| `GCS_BUCKET=` | ask your admin; see the note below | where video files are stored |
| `GCS_ENDPOINT_URL=` | `GCS_ENDPOINT_URL=` (**nothing after =**) | empty means real Google Cloud Storage |
| `GCS_PUBLIC_ENDPOINT_URL=` | `GCS_PUBLIC_ENDPOINT_URL=` (nothing) | only for a local emulator, which we don't use |
| `MEDIA_PUBLIC_BASE_URL=` | `MEDIA_PUBLIC_BASE_URL=` (nothing) | same |
| `PUBSUB_EMULATOR_HOST=` | `PUBSUB_EMULATOR_HOST=` (nothing) | empty means real Google Pub/Sub |
| `LOG_LEVEL=` | `LOG_LEVEL=INFO` | keeps the log files a sensible size |
| `PROVIDER=` | `PROVIDER=none` | switches off the "Improve with AI" button; see the note |
| `JWT_SECRET=` | a random value, see below | keeps sign-ins secure. Never share it |

**The `JWT_SECRET` value:** in Terminal run

```bash
openssl rand -hex 32
```

and paste the long line it prints after `JWT_SECRET=` (no spaces, no quotes).

**About `GCS_BUCKET`:** bucket names are unique across all of Google Cloud.
- If you share your colleagues' project, use their bucket name (for example `knowhub-data`).
- If this is **your own** project, pick a new name nobody else has used, like
  `knowhub-yourname-2026`. It's created for you in step 6.

**About `PROVIDER` (optional):** to turn on the AI writing help, set `PROVIDER=openai`,
`anthropic` or `gemini`, and put your key on the matching line (`OPENAI_API_KEY=…`,
`ANTHROPIC_API_KEY=…` or `GEMINI_API_KEY=…`). Everything else works without it.

Save with **⌘ S** and close TextEdit.

---

## Step 4 — Sign in to Google Cloud

Each command opens your browser. Choose your work Google account and click **Allow**.

```bash
gcloud auth login
gcloud auth application-default login
```

Then tell Google which project to use (put your project ID in place of `your-project-id`,
in both commands):

```bash
gcloud config set project your-project-id
gcloud auth application-default set-quota-project your-project-id
```

And switch on the three Google services KnowHub uses (safe to run even if they're already on):

```bash
gcloud services enable bigquery.googleapis.com storage.googleapis.com pubsub.googleapis.com
```

---

## Step 5 — Check everything is in place

```bash
make check
```

You should see `ok` next to python3, node, npm, terraform and gcloud. If a line says
`MISSING`, install that tool (the command is printed underneath), then run `make check` again.

---

## Step 6 — One-time setup

This single command does all the setup: it installs KnowHub's own packages, creates the
storage bucket and message topics in Google Cloud, creates the database tables in
BigQuery, and prepares the website.

```bash
make setup-local
```

It takes 5–10 minutes and prints a lot. **It's finished when you see:**

```
✔ set up. Next: ./knowhub.sh start
```

Then confirm the Google Cloud connection:

```bash
make check-gcp
```

Every line should say `ok` (a yellow `warn` is fine). A `FAIL` line tells you what to run to
fix it.

> Everything in this step is safe to repeat. If it stops halfway (the Wi-Fi dropped, say),
> just run `make setup-local` again.

---

## Step 7 — Start KnowHub

```bash
./knowhub.sh start
./knowhub.sh status
```

`status` should show:

```
  API       running  http://127.0.0.1:8000
  Web app   running  http://localhost:3000
```

Open **http://localhost:3000** in your browser. Click **Register** to create your
account, and you're in.

> If macOS asks *"Do you want the application node to accept incoming network
> connections?"*: choose **Deny** if only you will use KnowHub on this Mac, or **Allow**
> if colleagues on your network should reach it too. Either way it works for you.

If `start` says **NOT STARTED**, it also says why and what to run. See
[Troubleshooting](#troubleshooting).

---

## Step 8 — Keep it running, even after a restart

**8a. Schedule it:**

```bash
./knowhub.sh cron-install
```

This adds two scheduled jobs (cron): one starts KnowHub when the Mac starts, the other
checks every 10 minutes and restarts anything that has stopped.

**8b. Let the scheduler read the KnowHub folder.** macOS protects your Documents folder, and
without this permission the scheduled jobs are silently blocked:

1. Open **System Settings → Privacy & Security → Full Disk Access**.
2. Click **+** (enter your password if asked).
3. Press **⌘ Shift G**, type `/usr/sbin/cron`, press **Enter**, then click **Open**.
4. Make sure the switch next to **cron** is **on**.

**8c. Check it works.** Wait 10 minutes, then run:

```bash
./knowhub.sh status
```

The `Cron` line should say `installed; last check N min ago`. If it says
**has never run**, go back to 8b.

**8d. Test a restart (recommended).** Restart the Mac, log in, wait two minutes, then open
http://localhost:3000. It should be there without you doing anything.

> **"All the time" means while the Mac is awake.** When the Mac sleeps, so does KnowHub,
> and it picks up again on wake. To keep a desktop Mac awake, open **System Settings →
> Energy** (or **Battery → Options** on a laptop) and turn on *Prevent automatic sleeping
> when the display is off*.

**That's the setup done.** 🎉

---

## Optional — use http://knowhub-local.com instead of localhost:3000

See **"Open it at http://knowhub-local.com"** in the [README](README.md). Afterwards run
`make setup-gcp` (so uploads are allowed from the new address), then
`./knowhub.sh restart`.

---

## Everyday use

| To… | Run |
|---|---|
| see if it's running, and where | `./knowhub.sh status` |
| stop it | `./knowhub.sh stop` (the 10-minute check starts it again; use `cron-remove` to stop for good) |
| start it now instead of waiting for the check | `./knowhub.sh start` |
| restart it (after changing `.env`) | `./knowhub.sh restart` |
| watch what it's doing | `./knowhub.sh logs` (press Ctrl C to leave) |
| list all commands | `./knowhub.sh help` |

The log files are in the `logs` folder:

| File | What's in it |
|---|---|
| `logs/knowhub.log` | what the start script did, and why it refused to start if something's wrong. **Look here first** |
| `logs/api.log` | the server: every request, and errors |
| `logs/web.log` | the website |
| `logs/cron.log` | anything printed while running from the schedule |

Logs are trimmed automatically when they pass 10 MB, and the previous part is kept as `*.1`.

---

## Updating to a new version

```bash
cd ~/Documents/KnowHub
./knowhub.sh stop
git pull
make install
make setup-bq
make build-web
./knowhub.sh start
```

`make setup-bq` only changes something when the new version added tables or columns. It's
safe to run every time.

## Changing a setting later

Edit `.env` (`open -e .env`), save, then `./knowhub.sh restart`. One exception: if you
change **`API_HOST_PORT`**, also run `make build-web` before restarting. The website
remembers where the server is when it's built, and `start` will tell you if you forget.

## Removing KnowHub

```bash
cd ~/Documents/KnowHub
./knowhub.sh cron-remove
./knowhub.sh stop
cd ~ && rm -rf ~/Documents/KnowHub
```

Your data stays in Google Cloud (the BigQuery dataset and the storage bucket) until someone
deletes it there.

---

## Troubleshooting

When KnowHub won't start, `logs/knowhub.log` (or the output of `./knowhub.sh start`) has a
**NOT STARTED** line and a **fix** line under it:

| It says | Do this |
|---|---|
| there is no .env file | step 3 |
| RUN_ON=PSQL in .env | set `RUN_ON=BQ` in `.env` (step 3) |
| JWT_SECRET in .env is not set | step 3, the `JWT_SECRET` part |
| the Python packages are not installed / the web app's packages are not installed | `make install` |
| the web app has not been built yet / was built for a different API port | `make build-web` |
| this machine is not signed in to Google Cloud | step 4 |
| port 8000 (the API) is already used by … | another program uses that port. Quit it, or pick another port: in `.env` set `API_HOST_PORT=8001` and `API_BASE_URL=http://localhost:8001`, then `make build-web` and `./knowhub.sh start` |
| port 3000 (the web app) is already used by … | quit that program (often a Terminal still running `make web`), or set `WEB_HOST_PORT=3001` and `WEB_BASE_URL=http://localhost:3001` in `.env` |
| the API stopped right after starting | read the last lines of `logs/api.log`. Usually a typo in `.env` (the error names the setting) |
| the web app stopped right after starting | read the last lines of `logs/web.log` |

**Other problems:**

| What you see | Why, and what to do |
|---|---|
| `./knowhub.sh status` says cron **has never run** | Full Disk Access is missing: step 8b |
| KnowHub doesn't come back after a restart | same as above; also check `./knowhub.sh status` says cron is *installed* (else `./knowhub.sh cron-install`) |
| the page loads but uploads fail | the bucket doesn't allow uploads from the address you're using. Check `GCS_CORS_ORIGINS` in `.env` lists it (for example `http://localhost:3000`), then `make setup-gcp` |
| signing in, liking or commenting takes about 2 seconds | normal on BigQuery: every save takes 1.5–2 s. Reading is fast |
| every page is an error | open http://localhost:8000/api/v1/health: the item that isn't `ok` is the cause. Then `make check-gcp` explains it |
| `make setup-local` fails with "permission denied" or "403" | your Google account is missing a role on the project ("Before you start") |
| `make setup-local` fails on the bucket with "already exists" / "not available" | someone else owns that bucket name: choose another `GCS_BUCKET` (step 3) |

Still stuck? Send the person who set KnowHub up the output of `./knowhub.sh status` and the
last 30 lines of `logs/knowhub.log` and `logs/api.log`:

```bash
tail -n 30 logs/knowhub.log logs/api.log
```

---

<sub>For developers: `knowhub.sh` only checks and starts things. It never installs, builds or
changes Google Cloud, so the 10-minute schedule is cheap. The API runs from `backend-bq/`
on 127.0.0.1, and the website runs as a production build (`next start`); use `make api` /
`make web` for development with auto-reload. BigQuery design and trade-offs:
[project-bq.md](project-bq.md).</sub>
