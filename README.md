# Anki habit-tracker wallpaper

A phone wallpaper that shows your Anki progress: a year of study days as filled or empty squares, your streak, totals, and a random quiz card from your own collection. It updates itself every two hours, for free.

How it works:

1. Every two hours, GitHub (free) downloads a copy of your collection from AnkiWeb, draws the wallpaper, and posts the picture at a fixed web address.
2. The free **Remote Wallpaper** app on your phone fetches that picture on a timer and sets it as your wallpaper.

Your reviews from AnkiDroid and from Anki on your computer both count, as long as they sync to AnkiWeb. The collection is only downloaded, never uploaded, so nothing in your AnkiWeb account is changed.

## What's on it

- **Streak**: days in a row you've studied, your longest run and total study days.
- **Today**: reviews done and cards still due, with a nudge if you haven't studied yet.
- **Year tracker**: one row per month, one square per day. Filled means you studied, an outline means you missed it, the red one is today.
- **Totals**: words learned, mastered (interval of 21+ days), new this week, total reviews, hours studied, and recall over the last 30 days.
- **Quiz card**: a random card you've already learned. Its answer appears under "Last card" on the next refresh, along with a new card.

## Setup (about 15 minutes)

### 1. Make a GitHub repository

1. Sign in at [github.com](https://github.com) (a free account is fine).
2. Click **New repository**. Name it anything, for example `anki-wallpaper`.
3. Choose **Public**. The phone app needs to download the picture without logging in. Only the picture and a small `state.json` (your streak numbers and the current quiz card) become public. Your password and collection never do.
4. Click **Create repository**, then **uploading an existing file**.
5. Unzip this folder and drag everything in, including the `.github` folder. Click **Commit changes**.

If the `.github` folder doesn't come along (it's hidden on some computers), add it by hand: **Add file > Create new file**, type `.github/workflows/anki-wallpaper.yml` as the name, paste in the contents of that file from this folder, and commit.

### 2. Add your AnkiWeb login as secrets

In the repository: **Settings > Secrets and variables > Actions > New repository secret**. Add two:

| Name | Value |
|---|---|
| `ANKI_USERNAME` | the email you use for AnkiWeb |
| `ANKI_PASSWORD` | your AnkiWeb password |

Secrets are encrypted and are never shown in logs.

### 3. Run it once

1. Open the **Actions** tab. If GitHub asks, click the button to enable workflows.
2. Click **Update Anki wallpaper**, then **Run workflow**.
3. After a minute or two the run turns green. Your wallpaper is now at:

```
https://raw.githubusercontent.com/YOUR-GITHUB-NAME/YOUR-REPO-NAME/wallpaper/wallpaper.png
```

Open it in a browser to check it. The run's summary page also shows the exact link.

### 4. Set it as the wallpaper on your phone

1. On the phone, open the [Remote Wallpaper releases page](https://github.com/cssnr/remote-wallpaper-android/releases), download `app-release.apk` from the latest release and install it (allow installs from your browser when Android asks). It's free and open source. If you use Obtainium, you can add the same GitHub link there to get updates automatically.
2. Open Remote Wallpaper, add a new remote and paste your wallpaper link from step 3.
3. Set the refresh interval to about an hour and turn on cropping to fit the screen.
4. Set it as your wallpaper. The app also has a home-screen widget with a refresh button, handy right after you finish your reviews.

### 5. Keep your reviews flowing to AnkiWeb

- **AnkiDroid**: turn on automatic sync (Settings > Sync) so reviews reach AnkiWeb when you close the app.
- **Anki on a computer**: it syncs on open and close by default.

The wallpaper can only show what has reached AnkiWeb, so if numbers look behind, sync and then press **Run workflow** for an instant refresh.

## Customizing

Edit `config.json` in your repository (open it on GitHub and click the pencil icon). Changes show up on the next run.

| Setting | What it does |
|---|---|
| `timezone` | Your time zone, for deciding which day a review belongs to. Uses Anki's "next day starts at" hour too. |
| `width`, `height` | Image size. Set to 1080 x 2392 for the CMF Phone 2 Pro. |
| `top_space` | Empty space above the content, in pixels. Raise it if your clock or a widget covers the top. |
| `tracker` | `"year"` shows January to December. `"rolling"` shows the last 12 months. |
| `words_label` | Label for the first total, for example `"Cards learned"` or `"Kanji learned"`. |
| `stats_search` | Limit every number to part of your collection with Anki search syntax, for example `"deck:Spanish"`. Empty means everything. |
| `quiz_search` | Which cards the quiz picks from, for example `"deck:Spanish -is:new -is:suspended"`. |
| `background_image` | Upload a photo named `background.jpg` to the repository and it goes behind everything. |
| `background_dim` | How dark the layer over your photo is, from `0` (none) to `1` (solid). |
| `colors` | `ink` background, `paper` squares and text, `red` today and highlights, `rule` lines and missed days, `muted` small text. |

To change how often it updates, edit the `cron` line in `.github/workflows/anki-wallpaper.yml`. `"23 */2 * * *"` means minute 23 of every second hour. Every hour is `"23 * * * *"`. Please don't go below hourly; it downloads your whole collection each time.

## If something goes wrong

- **The run is red**: open it and read the step that failed. "Could not log in to AnkiWeb" usually means a typo in a secret.
- **The wallpaper on the phone doesn't change**: open the link in a browser. If the picture there is new, tap refresh in Remote Wallpaper. GitHub can also cache the picture for up to 5 minutes.
- **Updates stopped after a couple of months**: GitHub pauses scheduled runs in public repositories that look inactive. Open the Actions tab and enable the workflow again.

## Running it on your computer (optional)

With Python 3.10+ and Google Chrome installed:

```
pip install -r requirements.txt
python anki_wallpaper.py --collection "path/to/collection.anki2" --out out
```

Close Anki first. The script works on a copy, so your collection file is never modified.

## Credits

Fonts: Big Shoulders Display and Literata, both under the SIL Open Font License (see `fonts/`).
