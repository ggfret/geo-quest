# Putting Geo Quest online (Render + Neon, both free)

The website runs on [Render](https://render.com) and everyone's accounts and scores are kept in a Postgres
database on [Neon](https://neon.com). Render's free plan can't keep files, which is why the database lives
on Neon. Both free plans are permanent and need no credit card for this.

The address will be something like `https://geo-quest.onrender.com`.

## 1. Create the database on Neon

1. Sign up at <https://neon.com> (signing in with GitHub is quickest).
2. Create a project:
   - **Name:** `geo-quest`
   - **Postgres version:** 17
   - **Region:** AWS Europe Central 1 (Frankfurt), the same place the website will run
3. On the project dashboard, click **Connect** and copy the **connection string**. It starts with
   `postgresql://` and contains a password, so treat it like one: don't post it anywhere.

## 2. Optional: bring your progress from your own computer

Do this before anyone signs up online, because it only copies into an empty database. In Terminal:

```bash
cd ~/Claude/geo-quest
.venv/bin/python scripts/copy_progress.py postgresql:///geoquest "PASTE-THE-NEON-CONNECTION-STRING"
```

Keep the quotes around the connection string. It prints how many rows it copied. You'll log in online with
the same username and password as on your computer.

## 3. Create the website on Render

1. In the Render dashboard, click **New** → **Blueprint**.
2. Connect your GitHub account if asked, and pick the **geo-quest** repository.
3. Render reads `render.yaml` from the repository and shows one web service, `geo-quest`, on the free plan.
   It asks for **DATABASE_URL**: paste the Neon connection string.
4. Click **Apply** (or **Deploy Blueprint**). The first build takes a few minutes.

When it says **Live**, open the address shown at the top of the service page.

If you didn't copy your progress in step 2, **sign up first, before your friends**: the first account
(number 1) is the owner, who sees everyone's 💬 feedback at `/feedback`.

Anyone with the link can sign up. To make sign-up need a code instead, add an environment variable
`GEO_INVITE_CODE` with a code of your choice (service → **Environment**), and share the code with friends.

## Updating the site later

Push to GitHub. Render notices and redeploys by itself in a few minutes; the database isn't touched.

## Good to know

- **Sleeping:** with nobody on it for 15 minutes, the free website sleeps. The next visitor waits about a
  minute while it wakes up; after that it's quick. The database also sleeps after 5 idle minutes, but wakes
  in about a second.
- **Free limits:** Render gives 750 hours a month (enough for one site running all the time). Neon gives
  1 GB of storage (years of answers for a group of friends) and 100 compute hours a month, and only counts
  the time the database is awake.
- **Errors:** the service's **Logs** tab on Render shows what went wrong.
- **Backups:** Neon keeps a short history you can restore from (**Branches** / **Restore** in its dashboard).
  For a copy on your own computer:

  ```bash
  /opt/homebrew/opt/postgresql@17/bin/pg_dump "PASTE-THE-NEON-CONNECTION-STRING" > geo-quest-backup.sql
  ```

- **Logins:** Render created a random `GEO_SECRET_KEY` that signs the login cookie. Changing it logs
  everyone out, but nobody loses progress.
