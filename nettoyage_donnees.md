# Nettoyage des données : Olist

Ce document liste les incohérences trouvées lors de l'analyse des CSV, la décision prise pour chacune, et sa justification. Il complète `analyse_donnees_et_modelisation.md` (qui porte sur la modélisation) en se concentrant sur la **qualité** des données.

## 1. Bug corrigé : perte du zéro initial des codes postaux

**Le problème :** les codes postaux brésiliens (CEP) peuvent commencer par un zéro (ex : `09790`). Lu sans précaution, `pandas` interprète la colonne comme un nombre entier, ce qui supprime silencieusement ce zéro (`09790` devient `9790`).

**Ampleur mesurée :**
- 23 995 clients concernés sur 99 441 (**24,1 %**)
- 1 027 vendeurs concernés sur 3 095 (**33,2 %**)

```python
customers_int = pd.read_csv('olist_customers_dataset.csv')  # lecture par défaut -> int64
(customers_int['customer_zip_code_prefix'] < 10000).sum()   # 23995
```

**Correction appliquée :** on force la lecture de ces colonnes en texte dès l'ouverture du CSV (`dtype={"customer_zip_code_prefix": str}` / `dtype={"seller_zip_code_prefix": str}`), ce qui préserve le zéro initial tel qu'il apparaît réellement dans le fichier source.

**Important :** ce bug était déjà présent dans la première version d'`import_data.py`. Si tu as déjà importé les données avant cette correction, **relance l'import** — le script est idempotent (upsert sur `_id`), donc relancer le corrige silencieusement sans dupliquer quoi que ce soit.

## 2. `review_id` dupliqué entre commandes différentes

**Le problème :** 789 `review_id` apparaissent dans plusieurs lignes, chacune associée à un `order_id` **différent** (mais avec le même score et la même date de création).

```python
reviews[reviews['review_id'].duplicated(keep=False)]['review_id'].nunique()  # 789
```

**Décision : aucune action corrective.** C'est une particularité connue du dataset Olist (un même événement de review associé à plusieurs commandes), pas une erreur de notre pipeline. Notre modèle indexe les avis par `order_id` (pas par `review_id`), donc chaque commande garde son propre avis correctement rattaché. À documenter comme limitation connue si on devait un jour compter des avis "uniques" plutôt que des avis "par commande".

## 3. Paiements à 0 €

**Le problème :** 9 lignes de `order_payments` ont `payment_value = 0`.

**Analyse :** en croisant avec `orders.csv`, les 3 cas où c'est le **seul** paiement de la commande correspondent tous à `order_status = 'canceled'` et `payment_type = 'not_defined'`. Les 6 autres cas sont une ligne à 0 € parmi plusieurs paiements réels sur la même commande (n'affecte pas le total).

**Décision : aucune action corrective.** Une commande annulée avec un paiement à 0 € est cohérente avec la réalité métier (le paiement n'a jamais abouti), pas une anomalie à corriger.

## 4. `payment_installments = 0`

**Le problème :** 2 lignes sur 103 886 ont `payment_installments = 0`, alors qu'un paiement réel (carte de crédit, montant non nul) ne peut pas être "en 0 fois".

**Décision : plafonné à 1** (`max(installments, 1)`) lors de l'import. Impact négligeable (0,002 % des lignes) mais évite une valeur incohérente dans l'API.

## 5. Poids produit à 0 g

**Le problème :** 4 produits sur 32 951 ont `product_weight_g = 0`, physiquement impossible pour un colis expédié.

**Décision : traité comme valeur manquante** (`null`), plutôt que de fausser une éventuelle moyenne de poids par catégorie.

## 6. Vérifications qui n'ont rien trouvé (mais qu'il fallait faire)

| Vérification | Résultat |
|---|---|
| Doublons de lignes exactes (tous fichiers) | 0 |
| Doublons de clé primaire (`order_id`, `product_id`, `seller_id`, `customer_id`) | 0 |
| `order_items.product_id` sans produit correspondant dans `products.csv` | 0 |
| `order_items.seller_id` sans vendeur correspondant dans `sellers.csv` | 0 |
| `order_items` / `order_payments` référençant un `order_id` inexistant | 0 |
| `orders.customer_id` sans client correspondant dans `customers.csv` | 0 |
| Commandes livrées avant leur date d'achat (incohérence temporelle) | 0 |
| Prix ou frais de port négatifs | 0 |

L'intégrité référentielle du dataset est bonne — aucune commande, produit ou vendeur "fantôme" à gérer.

## Résumé des corrections dans `import_data.py`

| Champ | Règle |
|---|---|
| `customer_zip_code_prefix`, `seller_zip_code_prefix` | Lus en texte (`dtype=str`) dès l'ouverture du CSV, jamais en `int` |
| `products.weight_g` | `0` → `null` |
| `payments.installments` | Plafonné à un minimum de `1` |
| Toutes les autres valeurs manquantes (`NaN`) | Converties en `null` (déjà en place, voir `analyse_donnees_et_modelisation.md`) |
