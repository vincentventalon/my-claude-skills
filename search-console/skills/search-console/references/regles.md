# Règles de lecture Search Console, en détail

Chaque règle se suffit à elle-même. Les chiffres entre parenthèses calibrent la règle : ce sont des
ordres de grandeur observés sur des sites réels, à recalculer sur le tien quand tu peux.

## 1. Le bruit

- **Un compte suit une loi de Poisson.** L'écart-type de n clics vaut √n. Entre deux périodes, un
  écart est réel s'il dépasse 1,96 × √(avant + après) (95 %). Calcule et affiche le seuil avant de
  conclure.
- **Petit site, page seule, requête seule : élargis.** La variance réelle dépasse Poisson
  (surdispersion mesurée entre 1,2 et 2,5). Le script prend 1,96 × √(2,5 × (avant + après)) sous
  200 clics par 28 jours, et toujours pour une page ou une requête du journal.
- **Ce que le volume permet de voir.** Pour voir un doublement, il faut une douzaine de clics par
  période au seuil de Poisson, une trentaine au seuil élargi. Ordres de grandeur sur un site à
  ~180 clics par semaine : ±20 % sur les clics du site, ±60 % sur un groupe de ~20 clics, rien sur
  une page à moins de 10 clics par semaine ; ±7 % sur les impressions du site.
- **Position par requête, semaine contre semaine : écart-type d'environ 17 places.** Détecter un
  déplacement d'une place demande plus de 1 000 requêtes stables.
- **CTR.** Voir +20 % de CTR sur un groupe à ~4 000 impressions par semaine demande environ 50 000
  impressions par période, soit des mois. Jamais à la semaine sur un petit site.
- **Beaucoup de tests, seuil plus haut.** À 5 %, tester 100 pages donne environ 5 faux positifs.
  Au-delà d'une cinquantaine de pages, exige |z| > 3. Un écart pile au bord du seuil ne compte pas.
- **« Non détectable » est un verdict.** Ne l'écris jamais comme une version prudente du verdict
  positif (« légère hausse », « tendance encourageante »).

## 2. Les périodes

- Deux périodes de même durée, mêmes jours de semaine. 28 jours contre les 28 d'avant pour le mois,
  semaine complète lundi-dimanche contre la précédente pour « il s'est passé un gros truc ? ».
- **Données finales seulement.** Les 2 à 3 derniers jours sont provisoires et remontent encore
  pendant environ 48 h. Le script s'arrête au dernier jour final.
- **Une semaine seule hors du seuil n'est pas une tendance.** Un changement de niveau, c'est deux
  semaines basses contre les deux d'avant. Pour une semaine en cours, compare les mêmes jours
  (lundi-mercredi contre lundi-mercredi).
- **La saison.** Compare aux mêmes semaines de l'an dernier seulement si l'an dernier avait du
  volume (le script exige 200 clics sur les deux fenêtres). Sinon, la saison reste une hypothèse.

## 3. Position et CTR

- **Panier fixe.** La position moyenne est pondérée par les impressions des requêtes du moment. Un
  site qui gagne des requêtes neuves (souvent mal classées) voit sa position « baisser » sans que
  rien ne bouge. Compare uniquement les requêtes présentes sur les deux périodes.
- **Le panier se sélectionne lui-même.** Une requête qui sort du classement sort du panier. Donne
  toujours la part des impressions gardée (le script l'affiche). Si elle est faible, le test ne
  voit pas ce qui disparaît.
- **La position moyenne d'une page n'est pas sa position sur sa requête principale.** Une page à
  5,9 en moyenne peut être 15e sur la requête qui compte.
- **Courbe de CTR.** Mesure la courbe du site (clics / impressions par position), n'utilise pas une
  courbe de manuel. Avec les réponses IA en haut de page, la courbe peut être plate des positions
  1 à 14, et une requête à réponse unique fait zéro clic même en position 1 ou 2.
- **« Classée mais pas cliquée ».** Clics attendus = impressions × CTR du site à cette position.
  Si les clics observés sont nettement en dessous (probabilité de Poisson très faible), lis la
  page de résultats : souvent une intention de navigation (on cherche un site officiel).

## 4. Demande ou classement

- Sur les mêmes requêtes, compare le rapport d'impressions et le déplacement de position, chacun
  avec son intervalle. Le script pondère chaque requête par l'inverse de sa variance de Poisson :
  une requête géante ne pèse pas tout, une requête à 10 impressions presque rien.
- Impressions en baisse, position stable : la demande baisse (saison, pays, actualité).
  Position qui recule (nombre plus grand) : le classement.
- Fais le test par pays et sur mobile seul. Une baisse « du site » vient souvent d'un seul pays.
- **Impressions sans humain.** Des impressions ordinateur qui montent puis s'effondrent, souvent
  hors du pays principal et sur des requêtes masquées, avec des clics stables : robots ou
  changement côté Google. Le CTR et la position du site deviennent faux. Lis les clics et le mobile.
- Pays × page et appareil × page sont tronqués par l'API (on peut ne récupérer qu'un tiers des
  clics) : lis pays et appareil au niveau du site.

## 5. Les pages

- **Le niveau page est presque complet**, contrairement au niveau requête : c'est là qu'on cherche
  ce qui bouge.
- **Les faits oui/non se lisent tout de suite** : une page qui apparaît, qui disparaît, qui est
  indexée ou non, une redirection qui répond ou non. Pas besoin de statistique.
- **Sépare le stock des pages neuves** avant de lire une tendance. Le nombre de requêtes distinctes
  est un bon signal de croissance, insensible au bruit de position.
- **Groupe témoin choisi par une règle** (toutes les pages au-dessus d'un volume), jamais à la main :
  un témoin choisi à la main est une anecdote. Pour créditer un lot de changements, compare pages
  touchées et non touchées (différence de différences). Si les non touchées montent autant, rien
  n'est prouvé.
- **Dans une seule page**, le test qui tranche sépare les requêtes visées et non visées de la même
  page et compare leurs trajectoires. Attention au retour vers la moyenne si elles partent de
  niveaux différents.

## 6. Après un changement

- **Avant de mettre en ligne**, note la référence, le plus petit écart visible, le seuil de succès
  et le déclencheur de retour en arrière (« si la requête X perd plus de N impressions par jour, je
  remets l'ancien titre »).
- **Date du journal = mise en ligne réelle.** Un commit peut rester des jours sans être déployé.
- **Fenêtre minimale** : 3 semaines, 4 pour l'accueil et les pages hub. Une page qui part de la
  position 50 ou au-delà met environ 7 semaines à remonter. À une semaine, c'est un test de fumée.
- **Lis la cible**, pas le total de la page ni du site.
- **Quatre issues** : amélioration détectable, pas de régression détectable, régression détectable
  (reviens en arrière), indécidable. « Indécidable » est fréquent et valable.
- **Un changement à la fois.** Deux changements livrés ensemble (titre + intro) ne se séparent
  plus. Dans un même groupe de pages, espace les changements de 3 semaines. Revenir en arrière et
  relire 3 semaines est le seul test de cause.
- **Recrawl.** Un changement ne peut agir qu'après le passage de Google. L'inspection d'URL donne
  la date du dernier crawl : avant, la ligne attend un recrawl.

## 7. Renommages, redirections, suppressions

- Une URL renommée coupe son historique. Le lendemain, la nouvelle URL a environ 1 % des
  impressions de l'ancienne ; l'essentiel bascule en 3 semaines ; l'ancienne disparaît d'une
  fenêtre de 28 jours en 7 semaines environ. Ce n'est pas « la nouvelle page est moins bonne ».
- Ne diagnostique pas un groupe dont les URL ont changé dans la fenêtre. N'empile aucun changement
  sur une 301 fraîche.
- Une 301 pointe directement vers la cible finale (pas de chaîne), les liens internes passent à la
  nouvelle URL, le contenu unique migre. Une page sans historique peut simplement répondre 404.
  Teste chaque règle en production (301 puis 200).
- D'anciennes URL qui gardent quelques impressions, une page en noindex encore visible : retard de
  Google, rien à faire.

## 8. Clusters, hubs et satellites

- **Chevauchement structurel et coût mesuré sont deux verdicts.** Deux pages qui partagent requêtes,
  intertitres ou FAQ : constat, prouvable. Que ça coûte des clics : rarement prouvable à petit
  volume. Corrige pour des raisons d'architecture, sans le vendre comme la cause d'une baisse.
- **Page outil contre article sur la même intention : Google en garde un.** Un article publié contre
  un outil déjà installé peut faire quelques impressions en deux semaines pendant que l'outil
  progresse.
- **Signature d'une cannibalisation** : une requête servie par plusieurs pages, la page qui prend le
  plus d'impressions étant la moins bien classée. Pour la réfuter : si les deux baissent ensemble,
  pas de transfert ; si l'une sort et que l'autre ne remonte pas, rien n'était volé.
- **Une page qui gagne sur le nom de l'autre** : c'est un problème de nom, pas de doublon. Renomme
  la perdante vers sa vraie niche, ne fusionne pas.
- **Défaire un chevauchement** (en un seul changement) : sépare l'intention dans title, H1 et meta
  description ; retire la formule exacte de la page perdante ; ne touche pas le title de la page
  qui tient la requête ; supprime les intertitres et FAQ partagés ; en créant un satellite, réduis
  la section du parent à un résumé + lien, et lie dans les deux sens. Un exemple chiffré fixe n'est
  pas un doublon d'un outil interactif.
- **Quand découper en hub + satellites** : seulement avec un gros réservoir d'impressions concentré
  sur une URL. Fixe le seuil de découpe à l'avance. Ne découpe pas des synonymes (doublons faibles)
  ni des requêtes à réponse unique. Ajoute des satellites, ne redécoupe pas le hub après coup, et
  choisis le hub par ses liens internes.
- **Juge les satellites en clics pour 1 000 impressions** : le hub prend le volume des requêtes de
  tête en positions 9 à 14, les satellites se classent haut sur des besoins précis et prennent les
  clics. Un vrai découpage se voit en jours.

## 9. Indexation et site neuf

- Indexée ou non, recrawlée ou non, canonique choisie par Google : ce sont des faits. Une page neuve
  est souvent indexée en 0 à 6 jours.
- « Explorée, actuellement non indexée » : Google l'a lue et ne la garde pas. Vérifie ses liens
  entrants dans le texte (au moins 3) et qu'elle ne double pas une autre page.
- « Détectée, actuellement non explorée » : il ne l'a pas encore lue. Rien à juger.
- Une page indexée, crawlée, bien liée, à zéro impression pendant qu'une page sœur monte : elle est
  éclipsée par la sœur, ce n'est pas un problème technique.
- Les liens de pied de page identiques partout ne comptent pas comme maillage.

## 10. Choisir quoi travailler

- **Pages à portée** : positions 4 à 20 avec au moins 300 impressions sur 28 jours. Estime le gain
  avec le CTR réel des meilleures pages du site (souvent 1,5 à 2 %), pas avec un CTR théorique.
  Sur une page limitée par sa position, changer le titre rapporte peu : le levier est le
  classement, donc les liens.
- **Plafond d'autorité** : la longue traîne monte mais les requêtes de tête ne bougent pas. Le
  plafond est l'autorité du site, pas le contenu : ne réécris pas.
- **Une piste à moins d'une dizaine d'impressions est du bruit.** Retire les requêtes de marque
  d'autres sociétés. Recharge les chiffres avant d'agir : les réservoirs bougent vite.
- **Search Console est aveugle là où tu n'as pas de page.** Pour un sujet absent, prends une source
  de volume externe.
- **Contenu saisonnier** : publie 1 à 2 mois avant le pic.
