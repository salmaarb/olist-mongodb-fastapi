# Réponses aux questions du brief
---

## 1. Comment représenter les différentes entités et relations dans MongoDB ?

On a choisi **4 collections** plutôt que de recopier les 9 fichiers CSV un pour un :

- `orders`  la commande, avec ses articles, paiements et avis **embarqués** à l'intérieur du même document
- `products`  le catalogue produit, en collection séparée
- `sellers` le catalogue vendeurs, en collection séparée
- `customers`  une entrée par **personne réelle** (`customer_unique_id`), avec un compteur de commandes

Les relations entre `orders` et `products`/`sellers` sont représentées par **référence** (on stocke juste `product_id` / `seller_id` dans la commande), pas par jointure  MongoDB n'a pas de jointure native comparable au SQL.

## 2. Quelles données doivent être embarquées dans un même document et lesquelles doivent rester séparées ?

La règle qu'on a appliquée, avec des chiffres à l'appui :

- **On embarque** quand la donnée est petite, bornée, et n'a de sens qu'avec son document parent. Exemple : les articles d'une commande (`items`) on a vérifié qu'il y en a toujours entre 1 et 12, jamais plus, sur les 99 441 commandes. Pareil pour les paiements (1 à 29) et l'avis (0 ou 1 dans la quasi-totalité des cas).
- **On référence** quand l'entité est réutilisée par de nombreux documents différents. Exemple : un produit est acheté en moyenne dans ~3,4 commandes différentes, un vendeur dans ~36. Les embarquer aurait dupliqué leurs informations des dizaines de fois, et rendu toute correction (ex: une catégorie mal renseignée) très difficile à répercuter partout.

## 3. Comment gérer les incohérences, valeurs manquantes et formats de données ?

Trois niveaux de traitement, tous documentés dans `nettoyage_donnees.md` :

- **Valeurs manquantes (`NaN`)** : converties systématiquement en `null` à l'import, jamais supprimées ni remplacées par une valeur arbitraire.
- **Bug de format trouvé et corrigé** : les codes postaux brésiliens commencent parfois par un zéro (`09790`). Lus sans précaution, pandas les interprète comme des nombres et supprime ce zéro ça concernait 24 % des clients et 33 % des vendeurs avant correction. On force maintenant la lecture en texte (`dtype=str`).
- **Incohérences ponctuelles documentées plutôt que corrigées à l'aveugle** : par exemple, des paiements à 0 € qui correspondent en réalité à des commandes annulées (donc légitimes), ou des `review_id` partagés entre deux commandes différentes (particularité connue du dataset, sans impact sur notre modèle puisqu'on indexe par `order_id`).
- On a aussi **vérifié l'intégrité référentielle** (aucun produit, vendeur ou client orphelin trouvé) plutôt que de la supposer.

## 4. Quels usages de consultation ou d'analyse l'API doit-elle permettre ?

L'API couvre plusieurs types d'usages :

- **Consultation unitaire** : détail d'une commande, d'un produit, d'un vendeur, d'un client (`GET /orders/{id}`, etc.)
- **Consultation filtrée et paginée** : liste des commandes par ville/statut, produits par catégorie, clients par nombre de commandes (fidélité)
- **Analyse agrégée** : chiffre d'affaires total par état (`/stats/revenue-by-state`), note moyenne des avis par catégorie de produit (`/stats/reviews-by-category`, avec un `$lookup` entre `orders` et `products`)

## 5. Comment éviter des requêtes trop coûteuses ou des réponses trop volumineuses ?

- **Pagination obligatoire** sur toutes les listes (`skip` / `limit`), avec un `limit` **plafonné à 100**  impossible de demander toute la collection d'un coup.
- **Filtres ciblés** plutôt que de tout renvoyer puis filtrer côté client (le filtre est appliqué directement dans la requête MongoDB).
- **Index sur les champs filtrés** (voir question 6), pour que le filtrage lui-même reste rapide même sur 99 441 documents.
- **Résultats agrégés déjà calculés côté serveur** (ex: moyenne, somme) plutôt que de renvoyer les données brutes et laisser le client calculer.

## 6. Quels index sont pertinents et comment démontrer leur intérêt ?

Index créés : `customer.city`, `status`, `items.product_id`, `category_name_english` (products), `city` (sellers), `orders_count` (customers)  tous choisis parce qu'ils correspondent à un filtre réellement exposé par l'API.

**Démonstration chiffrée** sur la requête `db.orders.find({"items.product_id": "..."})` (trouver les commandes contenant un produit donné) :

| | Sans index | Avec index |
|---|---|---|
| Plan d'exécution | `COLLSCAN` | `IXSCAN` → `FETCH` |
| Documents examinés | 99 441 | 5 |
| Temps d'exécution | 122 ms | 6 ms |

C'est une requête très **sélective** (un produit n'apparaît en moyenne que dans ~3,4 commandes), donc l'index change radicalement la stratégie d'exécution  c'est justement le genre de cas où un index apporte un vrai gain, contrairement à un filtre peu sélectif où l'index n'aiderait presque pas.

## 7. Comment rendre le service compréhensible et réutilisable par un autre développeur ?

- **Documentation Swagger/OpenAPI générée automatiquement par FastAPI** (`/docs`), sans effort supplémentaire de notre part
- **README complet** : installation, lancement, architecture, exemples, structure du dépôt
- **Erreurs HTTP cohérentes** (404 explicite, 422 avec le détail du paramètre invalide) plutôt que des erreurs Python brutes
- **Tests automatisés** qui documentent, en creux, le comportement attendu de chaque route
- **Modélisation et nettoyage des données documentés séparément** (`analyse_donnees_et_modelisation.md`, `nettoyage_donnees.md`), pour qu'un autre développeur comprenne le *pourquoi* des choix, pas seulement le *quoi*
