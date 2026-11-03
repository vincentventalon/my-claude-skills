# script : le script de ta prochaine vidéo courte

*La skill comprend aussi l'anglais (« write my script », « hook for this video »). This guide is in
French; the skill writes the script in the language you record in.*

## Ce que ça fait

Tu donnes un sujet ou une anecdote, Claude te rend le script d'une vidéo face caméra de 30 s à
2 min (TikTok, Reels, Shorts), prêt à tourner :

- **3 hooks**, chacun tiré d'une des 22 formules nommées, avec pourquoi il fait rester. Un hook ne
  s'invente pas : il se récupère parmi ceux qui ont marché.
- **3 hooks texte** pour l'écran, ce qu'on lit sans le son, déjà au format du titre de la skill
  `edit`.
- **Le script**, bloc par bloc : le hook, la lock-in zone (trois gestes avant 15 s), le corps en
  « mais / donc » (jamais « et puis »), le double payoff, les relances, les CTA aux coutures.
- **Les notes visuelles** de chaque bloc : plein cadre, slide, chiffre, objet réel.
- **Une passe anti-slop** : les mots d'IA en français et en anglais, les tournures écrites qui ne
  se disent pas, et le test du comptoir (« tu le dirais à un pote au comptoir ? »).
- **Le timing** à ton débit, bloc par bloc.

Tout dans `script.md`, dans ton dossier. Les règles viennent de ce qui a été mesuré sur 100 vidéos
publiées et 60 comptes étudiés : ce qui fait rester, ce qui ne change rien (la longueur du hook, un
chiffre), ce qui fait partir (un hook qui parle de ton compte, une présentation).

```
toi     écris-moi le script : j'ai automatisé mes relances clients avec un script Python
claude  Pour qui, quelle durée, tu donnes le script ? Raconte-moi ce qui s'est passé, avec les chiffres.
toi     les freelances, 60-75 s, oui, mot RELANCE. Une facture de 1 200 € payée deux mois en retard…
claude  3 hooks, 3 hooks texte, le script : 183 mots, 61 à 73 s, dans la cible.
        Rien à remplir. À toi : le hook, le hook texte, un save ou pas.
        → script.md
```

Le script complet de cet exemple : [references/exemple.md](references/exemple.md).

## Ce que tu dis à Claude

« écris-moi un script sur… », « le script de ma prochaine vidéo », « un hook pour cette vidéo »,
« write my script », « give me hooks », ou tu dictes ton anecdote telle quelle.

## Avec les autres skills

- **`audit`** (ton compte) : s'il y a un `audit-*/AUDIT.md` dans le dossier, le script part de tes
  meilleurs hooks et de la durée qui marche chez toi.
- **`outliers`** (ta niche) : s'il y a un `outliers-*/OUTLIERS.md`, il part des « 5 à refaire ».
- **`edit`** : le bloc « Pour le montage » du script lui donne le titre du haut et le carton de fin.

Pour chercher parmi des milliers de vrais hooks qui ont marché, branche le connecteur Nadia
(usenadia.com) : avec un compte, Claude cherche les hooks par sujet et par forme (outils
`hooksSearchTool`, `hooksFormsTool`).

## Prérequis

Claude Code, et Python 3 pour le compteur (`scripts/timing.py`, rien à installer). Aucun appel
réseau, rien de payant.

## Ce que ça ne promet pas

Les règles viennent de vues comparées à la normale de chaque compte : des corrélations, pas des
lois. Un bon script ne garantit aucune vue ; le sujet, la façon de le dire et le moment comptent
autant. Et il sonne comme toi dans la mesure où Claude a tes mots : donne-lui tes transcripts.
