# Exemple : la skill jouée de bout en bout

Le sujet de test : « j'ai automatisé mes relances clients avec un script Python ». La personne et
ses chiffres sont fictifs ; tout le reste est ce que la skill fait, dans l'ordre. Le script tient en
61 à 73 s et passe sa propre passe anti-slop.

## La demande

> j'ai automatisé mes relances clients avec un script Python, écris-moi le script de la vidéo

## Ce que la skill demande, en un message

Pas d'`AUDIT.md` ni d'`OUTLIERS.md` dans le dossier : je pars des formules. (La skill `audit` te
donne ce qui marche sur ton compte, `outliers` dans ta niche.) Quatre questions :

1. Raconte-moi ce qui s'est passé, avec les vrais chiffres.
2. Pour qui, cette vidéo ?
3. Quelle durée ? (60 à 75 s par défaut)
4. Tu donnes le script ? Si oui, quel mot à commenter ?

## Ce que la personne répond

> Pour les freelances et les indépendants qui facturent eux-mêmes. 60-75 s, oui. Je donne le
> script, mot RELANCE. Une facture de 1 200 € m'a été payée avec deux mois de retard : le client
> avait juste oublié, et moi j'osais pas relancer. J'ai écrit un script Python d'une quarantaine
> de lignes qui tourne chaque matin : il lit mon tableau de factures, envoie un mail sympa à J+3,
> un plus ferme à J+10, et à J+20 il me prévient pour que j'appelle. Au début il a relancé un
> client qui avait déjà payé, donc maintenant il vérifie d'abord les virements. En trois mois,
> toutes mes factures ont été payées et j'ai écrit zéro relance.

## Le `script.md` livré

````markdown
# Relancer ses clients avec un script

| | |
|---|---|
| Thèse | Une relance, c'est une règle : écrite une fois, un script la tient à ta place, sans oublier et sans gêne. |
| Pour qui | les freelances et les indépendants qui facturent eux-mêmes |
| Durée visée | 60-75 s |
| Ressource | commente « RELANCE » → le script Python |
| D'où part le hook | les formules (ni audit ni outliers dans le dossier) |

## Faits

| fait | source |
|---|---|
| une facture de 1 200 € payée avec deux mois de retard | dit |
| le client avait juste oublié ; « j'osais pas relancer » | dit |
| un script Python d'une quarantaine de lignes, lancé chaque matin | dit |
| il lit le tableau des factures et leurs échéances | dit |
| J+3 : mail sympa ; J+10 : mail plus ferme ; J+20 : il prévient pour appeler | dit |
| au début, il a relancé un client qui avait déjà payé ; depuis, il vérifie les virements | dit |
| en trois mois, toutes les factures payées, aucune relance écrite à la main | dit |

## Hooks

1. **« Si tu relances encore tes clients à la main, arrête. »** · formule 1, Si tu… (avec
   l'injonction de la 4) · pourquoi : il vise exactement celui qui le fait, et « arrête » ouvre
   aussitôt « et je fais comment ? » ; « Si tu… » est le début de phrase le plus solide mesuré ·
   10 mots ≈ 3-4 s · celui que je tournerais
2. « Je te donne le script qui relance mes clients à ma place. » · formule 3, Je te donne… ·
   pourquoi : il repart avec un objet ; mais l'objet est donné d'entrée, et la carotte de la fin
   disparaît · 12 mots ≈ 4-5 s
3. « Ton client te doit 1 200 euros, et t'oses pas le relancer. » · formule 15, le problème en
   scène · pourquoi : la gêne est la sienne, le montant est un enjeu pour lui ; mais il ne parle
   qu'à ceux qui ont une facture en retard aujourd'hui · 12 mots ≈ 4-5 s

## Hook texte

1. TU RELANCES ENCORE / À LA MAIN ? · mot coloré : MAIN · ouvre : « il y a un autre moyen ? » ·
   payé par : « Un script de quarante lignes le fait pour toi. » · redit l'oral
   pour edit : --title "TU RELANCES ENCORE | À LA *MAIN* ?"
2. 40 LIGNES / QUI RELANCENT POUR TOI · mot coloré : RELANCENT · ouvre : « quarante lignes, ça
   suffit ? » · payé par : les trois règles
   pour edit : --title "40 LIGNES | QUI *RELANCENT* POUR TOI"
3. COMMENT RELANCER / SANS ÊTRE LOURD ? · mot coloré : LOURD · ouvre : la question qu'il se pose
   déjà · payé par : « Trois jours après l'échéance, il envoie un petit mail sympa. »
   pour edit : --title "COMMENT RELANCER | SANS ÊTRE *LOURD* ?"

## Script

### HOOK
> Si tu relances encore tes clients à la main, arrête.

Écran : plein cadre ; le hook texte en haut dès la première image.

### LOCK-IN
> Un script de quarante lignes le fait pour toi, et lui, il oublie jamais.
> Moi, j'ai attendu deux mois une facture de **1 200 euros**.
> Je te montre ses trois règles, et le script, je te le donne à la fin.

Écran : sur « quarante lignes », le fichier du script qui défile ; sur « 1 200 euros », le chiffre
seul, en gros : **1 200 € · 2 MOIS** ; sur « trois règles », une slide à trois lignes vides.
Gestes : contraste (« lui, il oublie jamais »), preuve (la facture), plan et objet promis.

### 1 · Le problème
> Mais le client, il était pas de mauvaise foi : il avait juste oublié. Et moi, j'osais pas relancer.

Écran : plein cadre, l'aveu passe par le visage. Antagoniste : la relance à la main.

### 2 · Les trois règles
> Donc c'est le script qui relance. Chaque matin, il ouvre mon tableau de factures et il regarde les dates.
> Trois jours après l'échéance, il envoie un petit mail sympa.
> À dix jours, un mail plus ferme.
> Et à vingt jours, c'est moi qu'il prévient, parce que là, faut décrocher le téléphone.

Écran : la slide se remplit, une ligne par phrase : **J+3 · mail sympa**, **J+10 · plus ferme**,
**J+20 · tu appelles**. Payoff 1, vers le tiers de la vidéo.

### 3 · Le piège
> [relance] Mais y a un piège.
> Au début, il a relancé un client qui avait déjà payé. La honte.
> Donc maintenant, avant d'écrire, il regarde si l'argent est arrivé.

Écran : plein cadre sur « la honte » ; puis une slide : **L'ARGENT EST ARRIVÉ ?**

### PAYOFF
> Résultat : en trois mois, toutes mes factures ont été payées, et j'ai pas écrit une seule relance.

Écran : le chiffre seul : **3 MOIS · 0 RELANCE ÉCRITE**. Payoff 2, gardé pour la fin.

### CTA
> Le script, commente **RELANCE** et je te l'envoie.

Écran : le mot **RELANCE**, en grand.

### FIN
> Et hésite pas à t'abonner, j'en partage d'autres comme ça.

Écran : le carton de fin.

## Pour le montage

```text
titre : TU RELANCES ENCORE | À LA *MAIN* ?
carton de fin : Abonne-toi pour d'autres scripts
durée visée : 60-75 s
à couper selon la plateforme : « Le script, commente RELANCE et je te l'envoie. »
  (là où personne n'enverra le lien en message)
```

Pour `edit` : `--title "TU RELANCES ENCORE | À LA *MAIN* ?" --cta "Abonne-toi pour d'autres scripts"`

## Passes

Anti-slop, premier jet → livré :

| avant | après | pourquoi |
|---|---|---|
| « une facture de 1 200 euros m'a été payée avec deux mois de retard » | « j'ai attendu deux mois une facture de 1 200 euros » | le passif, c'est de l'écrit (§ 1) ; la lock-in raccourcit d'autant |
| « Mais le client était pas de mauvaise foi » | « Mais le client, il était pas de mauvaise foi » | la dislocation, la marque de l'oral (§ 3) |
| « il vérifie les virements reçus » | « il regarde si l'argent est arrivé » | un groupe nominal là où l'oral met un verbe (§ 1) |
| « Donc maintenant, c'est le script qui relance » | « Donc c'est le script qui relance » | deux « donc maintenant » en vingt secondes |
| « Je te montre les trois règles qu'il suit » | « Je te montre ses trois règles » | trois mots de moins, même sens |

Test du comptoir : chaque phrase passe ; « faut décrocher le téléphone » et « la honte » restent
telles quelles. `timing.py` : aucun mot de la liste.

Coutures :

| bloc | s'ouvre sur | |
|---|---|---|
| 1 · Le problème | « Mais le client, il était pas de mauvaise foi » | mais |
| 2 · Les trois règles | « Donc c'est le script qui relance » | donc |
| 3 · Le piège | « Mais y a un piège » | mais, et c'est la relance |
| dans le 3 | « Donc maintenant, avant d'écrire… » | donc |
| PAYOFF | « Résultat : … » | résultat |

Promesse :

| promesse du hook et de la lock-in | payée par |
|---|---|
| « arrête » (de relancer à la main) | « Donc c'est le script qui relance. » |
| « quarante lignes… il oublie jamais » | « Chaque matin, il ouvre mon tableau de factures » ; « j'ai pas écrit une seule relance » |
| « ses trois règles » | J+3, J+10, J+20 |
| « le script, je te le donne à la fin » | « Le script, commente RELANCE et je te l'envoie. » |

CTA : pas de save dans la lock-in. Elle a déjà ses trois gestes, et l'objet part par le
commentaire : un seul renvoi à soi à la fois. À tester sur une prochaine vidéo : « enregistre-la,
les trois règles tu vas les recopier » (+7 mots).

## Timing

```text
débit : 2.5-3 mots/s
bloc                  mots     durée  fin vers
HOOK                    10     3-4 s  0:03-0:04
LOCK-IN                 41   14-16 s  0:17-0:20
1 · Le problème         18     6-7 s  0:23-0:28
2 · Les trois règles    51   17-20 s  0:40-0:48
3 · Le piège            28    9-11 s  0:49-0:59
PAYOFF                  17     6-7 s  0:55-1:06
CTA                      8       3 s  0:58-1:09
FIN                     10     3-4 s  1:01-1:13
TOTAL                  183   61-73 s
dans la cible (60-75 s)

rien à relire
```

La lock-in finit vers 17-20 s au débit naturel ; les blancs coupés au montage la ramènent vers
15 s. Coupe sûre si c'est trop long : le bloc 3 entier (−28 mots, une dizaine de secondes) ; la
vidéo tient sans lui mais perd sa relance. Jamais la fin.

## À remplir, à trancher

- Rien à remplir : chaque chiffre vient de ce que tu as dit.
- À toi : le hook (1, 2 ou 3), le hook texte, le save dans la lock-in.
- Le script envoyé à ceux qui commentent RELANCE doit exister avant le tournage.
````

## Ce qui revient dans le chat

Les 3 hooks et les 3 hooks texte, le script entier (du hook au carton de fin, avec ses lignes
`Écran`), le timing (« 183 mots, 61 à 73 s, dans la cible »), et ce qui reste à trancher. À la
première retouche (« remplace la honte par autre chose »), le fichier change en place et le script
entier revient dans le chat, avec en tête : « changé : la fin du bloc 3 ; coutures et anti-slop
repassés ».
