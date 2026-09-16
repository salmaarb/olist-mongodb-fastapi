# Olist : MongoDB & FastAPI

Projet Data Engineering : modélisation, import et exposition via API REST des données e-commerce Olist (dataset public brésilien, ~99 441 commandes, 2016-2018).

## Sommaire

- [Architecture](#architecture)
- [Modélisation MongoDB](#modélisation-mongodb)
- [Installation](#installation)
- [Import des données](#import-des-données)
- [Lancer l'API](#lancer-lapi)
- [Endpoints disponibles](#endpoints-disponibles)
- [Performance : index et explain()](#performance--index-et-explain)
- [Nettoyage des données](#nettoyage-des-données)
- [Tester l'API](#tester-lapi)
- [Structure du dépôt](#structure-du-dépôt)
- [Auteurs](#auteurs)

---

## Architecture

```
                 ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
   CSV Olist ──► │ import_data_ │  ───►  │   MongoDB    │  ◄───  │   main.py    │ ◄── Client HTTP
   (8 fichiers)  │  simple.py   │        │  (4 collect.)│        │  (FastAPI)   │     (navigateur,
                 └──────────────┘        └──────────────┘        └──────────────┘      Postman, ...)
```

Le parcours d'une requête, du client à la réponse :

1. Le client appelle une route (ex: `GET /orders/{id}`).
2. FastAPI reçoit la requête et valide les paramètres reçus (types, bornes).
3. Le code interroge MongoDB (`find_one`, `find`, ou `aggregate` pour les statistiques).
4. MongoDB renvoie un ou plusieurs documents.
5. FastAPI les convertit automatiquement en JSON et répond au client, avec un code HTTP cohérent (200, 404, 422...) dans tous les cas.

**Pourquoi passer par une API plutôt que donner un accès direct à MongoDB :** sécurité (pas d'accès brut à la base), contrôle de ce qui est exposé, validation des entrées, et simplicité pour un développeur tiers qui n'a pas besoin de connaître MongoDB pour utiliser le service.

---

## Modélisation MongoDB

La structure relationnelle d'origine (9 fichiers CSV) n'a **pas** été reproduite telle quelle. Le modèle repose sur 4 collections, décidées après analyse des données :

| Collection | Contenu | Décision |
|---|---|---|
| `orders` | Commande + **items[] embarqués** + **payments[] embarqués** + **review embarquée** | Embedding : listes petites et bornées (1 à 12 articles, 1 à 29 paiements), review quasi toujours unique — et toujours consultés avec la commande |
| `products` | Catalogue produit | Référencé (`product_id`) : un produit est réutilisé dans ~3,4 commandes en moyenne, l'embarquer le dupliquerait partout |
| `sellers` | Catalogue vendeurs | Référencé (`seller_id`) : réutilisé dans ~36 commandes en moyenne |
| `customers` | Une entrée par **personne réelle** (`customer_unique_id`), avec compteur de commandes | `customer_id` est généré une fois par commande dans Olist — il ne suffit pas pour repérer un client fidèle |

Exemple de document `orders` :

```json
{
  "_id": "e481f51cbdc54678b7cc49136f2d6af7",
  "customer": { "customer_unique_id": "...", "city": "franca", "state": "SP" },
  "status": "delivered",
  "items": [{ "product_id": "...", "seller_id": "...", "price": 58.9, "freight_value": 13.29 }],
  "payments": [{ "type": "credit_card", "installments": 3, "value": 72.19 }],
  "review": { "score": 4, "comment_message": null }
}
```

Le détail des vérifications ayant mené à ce modèle (cardinalités, ratios de réutilisation...) est dans `analyse_donnees_et_modelisation.md` et le notebook `olist_analyse_modelisation.ipynb`.

---

## Installation

Prérequis : Python 3.10+, une instance MongoDB accessible en local (`mongodb://localhost:27017`).

```bash
git clone <url-du-depot>
cd olist-mongodb-fastapi

python -m venv venv
source venv/bin/activate        # ou venv\Scripts\activate sous Windows

pip install -r requirements.txt
```

Pas de fichier `.env` dans cette version : la configuration (adresse MongoDB, nom de la base, dossier des données) se modifie directement en haut de chaque script (`import_data_simple.py` et `main.py`), dans une section clairement indiquée `# CONFIGURATION`.

---

## Import des données

1. Télécharger le dataset [Brazilian E-Commerce Public Dataset by Olist (Kaggle)](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).
2. Extraire les CSV dans un dossier `data/` à la racine du projet.
3. Lancer l'import :

```bash
python import_data_simple.py
```

Le script :
- lit les 8 fichiers CSV utilisés (customers, orders, order_items, order_payments, order_reviews, products, sellers, product_category_name_translation) ;
- construit les 4 collections (`orders`, `products`, `sellers`, `customers`) ;
- **vide puis reconstruit** chaque collection à chaque exécution (`delete_many` + `insert_many`) — relancer le script donne toujours un résultat propre, sans jamais dupliquer de données ;
- crée les index nécessaires (voir section performance).

Ça prend quelques minutes (le script est volontairement écrit de façon simple et lisible plutôt qu'optimisé pour la vitesse).

---

## Lancer l'API

```bash
uvicorn main:app --reload
```

- Documentation interactive (Swagger) : http://localhost:8000/docs
- Documentation alternative (ReDoc) : http://localhost:8000/redoc

---

## Endpoints disponibles

| Méthode | Route | Description |
|---|---|---|
| GET | `/` | Vérifie que l'API répond |
| GET | `/orders/{order_id}` | Détail complet d'une commande (items, paiements, avis) |
| GET | `/orders` | Liste paginée, filtrable par `city`, `status` |
| GET | `/products/{product_id}` | Fiche produit |
| GET | `/products` | Liste paginée, filtrable par `category` |
| GET | `/sellers/{seller_id}` | Fiche vendeur |
| GET | `/sellers` | Liste paginée, filtrable par `city` |
| GET | `/customers/{customer_unique_id}` | Fiche client (personne réelle) |
| GET | `/customers` | Liste paginée, filtrable par `min_orders` (clients fidèles) |
| GET | `/stats/revenue-by-state` | **Agrégation** — chiffre d'affaires total par état |
| GET | `/stats/reviews-by-category` | **Agrégation** — note moyenne des avis par catégorie de produit (`$lookup` orders ↔ products) |

Toutes les listes sont **paginées** (`skip`, `limit`, `limit` plafonné à 100) pour éviter des réponses trop volumineuses. Un paramètre invalide (ex: `limit=500`) renvoie un `422`. Une ressource introuvable renvoie un `404` explicite.

---

## Performance : index et explain()

**Requête analysée :** `db.orders.find({"items.product_id": "<id>"})` — retrouver toutes les commandes contenant un produit donné (usage réel : suivi des ventes d'un produit pour un vendeur).

Cette requête est très sélective : un produit n'apparaît en moyenne que dans ~3,4 commandes sur 99 441, ce qui en fait un bon candidat pour démontrer l'intérêt d'un index.

| Métrique | Sans index | Avec index sur items.product_id |
|---|---|---|
| Plan d'exécution | COLLSCAN | IXSCAN → FETCH |
| Documents examinés | 99 441 | 5 |
| Temps d'exécution | 122 ms | 6 ms |

➡️ L'index divise le nombre de documents scannés par ~19 888 et le temps d'exécution par ~20.

Analyse reproductible via :
```bash
python analyze_performance_simple.py
```

Autres index créés par `import_data_simple.py` : `customer.city`, `status`, `items.product_id`, `category_name_english` (products), `city` (sellers), `orders_count` (customers).

---

## Nettoyage des données

Voir `nettoyage_donnees.md` pour le détail complet. En résumé :

| Problème trouvé | Décision |
|---|---|
| Codes postaux : le zéro initial était perdu à la lecture (24 % des clients, 33 % des vendeurs) | Colonnes lues en texte (dtype=str) plutôt qu'en nombre |
| Poids produit à 0g (4 cas) | Traité comme valeur manquante (null) |
| payment_installments = 0 (2 cas) | Plafonné à un minimum de 1 |
| review_id dupliqué entre commandes différentes (789 cas) | Particularité connue du dataset, sans impact car on indexe par order_id |
| Intégrité référentielle (produits/vendeurs/clients orphelins) | Vérifiée : aucun problème trouvé |

---

## Tester l'API

Pas de framework de test complexe : un script simple qui envoie de vraies requêtes HTTP à l'API en cours d'exécution.

```bash
# Terminal 1 : l'API doit tourner
uvicorn main:app --reload

# Terminal 2 : lancer les vérifications
python tester_api.py
```

Le script vérifie, entre autres :
- qu'une commande existante répond 200 et contient bien ses articles ;
- qu'une commande inexistante répond 404 ;
- qu'une pagination avec une limite trop grande est refusée (422) ;
- qu'un filtre par ville renvoie des résultats cohérents ;
- que l'endpoint agrégé revenue-by-state répond avec des données.

---

## Structure du dépôt

```
.
├── main.py                              # API FastAPI (un seul fichier)
├── tester_api.py                        # tests manuels de l'API (sans pytest)
├── import_data_simple.py                # import CSV -> MongoDB
├── analyze_performance_simple.py        # analyse explain() avant/après index
├── analyse_donnees_et_modelisation.md    # analyse des données + justification du modèle
├── nettoyage_donnees.md                 # incohérences trouvées et règles de nettoyage appliquées
├── olist_analyse_modelisation.ipynb      # notebook reproduisant l'analyse
├── requirements.txt
└── README.md
```

---

## Auteurs

- [Nom Prénom 1] — [rôle / partie principale du projet]
- [Nom Prénom 2] — [rôle / partie principale du projet]

*(à compléter — le brief demande des contributions identifiables des deux membres du binôme dans l'historique Git)*
