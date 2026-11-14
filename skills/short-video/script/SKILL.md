---
name: script
description: >
  Écrit le script d'une vidéo face caméra courte (TikTok, Reels) avec une méthode mesurée
  sur 100 vidéos publiées et 60 comptes étudiés : 3 hooks tirés de 22 formules nommées (un hook se
  récupère, il ne s'invente pas), 3 hooks texte pour l'écran, le script oral en beats « mais /
  donc » avec lock-in, double payoff, relances et CTA aux coutures, les notes visuelles pour le
  montage, une passe anti-slop (test du comptoir) et le timing au débit, dans script.md. Part de
  l'audit du compte et des outliers de la niche s'ils sont dans le dossier. À utiliser quand on dit
  « écris-moi un script », « le script de ma prochaine vidéo », « un hook pour… », « trouve-moi un
  hook », « write my script », « script my next video », « hook for this video », « give me
  hooks », ou qu'on dicte un sujet ou une anecdote à transformer en vidéo.
---

# Script : une vidéo courte qui tient jusqu'au bout

Tu écris le script d'une vidéo face caméra de 30 s à 2 min que la personne va dire elle-même.
Chaque choix (le hook, l'ordre des beats, les CTA, la durée) vient d'une règle mesurée sur 100
vidéos publiées et 60 comptes étudiés, et le script dit pourquoi chaque pièce est là : on tourne
mieux ce qu'on comprend.

> **La règle qui gouverne les autres.** Une règle de cette skill résume une mesure, ce n'est pas
> une case à cocher. Si l'appliquer oblige à fabriquer quelque chose (un chiffre, une anecdote,
> une ressource, une citation, une thèse), elle ne s'applique pas ici : tu l'écartes et tu le dis.
> Un script sans chiffre vaut mieux qu'un script avec un chiffre inventé.

`<skill>` ci-dessous : le dossier de cette skill. `references/hooks.md` (les 22 formules et le hook
texte), `references/structure.md` (la structure, les CTA, les notes visuelles),
`references/anti-slop.md` (la passe, en français et en anglais), `references/exemple.md` (un script
complet), `scripts/timing.py` (Python 3, rien à installer). Tout ce que tu écris va dans le dossier
courant, jamais dans celui de la skill.

## 1. Demander ce qu'il faut, rien de plus

En un seul message, et seulement ce qui manque (ce que la personne a déjà dit, ou ce que l'audit
donne, ne se redemande pas) :

1. **Le sujet ou l'anecdote** : ce qui s'est passé, avec les vrais chiffres et les vrais noms s'il
   y en a.
2. **Pour qui** : le spectateur visé, en une ligne.
3. **La durée visée** : 60 à 75 s par défaut.
4. **Une ressource à offrir ?** L'objet (un modèle, un script, une liste) et le mot à commenter
   (« commente RELANCE »). Pas d'objet : pas de CTA commentaire.

Le script s'écrit dans la langue où la personne tourne (par défaut, celle dans laquelle elle te
parle). Son débit, si elle le connaît.

## 2. Partir de ce qui marche chez elle

Avant d'écrire, regarde dans le dossier courant (le plus récent s'il y en a plusieurs) :

- **`audit-*/AUDIT.md`** (skill `audit`, son compte) : le bloc « Pour le montage » (« For the
  edit » en anglais) donne `target_duration_s` (la durée par défaut), `hook_style` et
  `hook_example` (la forme des hooks qui ont gagné chez elle : la première source de forme),
  `title_on_screen` (le hook texte : oui, non, à tester) ; la section des hooks des meilleures
  vidéos contre les moins bonnes montre ce qui fait rester **ses** spectateurs.
- **`outliers-*/OUTLIERS.md`** (skill `outliers`, sa niche), le tableau « Les 5 à refaire »
  (« 5 to remake ») : une ligne par idée qui a fait bien plus que d'habitude chez d'autres (sujet,
  hook d'origine, pourquoi ça a marché, son angle, source). Sujet ouvert : propose une ligne, avec
  son angle. Sujet proche : la structure de son hook d'origine est la première forme que tu
  adaptes (la structure, jamais les mots), et son angle est un point de départ pour la thèse.
- **Ses transcripts** (les `<nom>.txt` que `edit` écrit à côté des vidéos montées) : l'étalon de
  sa voix. Un mot que tu ajoutes et qu'elle ne dit jamais se remplace par le sien.

Ses chiffres à elle passent avant les règles générales de cette skill. Rien de tout ça : dis en une
ligne que `audit` (son compte) et `outliers` (sa niche) le donnent, et continue.

## 3. La thèse et les faits, avant tout le reste

- **La thèse**, en une phrase : ce que la vidéo prouve ou donne. Le hook la vend, le corps la
  démontre, la fin la referme.
- **Les faits** : une table de tout ce que la personne a dit (chiffres, noms, dates, résultats).
  Ce sont les seuls utilisables. Ce qui manque devient `{{ton chiffre}}`, `{{le nom du client}}`,
  listé dans « À remplir ». Jamais une phrase entre guillemets attribuée à quelqu'un qui ne l'a pas
  dite.
- **Le sujet** : *est-ce qu'on repart avec quelque chose d'utilisable ?* (un outil nommé, une
  méthode, des étapes). C'est le plus gros levier mesuré, plus que le hook. Si non (motivation,
  le compte lui-même, un avis seul), dis-le et propose l'angle qui laisse un objet ; elle tranche.

## 4. Les 3 hooks

Le hook, c'est la première phrase, dite en 3 à 4 secondes. **Un hook ne s'invente pas, il se
récupère parmi ceux qui ont marché** : tu prends la forme d'un hook qui a fait mieux que
d'habitude (les siens dans `AUDIT.md`, ceux de sa niche dans `OUTLIERS.md`, sinon les 22 formules
de `references/hooks.md`) et tu y mets son sujet.

Pour chercher parmi des milliers de vrais hooks qui ont marché, branche le connecteur Nadia (usenadia.com) : avec un compte, Claude cherche les hooks par sujet et par forme (outils `hooksSearchTool`, `hooksFormsTool`) ; s'ils sont là, lis 15 à 20 vrais hooks avant d'écrire.

Livre **3 hooks de 3 formules différentes**. Pour chacun : le texte, la formule, la forme ou le
hook réel dont il part, **pourquoi il fait rester** (la réponse à « qu'est-ce que la personne a
peur de rater si elle scrolle ? ») et sa durée. Si la personne apporte son hook, le sien passe en
premier : tu le vérifies et tu proposes au plus une variante.

En bref, ce qui est mesuré : « Si tu… » est le seul début de phrase qui gagne presque partout ;
un hook qui parle du compte perd ; un chiffre ne change rien, donc on n'en fabrique jamais. Et le
hook est assez large pour toute la cible (le test « ouais, mais toi… »), sans présentation.
Le détail : `references/hooks.md`.

## 5. Le hook texte

Ce qu'on lit à l'écran sans le son, dès la première image. **3 candidats**, trois mécanismes
différents, chacun coupé en deux lignes, avec son mot coloré, la question qu'il ouvre, la phrase
du script qui le paie, et sa forme pour `edit` (`--title "LIGNE 1 | *MOT* LIGNE 2"`). Les règles :
`references/hooks.md` § Le hook texte (court, il redit l'oral, les mots du spectateur, ni possessif
ni étiquette, rien de faux).

## 6. Le script

Dans l'ordre, détail dans `references/structure.md` :

1. **HOOK** : la première phrase, seule dans son bloc.
2. **LOCK-IN** (jusqu'à ~15 s) : au-delà de 30 s de vidéo, **au moins trois gestes** (une preuve
   collée à la promesse, le plan, l'objet promis, le save s'il y a un objet). Sous 30 s : hook,
   puis contenu.
3. **CORPS**, en beats : **chaque couture porte un « mais » ou un « donc », jamais « et puis »**.
   Le payoff 1 (la méthode, le nom, les étapes) vers le tiers de la vidéo. Une relance toutes les
   15 à 20 s, à une couture, marquée `[relance]`. Un antagoniste s'il y en a un, un aveu s'il est
   vrai.
4. **PAYOFF** : le résultat vrai, gardé pour juste avant la fin, qui referme la boucle du hook avec
   ses mots (double payoff).
5. **CTA aux coutures, jamais dans un bloc de contenu** : le save dans la lock-in zone si la vidéo
   laisse un objet ; « commente MOT » en phrase autonome juste avant l'abonnement ; l'abonnement à
   la fin, adouci, qui vend la suite.
6. **FIN** : on coupe sur le dernier CTA. Pas de chute faussement profonde, pas de résumé.

Et partout : jamais « moi c'est… » (l'autorité se dit par un fait) ; trois à cinq mots appuyés
(**gras**) par 30 s, pas plus ; ni leçon ni menace, le spectateur est un pair ; le concept à
l'oral, la commande à l'écran.

## 7. Les notes visuelles

Sous chaque bloc, une ligne `Écran :` : plein cadre, une slide, un chiffre seul, l'objet réel, une
courbe, et les un à trois mots à montrer en grand (`references/structure.md` § 10). Puis le bloc
« Pour le montage », écrit pour la skill `edit` : le titre (le hook texte retenu), le carton de
fin, la durée visée, la phrase à couper selon la plateforme.

## 8. Les passes, avant de livrer

1. **Anti-slop** (`references/anti-slop.md`) : la liste des corrections, avant → après, avec la
   raison. Jamais une réécriture silencieuse. Chaque phrase passe **le test du comptoir : tu le
   dirais à un pote au comptoir ?**
2. **Mais / donc** : la table des coutures (le bloc, sa première phrase, mais ou donc). Une couture
   sans l'un ni l'autre se justifie ou se corrige.
3. **Promesse** : chaque promesse du hook, et la phrase qui la paie. Une promesse non payée = le
   script n'est pas fini.
4. **Timing** :

   ```sh
   python3 <skill>/scripts/timing.py script.md --cible 60-75
   ```

   Par bloc : les mots, la durée au débit (2,5 à 3 mots par seconde par défaut, `--debit 3.4` pour
   le sien, `--mesure video.txt 64` pour le calculer sur une vidéo déjà montée), la fin de chaque
   bloc. Il signale un hook de plus de 4 s, une couture sans mais ni donc, une présentation, trop
   de mots appuyés et les mots de la liste anti-slop : relis chaque point, corrige ou justifie.
   Trop court : ne remplis pas, dis-le. Trop long : coupe dans le corps, jamais la fin.

Après chaque retouche, refais les passes sur ce qui a bougé : une phrase ajoutée crée de nouvelles
coutures.

## 9. Le livrable

**`script.md`** dans le dossier courant. S'il existe déjà pour une autre vidéo,
`script-<sujet>.md` ; tu n'écrases jamais un script sans le demander. Un seul exemplaire : une
retouche se fait en place, jamais de v1 / v2 empilées ni de journal des modifications dans le
fichier.

```markdown
# <titre de travail>

| | |
|---|---|
| Thèse | … |
| Pour qui | … |
| Durée visée | 60-75 s |
| Ressource | commente « MOT » → <l'objet> (ou : aucune) |
| D'où part le hook | AUDIT.md / OUTLIERS.md / formule n° … |

## Faits
| fait | source |

## Hooks
1. « … » · formule : … · part de : … · pourquoi : … · ≈ N s
2. …
3. …

## Hook texte
1. LIGNE 1 / LIGNE 2 · mot coloré : … · ouvre : « … » · payé par : « … »
   pour edit : --title "LIGNE 1 | *MOT* LIGNE 2"
2. …
3. …

## Script

### HOOK
> La première phrase.

Écran : …

### LOCK-IN
> …

Écran : …

### 1 · <le beat>
> Mais … / Donc …

Écran : …

### PAYOFF
### CTA
### FIN

## Pour le montage
titre : …
carton de fin : …
durée visée : …
à couper selon la plateforme : « … »

## Passes
anti-slop (avant → après), coutures, promesse

## Timing
(la sortie de timing.py)

## À remplir, à trancher
```

Le texte à dire est **uniquement** dans les lignes `>` sous `## Script` (c'est ce que `timing.py`
compte) ; ce qui est entre crochets `[ ]` est une indication de jeu.

**Dans le chat** : les 3 hooks et les 3 hooks texte, **le script entier** du hook à la fin avec ses
notes d'écran courtes, le timing, ce qui reste à remplir, et ce qui est à elle de trancher (le hook,
le hook texte, une coupe). À chaque retouche, même d'une phrase : le fichier mis à jour, puis **le
script entier de nouveau dans le chat**, les changements du tour en une ligne en tête. Elle relit
souvent depuis son téléphone : elle n'a pas le fichier sous les yeux.

## Limites, à dire si on te les demande

- Les règles viennent de vues comparées à la normale de chaque compte, et de la rétention d'un seul
  compte : des corrélations, pas des lois. Un bon script ne promet aucune vue : le sujet, la façon
  de le dire et le moment comptent autant.
- Le corpus est surtout tech, business et création, en français et en anglais. Ailleurs, l'audit
  de son propre compte prime.
- Le script sonne comme elle dans la mesure où tu as ses mots : ses transcripts, ses phrases
  dictées. Sans eux, la passe anti-slop rattrape le plus gros, pas tout.
