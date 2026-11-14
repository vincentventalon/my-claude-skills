# La structure : du hook à la dernière phrase

Un script est une chaîne : le hook ouvre une promesse, la lock-in zone donne une raison de rester,
le corps la tient beat après beat, la fin la referme. Chaque bloc a un rôle ; un bloc sans rôle
sort.

## Le plan de vol (vidéo de 60 à 75 s)

| bloc | où | rôle |
|---|---|---|
| **HOOK** | 0 à 4 s | la première phrase, et rien d'autre (hooks.md) |
| **LOCK-IN** | jusqu'à ~15 s | au moins trois gestes : pourquoi te croire, ce qui vient, ce qu'il emporte |
| **CORPS** | 2 à 4 beats | chaque couture porte un « mais » ou un « donc » ; le payoff 1 vers le tiers |
| **PAYOFF** | juste avant la fin | le résultat vrai, gardé pour la fin, qui referme la boucle du hook |
| **CTA** | aux coutures | la ressource à commenter, puis l'abonnement |
| **FIN** | dernière phrase | on coupe sur le CTA, sans chute ni résumé |

Les repères de temps sont ceux de la vidéo montée. `scripts/timing.py` les estime au débit de
parole ; les blancs coupés au montage font gagner quelques secondes.

## 1. Le hook

Voir hooks.md. Une phrase, 3 à 4 secondes. Au-delà, propose une version courte à côté et laisse
trancher : on ne coupe pas à la place de la personne.

## 2. La lock-in zone (jusqu'à ~15 s)

Le spectateur a donné trois secondes. Sa question : *« d'accord, et maintenant ? »*

**Ce qui est mesuré** : sur une vidéo de plus de 30 secondes, **trois gestes ou plus** entre la fin
du hook et le contenu font mieux qu'un seul geste ou qu'une entrée directe, dans la grande
majorité des comptes étudiés. *Quel* geste choisir ne change rien de mesurable : n'en débats pas,
empile. Sous 30 secondes, la pile ne rapporte rien : hook, puis contenu.

Les gestes :

| geste | ce que c'est | exemple |
|---|---|---|
| **preuve** | un fait qui rend la promesse croyable, collé à elle | « ça fait dix ans que je fais ça », un résultat, un chiffre vrai |
| **transformation** | l'avant et l'après que le spectateur peut atteindre | « tu passes de trois heures à dix minutes » |
| **contraste** | ce que tout le monde fait contre ce qui marche | « tout le monde le fait à la main ; un script le fait mieux » |
| **boîte magique** | un nom lâché sans l'expliquer | « ça s'appelle la règle des trois relances » |
| **insistance** | on redit la promesse plus fort | « oui, quarante lignes, pas plus » |
| **plan** | ce qui vient, compté | « trois règles, dans l'ordre » |
| **carotte** | un objet réel promis pour la fin | « et le script, je te le donne à la fin » |
| **save** | si la vidéo laisse un objet à retrouver (§ 6) | « enregistre la vidéo, les trois règles tu vas les recopier » |

À éviter dans la lock-in zone :

- **le préambule sans tension** : « alors aujourd'hui je vais te parler de… » ;
- **la présentation** : « moi c'est… ». L'autorité se dit par un fait qui porte une information,
  jamais par un nom ;
- **payer la promesse tout de suite** : si le hook tranche (un verdict, une réponse), il n'y a plus
  de raison de rester. Ouvre aussitôt une deuxième boucle, nommée, payée à la fin.

## 3. Le corps : « mais » et « donc », jamais « et puis »

Une liste d'étapes enchaînées par « et puis » ou « numéro deux : » n'a pas de moteur. **Chaque
couture entre deux beats porte un « mais » ou un « donc »** : le beat suivant naît de la limite du
précédent. **Mais** = le problème, la limite, le conflit. **Donc** = la réponse, l'étape d'après.

> Mais si ce qui est lent, c'est le calcul et pas la taille du fichier, le découper t'aide pas.
> Donc deuxième étape : …

- **À l'intérieur d'un beat aussi**, dès qu'il y a une cause ou une opposition : « Mais Excel
  charge tout en mémoire, donc ta limite, c'est ta RAM » plutôt que « Ta limite, c'est ta RAM,
  parce que… ».
- **Les mots de l'oral** : mais, donc, sauf que, alors que, du coup, résultat. Jamais « ainsi »,
  « par conséquent », « toutefois ». « Cependant », une fois par script au plus, pour la bascule
  forte. En anglais : *but*, *so*, *which means*, *except*, *that's why* ; jamais *and then*,
  *next*.
- **Le contrôle** : relis le texte couture par couture. Une couture sans « mais » ni « donc » se
  justifie ou se corrige, et la table des coutures va dans le livrable. `timing.py` signale les
  blocs qui ne s'ouvrent ni sur l'un ni sur l'autre.
- **Ça coûte** une dizaine de pour cent de mots en plus : recompte.

Ce qui donne au corps sa tension :

- **Un antagoniste**, quand l'histoire en a un. Même un concept : la relance à la main,
  l'ancienne méthode, le tableur qui plante.
- **Un aveu** : une vraie galère avant la solution. Jamais inventée, et **jamais une citation de
  tiers fabriquée** : un fait se raconte comme un fait, il ne se met pas entre guillemets si
  personne ne l'a dit.
- **Un contre-pied**, si la personne a une vraie conviction : « on te dira X, moi je pense
  l'inverse », une ou deux phrases. Pas à chaque vidéo : un contre-pied sans conviction est pire
  que plat.
- **Le concept à l'oral, la commande à l'écran** : sur une explication technique, la voix dit à
  quoi sert chaque brique et dans quel ordre elles se tiennent ; les commandes, les options et
  le code vont sur une slide. Rassurer vaut mieux qu'impressionner.
- **Des relances**, une toutes les 15 à 20 secondes, **posées à une couture** (jamais au milieu
  d'un beat) et qui démarrent sur « mais » ou « donc » : le piège (« mais y a un piège »), le
  secret, la vanne, le rappel du hook. Toujours vraies. Marque-les `[relance]` dans le script.
- **Fermer une boucle et en ouvrir une autre dans la même phrase.**
- **Peu de mots appuyés** (en **gras** dans le script) : trois à cinq par tranche de 30 secondes,
  sur les mots qui portent un payoff (un chiffre, un contraste, une chute). Une frappe à chaque
  phrase ralentit le débit et la vidéo sonne récitée.

## 4. Le double payoff

- **Payoff 1, vers le tiers de la vidéo** : la révélation principale (la méthode, le nom, les
  étapes). Pas de teasing qui traîne : celui qui reste doit être payé tôt.
- **Payoff 2, gardé pour juste avant la fin** : le résultat vérifiable, le chiffre vrai, le « et
  surtout ». C'est lui qui fait rester jusqu'au bout.
- **La boucle ouverte nommée** dans le hook ou la lock-in zone se referme avec les mêmes mots :
  « le script que je t'ai promis ».

## 5. La chaîne de promesse

1. **Une thèse par script**, écrite avant le corps. Le hook la vend, le corps la démontre, la fin
   la referme ; le hook texte et la description vendent la même. Deux thèses = un spectateur
   perdu.
2. **La passe promesse** : relis le hook comme un inconnu, liste chaque promesse (un chiffre, un
   verdict, un bénéfice) et pointe la phrase du corps qui la paie. **Une promesse sans phrase qui
   la paie = le script n'est pas fini.**
3. **La carotte** promet un objet réel (« je te donne le script », pas « je te dis par où
   commencer »), choisi avant d'écrire le corps. Elle n'est pas obligatoire : mieux vaut pas de
   carotte qu'un objet inventé.
4. **Un mot clé ne change pas de sens en route** : si « prompt » veut dire « message » au hook, il
   ne veut pas dire « fichier » au milieu.

## 6. Les CTA, aux coutures

**Jamais de CTA à l'intérieur d'un bloc de contenu** : quelqu'un qui écoute un argument n'est pas
disponible pour une demande ; l'interrompre le fait partir, et il ne revient pas. Les CTA vivent aux
coutures, et un seul renvoi à soi à la fois.

| CTA | quand | comment |
|---|---|---|
| **save** | dans la lock-in zone, **seulement si la vidéo laisse un objet** (liste, étapes numérotées, modèle, chiffres) | formulé comme un service, l'objet nommé : « enregistre la vidéo, tu vas recopier les trois règles ». Si la phrase ne peut pas nommer ce qu'on garde, la vidéo n'a pas d'objet : pas de save. Jamais sur une vidéo d'avis. |
| **commentaire** (ressource) | à la couture d'avant la fin, juste avant l'abonnement | « Commente RELANCE et je t'envoie le script. » Une phrase autonome, pour pouvoir la couper au montage sur une plateforme où personne n'enverra le lien. Le mot en majuscules, le même à l'oral, à l'écran et dans la description. |
| **abonnement** | la fin, au spectateur qui est resté | adouci (« hésite pas à t'abonner »), jamais un « abonne-toi » sec ; il vend la suite (« j'en partage d'autres comme ça »), pas la vidéo finie. |
| **like** | la fin, s'il reste une demi-seconde | coût nul, effet non prouvé : jamais au prix d'une seconde de contenu. |

Au-delà d'une minute trente, une autre structure se défend : l'abonnement à la couture de la
lock-in zone (adouci, avec la raison avant la demande) et le save à la fin. Sous une minute
quinze, garde la première : chaque seconde de la lock-in zone compte.

## 7. La fin qui tient

Le payoff 2 referme la boucle du hook, puis les CTA, puis on coupe. Pas de chute faussement
profonde (« les outils changent, la compétence reste »), pas de résumé, pas de « voilà, c'est
tout ». La dernière phrase est concrète.

## 8. Les formats qui ont marché, à prendre comme moule

Un format qui a déjà marché coûte moins cher qu'une page blanche. Ceux qui ont tenu sur 100 jours
de vidéos publiées :

- **« X en 60 secondes »** : l'annonce en toute première phrase et les mêmes mots à l'écran ; vers
  7-20 s, un problème concret avec un personnage (« tu l'envoies à un client, chez lui ça
  plante ») ; trois notions au plus, chacune répond au problème, une phrase = une slide avec le
  vrai code ou la vraie commande ; à la fin, le problème du début est résolu, et on coupe. 75 s
  au plus une fois monté.
- **« Si je devais réapprendre X aujourd'hui »** : un ordre et des noms d'outils, jamais un récit.
- **« Une seule ressource »** : un objet réel, nommé tôt ; le save suit l'objet.
- **Le guide en N étapes** : le nombre annoncé au hook, un objet par étape.
- **Ce que j'utilise vraiment** : l'inventaire chiffré (outils, prix) ; l'autorité par l'objet.

Ce qui plafonne, pour ne pas le refaire : le récit sans objet (il attache les abonnés, il ne fait
pas de portée : une fois par semaine au plus), l'avis tranché seul (rien à enregistrer), la vidéo
qui parle du compte, la motivation.

## 9. La durée

- **60 à 75 s** par défaut ; la durée de l'audit (`target_duration_s`) passe avant.
- **Plus court que la cible** : ne remplis pas. Dis-le, et laisse trancher.
- **Plus long** : coupe dans le corps, jamais la fin (le payoff 2 et les CTA). Nomme la coupe sûre
  dans le livrable.
- Sur TikTok, la rémunération des créateurs ne compte que les vidéos de plus d'une minute : si la
  personne y est éligible, vise au-dessus.

## 10. Les notes visuelles

Une ligne `Écran :` sous chaque bloc : ce qu'on voit, et les un à trois mots qui méritent d'être
montrés en grand.

| ce qu'on montre | quand |
|---|---|
| **plein cadre** (le visage) | l'aveu, l'émotion, la vanne, le CTA : ce qui passe par la tête |
| **une slide** (deux à six mots, ou une ligne de code) | une étape, une règle, une commande : une phrase = une slide |
| **un chiffre seul, en gros** | la preuve, le payoff 2 : un chiffre vrai se montre plutôt qu'il ne se dit en entier |
| **l'objet réel** (capture, fichier, terminal, mail) | quand l'objet est le sujet ; révélé ligne à ligne |
| **une courbe qui se trace** | quand le sujet a une loi (« plus X, plus Y », un coût qui monte, un délai) |

Les règles :

- **Du texte dès la première image** : le hook texte, en haut.
- **L'objet du haut pose la question que la phrase résout**, il n'illustre pas la phrase : une
  courbe qui descend pendant « plus il devient lent » pose « jusqu'où ? » ; une grille de logos
  pendant « voici huit outils » ne pose rien.
- **Rien ne montre un nom caché avant qu'il soit dit.**

En fin de script, le bloc **« Pour le montage »** est écrit pour la skill `edit` du même dépôt :
le titre du haut (le hook texte retenu, `*mot*` coloré, ` | ` retour à la ligne), le carton de fin,
la durée visée, la phrase à couper selon la plateforme. Ses valeurs se passent telles quelles
(`--title`, `--cta`) ou se disent (« monte ma vidéo, titre … »). `edit` incruste le titre, les
sous-titres et le carton de fin ; les slides, chiffres et captures sont pour qui termine le
montage.
