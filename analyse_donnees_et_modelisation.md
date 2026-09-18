# Analyse des données Olist & Modélisation MongoDB

## 1. Fichiers utilisés

| Fichier | Lignes | Clé primaire |
|---|---|---|
| `olist_orders_dataset.csv` | 99 441 | `order_id` |
| `olist_customers_dataset.csv` | 99 441 | `customer_id` |
| `olist_order_items_dataset.csv` | 112 650 | `order_id` + `order_item_id` |
| `olist_order_payments_dataset.csv` | 103 886 | `order_id` + `payment_sequential` |
| `olist_order_reviews_dataset.csv` | 104 719 | `review_id` |
| `olist_products_dataset.csv` | 32 951 | `product_id` |
| `olist_sellers_dataset.csv` | 3 095 | `seller_id` |
| `product_category_name_translation.csv` | 71 | `product_category_name` |

`olist_geolocation_dataset.csv` (61 Mo, données de coordonnées GPS par code postal) a été volontairement écarté : aucun usage identifié ne le nécessite, et il n'apporte rien à la modélisation métier demandée.

Cela couvre 8 des 9 fichiers du dataset, largement au-dessus du minimum de 5 fichiers liés exigé par le brief.

---

## 2. Tests et vérifications effectués

Toutes les vérifications ci-dessous ont été faites avec `pandas` directement sur les CSV fournis, avant toute décision de modélisation.

### 2.1 Cardinalité items / commande

```python
items.groupby('order_id').size().value_counts()
```

| Nb d'articles | Nb de commandes |
|---|---|
| 1 | 88 863 |
| 2 | 7 516 |
| 3 | 1 322 |
| 4 | 505 |
| 5 | 204 |
| 6 | 198 |
| 7 | 22 |
| 8 | 8 |
| 10 | 8 |
| 12 (maximum observé) | 5 |

**Conclusion :** liste toujours petite et bornée (1 à 12) → candidate à l'embedding.

### 2.2 Cardinalité paiements / commande

```python
payments.groupby('order_id').size().value_counts()
```

| Nb de paiements | Nb de commandes |
|---|---|
| 1 | 96 479 |
| 2 | 2 382 |
| 3 | 301 |
| ... | ... |
| max observé | 29 |

**Conclusion :** également petit et borné → candidate à l'embedding.

Répartition des types de paiement (`payment_type`) :

| Type | Occurrences |
|---|---|
| credit_card | 76 795 |
| boleto | 19 784 |
| voucher | 5 775 |
| debit_card | 1 529 |
| not_defined | 3 |

Aucune valeur manquante sur les colonnes de paiement.

### 2.3 Cardinalité reviews / commande

```python
reviews.groupby('order_id').size().value_counts()
```

| Nb de reviews | Nb de commandes |
|---|---|
| 1 | 98 126 |
| 2 | 543 |
| 3 | 4 |

**Conclusion :** quasi-toujours 0 ou 1 → un objet embarqué suffit, pas besoin d'une liste.

Valeurs manquantes dans `order_reviews` :

| Colonne | Valeurs manquantes |
|---|---|
| `review_comment_title` | 87 656 / 104 719 |
| `review_comment_message` | 58 247 / 104 719 |

**Conclusion :** la majorité des avis n'ont pas de commentaire texte, seulement une note. C'est normal (l'utilisateur note sans commenter)  à conserver tel quel (`null`), ne pas exclure ces lignes.

### 2.4 Valeurs manquantes dans `orders`

| Colonne | Valeurs manquantes |
|---|---|
| `order_approved_at` | 160 |
| `order_delivered_carrier_date` | 1 783 |
| `order_delivered_customer_date` | 2 965 |

Distribution des statuts (`order_status`) :

| Statut | Nb |
|---|---|
| delivered | 96 478 |
| shipped | 1 107 |
| canceled | 625 |
| unavailable | 609 |
| invoiced | 314 |
| processing | 301 |
| created | 5 |
| approved | 2 |

**Conclusion :** les dates manquantes correspondent aux commandes non livrées (annulées, en cours)  cohérent, pas une erreur de données. À gérer comme `null` dans l'API, pas comme une anomalie à corriger.

### 2.5 Produits

| Colonne | Valeurs manquantes |
|---|---|
| `product_category_name` | 610 / 32 951 |
| `product_weight_g` / dimensions | 2 / 32 951 |

Catégories présentes dans `products.csv` : 73
Catégories présentes dans `translation.csv` : 71
Catégories sans traduction anglaise : `pc_gamer`, `portateis_cozinha_e_preparadores_de_alimentos`

**Conclusion :** incohérence mineure entre les deux fichiers, à documenter. Ces deux catégories seront importées avec `category_name_english: null`.

Ratio produits / lignes d'articles vendus : 32 951 produits pour 112 650 lignes d'articles → chaque produit apparaît en moyenne dans plusieurs commandes différentes.

**Conclusion :** entité partagée, forte réutilisation → candidate à la référence (pas à l'embedding).

### 2.6 Vendeurs

3 095 vendeurs, aucune valeur manquante. Ratio : 112 650 lignes d'articles / 3 095 vendeurs → chaque vendeur apparaît en moyenne dans ~36 commandes.

**Conclusion :** même raisonnement que les produits → entité partagée, référence.

### 2.7 Clients : `customer_id` vs `customer_unique_id`

```python
customers['customer_id'].nunique()          # 99 441
customers['customer_unique_id'].nunique()    # 96 096
```

**Conclusion :** `customer_id` est généré une fois par commande (autant de valeurs uniques que de commandes). `customer_unique_id` identifie la vraie personne : environ 3 345 personnes ont passé plus d'une commande (99 441 − 96 096). Toute analyse de fidélité/récurrence doit se baser sur `customer_unique_id`, jamais sur `customer_id`.

---

## 3. Modélisation MongoDB

### 3.1 Principe de décision retenu

| On **embarque** quand... | On **référence** quand... |
|---|---|
| la donnée est petite et bornée en taille (vérifié : max 12 items, max 29 paiements) | l'entité est réutilisée par des milliers d'autres documents (produits, vendeurs) |
| la donnée n'a de sens qu'au moment de la commande (prix payé ce jour-là, ville de livraison) | l'entité a un cycle de vie indépendant et peut être consultée seule (fiche produit, profil vendeur) |
| la donnée est presque toujours lue **avec** son parent, jamais seule | dupliquer l'information reviendrait à la copier des dizaines de fois inutilement |

### 3.2 Les 4 collections

#### `orders`
Document central. Embarque le snapshot du client, les articles, les paiements, l'avis.

```json
{
  "_id": "e481f51cbdc54678b7cc49136f2d6af7",
  "customer": {
    "customer_unique_id": "861eff4711a542e4b93843c6dd7febb0",
    "city": "franca",
    "state": "SP",
    "zip_code_prefix": "14409"
  },
  "status": "delivered",
  "purchase_timestamp": "2017-10-02T10:56:33",
  "approved_at": "2017-10-02T11:07:15",
  "delivered_carrier_date": "2017-10-04T19:55:00",
  "delivered_customer_date": "2017-10-10T21:25:13",
  "estimated_delivery_date": "2017-10-18T00:00:00",
  "items": [
    {
      "item_id": 1,
      "product_id": "4244733e06e7ecb4970a6e2683c13e61",
      "seller_id": "48436dade18ac8b2bce089ec2a041202",
      "price": 58.90,
      "freight_value": 13.29
    }
  ],
  "payments": [
    { "sequential": 1, "type": "credit_card", "installments": 3, "value": 72.19 }
  ],
  "review": {
    "review_id": "7bc2406110b926393aa56f80a40eba40",
    "score": 4,
    "comment_title": null,
    "comment_message": null,
    "created_at": "2018-01-18T00:00:00",
    "answered_at": "2018-01-18T21:46:59"
  }
}
```

*Justification chiffrée : items (1 à 12, section 2.1), paiements (1 à 29, section 2.2), review (0 ou 1 quasi systématiquement, section 2.3)  tous vérifiés petits et bornés, donc sûrs à embarquer. Dates nulles gérées comme `null` (section 2.4), cohérent avec les statuts non livrés.*

#### `products`
```json
{
  "_id": "1e9e8ef04dbcff4541ed26657ea517e5",
  "category_name": "perfumaria",
  "category_name_english": "perfumery",
  "name_length": 40,
  "description_length": 287,
  "photos_qty": 1,
  "weight_g": 225,
  "dimensions_cm": { "length": 16, "height": 10, "width": 14 }
}
```
*Justification : réutilisé par de nombreuses commandes (section 2.5) → référencé via `product_id` dans `orders.items`, jamais dupliqué. Catégories manquantes ou non traduites conservées en `null`, documentées plutôt que corrigées arbitrairement.*

#### `sellers`
```json
{
  "_id": "3442f8959a84dea7ee197c632cb2df15",
  "city": "campinas",
  "state": "SP",
  "zip_code_prefix": "13023"
}
```
*Justification : réutilisé par ~36 commandes en moyenne (section 2.6) → référencé via `seller_id`.*

#### `customers`
```json
{
  "_id": "861eff4711a542e4b93843c6dd7febb0",
  "city": "franca",
  "state": "SP",
  "orders_count": 1
}
```
*Justification : nécessaire uniquement parce que `customer_id` ≠ personne réelle (section 2.7). Cette collection, indexée sur `customer_unique_id`, permet de répondre à des questions d'analyse (clients récurrents) que l'embedding dans `orders` ne permettrait pas.*

### 3.3 Ce qu'on gagne avec ce modèle

- `GET /orders/{id}` → **1 seule requête MongoDB**, tout est dans le document (au lieu de 4 jointures en SQL classique).
- Le catalogue produits et la liste des vendeurs restent **consultables et modifiables indépendamment**, sans toucher à l'historique des commandes.
- Les questions d'analyse par personne réelle (fidélité client) restent possibles grâce à la collection `customers` séparée.
