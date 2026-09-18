"""
Script d'import du dataset Olist vers MongoDB

Comment ça marche, en résumé :
  1. On lit les 8 fichiers CSV avec pandas.
  2. On construit 4 "collections" MongoDB : products, sellers, customers, orders.
  3. Pour "orders", on regroupe dans un seul document : la commande, ses
     articles, ses paiements et son avis (c'est ce qu'on appelle
     "l'embedding" dans notre modélisation).
  4. On vide chaque collection puis on insère les nouveaux documents.
     (Vider avant de réinsérer, c'est plus simple à comprendre que de
     "mettre à jour" chaque document un par un, et ça donne toujours un
     résultat propre : à chaque lancement, la base est remise à jour.)

Pour le lancer : modifie les 3 variables de configuration juste en dessous,
puis lance simplement :
    python import_data.py
"""

import pandas as pd
from pymongo import MongoClient


# 1. CONFIGURATION

DOSSIER_DONNEES = "./data"
ADRESSE_MONGO = "mongodb://localhost:27017"
NOM_BASE = "olist"


# 2. CONNEXION À MONGODB

client = MongoClient(ADRESSE_MONGO)
db = client[NOM_BASE]


# 3. PETITE FONCTION UTILITAIRE


def valeur_ou_none(valeur):
    """Pandas utilise 'NaN' pour représenter une case vide.
    MongoDB, lui, utilise 'None' (qui devient 'null' en JSON).
    Cette fonction fait juste la conversion entre les deux.
    """
    if pd.isna(valeur):
        return None
    return valeur


# 4. LECTURE DES FICHIERS CSV

print("Lecture des fichiers CSV...")

orders = pd.read_csv(f"{DOSSIER_DONNEES}/olist_orders_dataset.csv")
items = pd.read_csv(f"{DOSSIER_DONNEES}/olist_order_items_dataset.csv")
payments = pd.read_csv(f"{DOSSIER_DONNEES}/olist_order_payments_dataset.csv")
reviews = pd.read_csv(f"{DOSSIER_DONNEES}/olist_order_reviews_dataset.csv")
products = pd.read_csv(f"{DOSSIER_DONNEES}/olist_products_dataset.csv")
translation = pd.read_csv(f"{DOSSIER_DONNEES}/product_category_name_translation.csv")

# les codes postaux commencent parfois par un zéro (ex: "09790").

customers = pd.read_csv(
    f"{DOSSIER_DONNEES}/olist_customers_dataset.csv",
    dtype={"customer_zip_code_prefix": str},
)
sellers = pd.read_csv(
    f"{DOSSIER_DONNEES}/olist_sellers_dataset.csv",
    dtype={"seller_zip_code_prefix": str},
)

print("Fichiers chargés.\n")


# 5. COLLECTION "products"

print("Construction de la collection 'products'...")

# Un dictionnaire pour traduire une catégorie du portugais vers l'anglais
traduction_categories = dict(
    zip(
        translation["product_category_name"],
        translation["product_category_name_english"],
    )
)

liste_produits = []

for _, ligne in products.iterrows():
    categorie = valeur_ou_none(ligne["product_category_name"])

    poids = valeur_ou_none(ligne["product_weight_g"])
    if poids == 0:
        # Un poids de 0 gramme n'a pas de sens pour un colis : on considère
        # que c'est une valeur manquante plutôt qu'une vraie mesure.
        poids = None

    produit = {
        "_id": ligne["product_id"],
        "category_name": categorie,
        "category_name_english": traduction_categories.get(categorie),
        "weight_g": poids,
        "dimensions_cm": {
            "length": valeur_ou_none(ligne["product_length_cm"]),
            "height": valeur_ou_none(ligne["product_height_cm"]),
            "width": valeur_ou_none(ligne["product_width_cm"]),
        },
    }
    liste_produits.append(produit)

db.products.delete_many({})  # on vide la collection...
db.products.insert_many(liste_produits)  # ...puis on la remplit d'un coup

print(f"-> {len(liste_produits)} produits importés.\n")


# 6. COLLECTION "sellers"

print("Construction de la collection 'sellers'...")

liste_vendeurs = []

for _, ligne in sellers.iterrows():
    vendeur = {
        "_id": ligne["seller_id"],
        "city": ligne["seller_city"],
        "state": ligne["seller_state"],
        "zip_code_prefix": ligne["seller_zip_code_prefix"],
    }
    liste_vendeurs.append(vendeur)

db.sellers.delete_many({})
db.sellers.insert_many(liste_vendeurs)

print(f"-> {len(liste_vendeurs)} vendeurs importés.\n")


# 7. COLLECTION "customers"


print("Construction de la collection 'customers'...")

clients_regroupes = (
    customers.groupby("customer_unique_id")
    .agg(
        city=("customer_city", "first"),
        state=("customer_state", "first"),
        orders_count=("customer_id", "count"),
    )
    .reset_index()
)

liste_clients = []

for _, ligne in clients_regroupes.iterrows():
    client_doc = {
        "_id": ligne["customer_unique_id"],
        "city": ligne["city"],
        "state": ligne["state"],
        "orders_count": int(ligne["orders_count"]),
    }
    liste_clients.append(client_doc)

db.customers.delete_many({})
db.customers.insert_many(liste_clients)

print(f"-> {len(liste_clients)} clients importés.\n")


# 8. COLLECTION "orders"
# On construit UN document par commande, qui contient directement :
#   - un aperçu du client (ville, état au moment de la commande)
#   - la liste de ses articles
#   - la liste de ses paiements
#   - son avis (s'il y en a un)


print("Construction de la collection 'orders' (ça prend quelques minutes)...")

customers_par_id = customers.set_index("customer_id")
items_par_commande = dict(list(items.groupby("order_id")))
paiements_par_commande = dict(list(payments.groupby("order_id")))
avis_par_commande = dict(list(reviews.groupby("order_id")))

liste_commandes = []

for _, commande in orders.iterrows():
    order_id = commande["order_id"]

    # --- le client  ---
    client_snapshot = None
    if commande["customer_id"] in customers_par_id.index:
        c = customers_par_id.loc[commande["customer_id"]]
        client_snapshot = {
            "customer_unique_id": c["customer_unique_id"],
            "city": c["customer_city"],
            "state": c["customer_state"],
            "zip_code_prefix": c["customer_zip_code_prefix"],
        }

    # --- les articles achetés (une liste, une commande peut en avoir plusieurs) ---
    articles = []
    if order_id in items_par_commande:
        for _, article in items_par_commande[order_id].iterrows():
            articles.append(
                {
                    "product_id": article["product_id"],
                    "seller_id": article["seller_id"],
                    "price": float(article["price"]),
                    "freight_value": float(article["freight_value"]),
                }
            )

    # --- les paiements  ---
    paiements = []
    if order_id in paiements_par_commande:
        for _, paiement in paiements_par_commande[order_id].iterrows():
            installments = int(paiement["payment_installments"])
            paiements.append(
                {
                    "type": paiement["payment_type"],
                    "installments": max(installments, 1),
                    "value": float(paiement["payment_value"]),
                }
            )

    # --- l'avis ---
    avis = None
    if order_id in avis_par_commande:
        premier_avis = avis_par_commande[order_id].iloc[0]
        avis = {
            "score": int(premier_avis["review_score"]),
            "comment_message": valeur_ou_none(premier_avis["review_comment_message"]),
        }

    commande_doc = {
        "_id": order_id,
        "customer": client_snapshot,
        "status": commande["order_status"],
        "purchase_timestamp": commande["order_purchase_timestamp"],
        "items": articles,
        "payments": paiements,
        "review": avis,
    }
    liste_commandes.append(commande_doc)

db.orders.delete_many({})
db.orders.insert_many(liste_commandes)

print(f"-> {len(liste_commandes)} commandes importées.\n")


# 9. CRÉATION DES INDEX
# Un index permet à MongoDB de retrouver des documents sans avoir à tous
# les lire un par un. On en crée sur les champs qu'on filtre souvent
# dans l'API
print("Création des index...")

db.orders.create_index("customer.city")
db.orders.create_index("status")
db.orders.create_index("items.product_id")
db.products.create_index("category_name_english")
db.sellers.create_index("city")
db.customers.create_index("orders_count")

print("Index créés.\n")


# 10. VÉRIFICATION FINALE

print("=== Import terminé ===")
print("orders   :", db.orders.count_documents({}))
print("products :", db.products.count_documents({}))
print("sellers  :", db.sellers.count_documents({}))
print("customers:", db.customers.count_documents({}))
