# Putting Geo Quest online (PythonAnywhere, free)

This puts the site at `https://YOURNAME.pythonanywhere.com`. Replace `YOURNAME` everywhere below with your PythonAnywhere username.

The free plan keeps files permanently, so the SQLite database (everyone's accounts and progress) survives restarts.

## 1. Create an account

Sign up for a free **Beginner** account at <https://www.pythonanywhere.com/>. Your username becomes the web address.

## 2. Download the code

Open the **Consoles** tab, start a **Bash** console, and run:

```bash
git clone https://github.com/ggfret/geo-quest.git
cd geo-quest
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 3. Create the web app

1. Open the **Web** tab and click **Add a new web app**.
2. Choose **Manual configuration** (not the "Flask" option, which would create an empty app), then **Python 3.11**.
3. On the web app's page, under **Virtualenv**, enter: `/home/YOURNAME/geo-quest/.venv`
4. Under **Code**, click the link to the **WSGI configuration file**. Delete everything in it and paste this, filling in your username and an invite code of your choice:

   ```python
   import os
   import sys

   os.environ["GEO_HTTPS"] = "1"                   # only send the login cookie over HTTPS
   os.environ["GEO_INVITE_CODE"] = "pick-a-code"   # friends need this to sign up; delete the line to let anyone sign up

   path = "/home/YOURNAME/geo-quest"
   if path not in sys.path:
       sys.path.insert(0, path)

   from app import app as application
   ```

   Save the file.
5. Under **Security**, turn on **Force HTTPS**.
6. Click the big green **Reload** button at the top.

Open `https://YOURNAME.pythonanywhere.com`, sign up, and send your friends the link and the invite code.

## 4. Optional: bring your progress from your own computer

1. On your computer, sign up on the local site first and keep the "Keep the progress already on this computer" box ticked, so the progress belongs to your account.
2. In the **Files** tab on PythonAnywhere, go to `/home/YOURNAME/geo-quest/` and upload `geo.db` from your `geo-quest` folder.
3. **Reload** the web app. Log in with the same username and password as on your computer.

Do this before any friends sign up, because uploading replaces the online database.

## Updating the site later

After pushing new code to GitHub, open a Bash console on PythonAnywhere and run:

```bash
cd ~/geo-quest && git pull && .venv/bin/pip install -r requirements.txt
```

Then click **Reload** on the Web tab.

## Good to know

- **Keep it running:** free web apps have to be renewed every few months. The Web tab shows a button to extend it, and PythonAnywhere emails you before it expires.
- **Backups:** the whole database is one file, `geo.db`. Download it from the Files tab now and then.
- **Errors:** if the site shows "Something went wrong", the **error log** link on the Web tab says why.
- The login signing key is created automatically in `instance/secret_key` on the server. Deleting that file logs everyone out, but nobody loses progress.
