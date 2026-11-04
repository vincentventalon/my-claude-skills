# The manual way: your own numbers in a CSV

When TikTok refuses the anonymous reading of the profile, the audit runs on
numbers the user gives. Same report, same math. (This skill reads TikTok
only: an Instagram account is not audited, not even this way.)

## Where the numbers come from

**A. An export of their stats.** TikTok Studio on a computer
(tiktok.com/tiktokstudio, Analytics, then Content) can download its figures
as a CSV. The menus move with TikTok's updates: if the user cannot find it, go
to B. Give the file to the script as it is: the usual columns (Publish time,
Duration, Link, Views, Likes, Comments, Shares, Saves, Description, and their
French versions) are recognized. The script prints the columns it read and
those it ignored: check that `views` is among the read ones.

**B. They paste their numbers.** In the app, each video shows its views. The
user pastes them in any form ("12/10, 3 400 views, 120 likes, 8 comments,
link..."); you write the CSV with the template below. 15 videos are enough
to start; the most recent first.

## Template

```csv
date,lien,duree_s,vues,likes,commentaires,partages,enregistrements,legende,fichier
2026-10-03,https://www.tiktok.com/@me/video/7300000000000000000,38,3400,120,8,5,40,Why your CV ends up in the bin #cv #jobs,
2026-10-05,,72,1150,48,3,2,12,My morning routine #routine,/Users/me/Movies/routine.mov
```

English headers work too: `date,url,duration_s,views,likes,comments,shares,saves,caption,file`.

- One line per video. An empty cell is unknown, never 0.
- Numbers like `3 400`, `3,4 k`, `3.4K`, `1.234` are read.
- Dates: `2026-10-03` is safest. `03/10/2026` is read day first in a French
  report and month first in an English one; `--date-order dmy|mdy` decides.
- Length: seconds (`38`) or `0:38`.
- No views at all: the ranking runs on likes + comments, says so, and never
  mixes them with views.

## The hooks in the manual way

For each line, in this order:

1. **`fichier`**: the path of the video on the computer (the original from
   the phone, or the one from the account's data export). Read locally,
   nothing goes online. The most reliable.
2. **`lien`**: the video's TikTok link. The script tries to read its first
   10 seconds anonymously, one video at a time, with the same pause and the
   same stop after two refusals in a row. TikTok may let single videos
   through when it refuses the profile; it may not.
3. Neither: the caption stands in for the hook, and the report says so.

## The command

```sh
python3 <skill>/scripts/audit.py @their_account --csv their_numbers.csv --followers 2400 --lang fr
```
