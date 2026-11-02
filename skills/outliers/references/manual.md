# The manual way: an account's numbers in a CSV

For an Instagram account (Instagram refuses anonymous reading) or a TikTok
account that refused today. Same math, same report: the account's median,
each reel against it.

## Where the numbers come from

The user reads them in the app, the way anyone looks at a profile; nothing
is scraped, nothing logs in for them. On the account's Reels tab, each reel
shows its views. For each of the last 15 to 30 reels, the most recent first:

- **the views** (on the grid);
- **the date**, when they can (open the reel). Without dates the lines are
  taken in the order given, most recent first, and nothing is set apart as
  too recent: say so in the report;
- **the link** (Share, then Copy link), when they can: it lets the script
  try the reel's first 10 seconds for the hook;
- likes, comments, the first line of the caption: a plus, never required.

They paste them in any form ("12/10, 34 k views, link..."); you write the
CSV with the template below.

## Template

```csv
date,lien,duree_s,vues,likes,commentaires,legende
2026-10-03,https://www.instagram.com/reel/XXXXXXXX/,38,34000,1200,85,Why your CV ends up in the bin
2026-10-01,,72,2100,48,3,My morning routine
```

English headers work too: `date,url,duration_s,views,likes,comments,caption`.

- One line per reel. An empty cell is unknown, never 0.
- Numbers like `3 400`, `3,4 k`, `3.4K`, `1.234` are read.
- Dates: `2026-10-03` is safest. `03/10/2026` is read day first in a French
  report and month first in an English one; `--date-order dmy|mdy` decides.
- Length: seconds (`38`) or `0:38`.
- No views at all: the ranking runs on likes + comments, says so, and never
  mixes them with views.

## The hooks

For the outliers only, in this order:

1. **`fichier`** (an optional column): the path of the video on the
   computer. Read locally.
2. **`lien`**: the script tries the reel's first 10 seconds anonymously,
   one reel at a time, with the same pause and the same stop after two
   refusals in a row. Instagram may let single reels through when it refuses
   the profile; it may not.
3. Neither: the caption stands in for the hook, and the report says so.

## The command

```sh
python3 <skill>/scripts/outliers.py --csv instagram:an_account=an_account.csv
python3 <skill>/scripts/outliers.py @a_tiktok_account --csv instagram:an_account=an_account.csv
```

The account name goes before `=`. With one account on the command line and
one CSV, `--csv FILE` alone is enough. Without accounts on the command line,
the CSV accounts join the watchlist's run.
