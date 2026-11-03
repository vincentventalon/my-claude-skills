# La passe anti-slop : un texte qui se dit, pas un texte qui se lit

Le script sera **dit face caméra**. Le juge n'est pas « est-ce bien écrit ? » mais :

> **Le test du comptoir : tu le dirais à un pote au comptoir ?** Si non, réécris jusqu'à ce que oui.

Principe : édition minimale. Tu corriges les tics, tu ne réécris pas la voix. Un passage qui sonne
déjà oral ressort presque identique. Ce qui fait foi avant toute règle de ce fichier : **les vrais
transcripts de la personne** (les `<nom>.txt` que la skill `edit` écrit à côté de chaque vidéo
montée, ou ce qu'elle t'a dicté). Un mot que tu ajoutes et qu'elle ne dit jamais est un mot importé :
remplace-le par le sien, pas par un synonyme « qui fait oral ».

Livrable de la passe : la liste des corrections (avant → après, et la section de ce fichier qui la
justifie). Jamais une réécriture silencieuse : la personne doit voir ce qui a bougé.

## En français

### 1. Le registre écrit qui fuit dans l'oral

Le tic n°1 de l'IA en français. Personne ne dit ça face caméra :

| écrit | oral |
|---|---|
| afin de, ainsi que, de plus, par ailleurs, néanmoins, toutefois | pour, et, en plus, mais |
| il s'agit de, cela signifie que | c'est, ça veut dire que |
| premièrement, deuxièmement, en conclusion | un, deux, dernière chose |
| « Comment fonctionne-t-il ? » (inversion) | « Ça marche comment ? » |
| la montée en compétence, l'acquisition de | monter en compétence, apprendre |
| le développement web | le dev web |

Symptôme général : un groupe nominal abstrait là où l'oral met un verbe.

### 2. Les élisions : la cohérence, pas la règle

L'oral mange le « ne » et élide : « c'est pas », « t'as », « y a ». L'IA garde les négations
complètes. Suis l'usage de la personne et reste cohérent dans un même bloc : pas de « tu n'as pas
besoin » trois lignes avant un « t'as rien à faire ». Le « ne » complet reste possible sur une
phrase solennelle, pour le contraste, jamais par défaut.

### 3. Les dislocations : la marque de l'oral, à garder

« Le cloud, c'est… », « Ton code, il tourne… », « Et ça, ça porte un nom. » La dislocation est la
signature de l'oral français. L'IA écrit « Le cloud est… ». Une passe qui retire les dislocations
détruit le script ; ajoutes-en là où une phrase sonne écrite.

### 4. Les tournures héritées de l'anglais

- **Le faux parallèle** : « Ce n'est pas juste X, c'est Y. » → dis la chose directement.
- **La question qui se répond toute seule** : « Le résultat ? Un carton. » → « Ça a cartonné. »
  Une vraie question de transition (« tu choisis lequel ? ») passe, une fois.
- **Les fragments empilés** : « Pas de diplôme. Pas d'excuse. Juste toi. » → une vraie phrase.
- **La chute faussement profonde** : « Les outils changent, la compétence reste. » → finis sur du
  concret.
- **La règle de trois** mécanique sur de l'abstrait. Trois actions concrètes (« héberger un site,
  lancer une base, faire tourner un script »), c'est de l'oral normal.
- **Le raclement de gorge** en début de bloc : « Alors voilà le truc », « Laisse-moi te dire »,
  « Honnêtement ? » → entre directement dans le fait.
- **Le tiret cadratin** (—) : à l'oral, il n'existe pas. Une virgule, un point, ou deux phrases.
- **Les connecteurs d'écrit** entre deux beats : « ainsi », « par conséquent », « toutefois ».
  À l'oral : mais, donc, sauf que, du coup, résultat (structure.md § 3).

### 5. Les mots d'IA en français

Remplacement : le fait brut, un chiffre vrai, un nom, ou rien. `scripts/timing.py` cherche ces
mots dans le texte à dire et les signale : chaque signalement se relit, il n'est pas une faute
(« l'essentiel », dans « l'essentiel de Git en une minute », passe très bien).

```slop
afin de
ainsi que
par ailleurs
néanmoins
toutefois
par conséquent
il s'agit de
cela signifie
premièrement
deuxièmement
en conclusion
en somme
in fine
force est de constater
il est important de noter
crucial
cruciale
essentiel
essentielle
incontournable
véritable
révolutionner
révolutionnaire
optimiser
exploiter
levier
écosystème
paysage
s'inscrit dans
témoigne de
souligne
met en lumière
plonger dans
plongeons
sans plus attendre
découvrir
n'hésite pas à       # « hésite pas à t'abonner », sans le « n' », est la forme orale qui reste
booster
fascinant
captivant
au cœur de
à l'ère de
dans un monde où
redoutable
puissant
```

### 6. Les codes de l'oral, à disposition

Ce qui revient le plus chez les créateurs qui parlent bien face caméra : du vocabulaire disponible,
pas un quota. À saupoudrer là où un passage sonne écrit, dans la voix de la personne.

- **« en gros »** : le simplificateur ; une explication s'ouvre ou se ferme avec.
- **« c'est-à-dire »** : la vulgarisation s'articule avec ça, pas avec « en d'autres termes ».
- **« de A à Z »** : la promesse totale.
- **« tout simplement »** : la chute qui désacralise (« c'est tout simplement un fichier »).
- **« bref », « tu vois », « alors là », « franchement », « regarde »** : les relances qui tiennent
  le face-à-face.
- **La redite après un chiffre fort** : « oui, tu m'as bien entendu ».
- **Les anglicismes du métier** assumés : free tier, SaaS, framework. Jamais de traduction forcée
  (« informatique en nuage »).
- **Le tutoiement** partout. Zéro « chers abonnés ».

## En anglais

### Written English that leaks into speech

| written | spoken |
|---|---|
| do not, it is, you are | don't, it's, you're |
| utilize, in order to, prior to | use, to, before |
| furthermore, moreover, additionally | and, also, plus |
| in conclusion, ultimately | last thing, so |
| one must consider | think about |

### Shapes to hunt

- "It's not just X, it's Y." → say Y.
- "The result? A disaster." → "It was a disaster."
- "No degree. No network. Just grit." → one real sentence.
- A wise-sounding closer ("Tools change, skills stay.") → end on something concrete.
- Throat-clearing openers: "Here's the thing", "Let me explain", "So, basically" → start with the fact.
- The em dash, triads of abstractions, "whether you're a beginner or a pro".

### AI words in English

```slop
delve
dive into
let's dive in
pivotal
landscape
tapestry
testament
leverage
seamless
seamlessly
robust
game-changer
game changer
unlock
unleash
elevate
empower
navigate
foster
realm
in today's fast-paced world
in today's world
it's important to note
it's worth noting
furthermore
moreover
additionally
in conclusion
buckle up
here's the thing
secret sauce
supercharge
revolutionize
cutting-edge
harness
embark
synergy
holistic
vibrant
meticulous
look no further
without further ado
```

Spoken codes that work in English: "basically", "step by step", "start to finish", "look",
"here's how", "you know what I mean", contractions everywhere, "you" everywhere.

## Les deux tests de sortie

1. **Le test du comptoir** : lis chaque bloc à voix haute. Chaque phrase que tu n'imagines pas
   sortir de la bouche de la personne devant un pote → réécris.
2. **Le test de portabilité** : une phrase qui marcherait telle quelle dans n'importe quelle vidéo
   (« c'est une opportunité incroyable ») est du remplissage → remplace-la par un fait, un chiffre
   vrai, un nom, ou coupe-la.

Toute retouche après la passe repasse la passe : un mot ajouté en v2 n'a pas été criblé.
