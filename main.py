"""
API Olist

Comment lancer cette API :
    uvicorn main:app --reload

Puis ouvre http://localhost:8000/docs pour la tester dans le navigateur
"""

from fastapi import FastAPI, HTTPException, Query
from pymongo import MongoClient


# CONFIGURATION ET CONNEXION

ADRESSE_MONGO = "mongodb://localhost:27017"
NOM_BASE = "olist"

client = MongoClient(ADRESSE_MONGO)
db = client[NOM_BASE]

app = FastAPI(title="Olist API ")


@app.get("/")
def accueil():
    """Juste pour vérifier que l'API répond."""
    return {"message": "L'API fonctionne. Va voir /docs pour la documentation."}


# COMMANDES (orders)


@app.get("/orders/{order_id}")
def get_order(order_id: str):
    """Retourne le détail complet d'une commande (articles, paiements, avis)."""
    commande = db.orders.find_one({"_id": order_id})
    if commande is None:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    return commande


@app.get("/orders")
def list_orders(
    city: str = None,
    status: str = None,
    skip: int = 0,
    limit: int = Query(
        default=20, le=100
    ),  # 100 max, pour éviter une réponse trop lourde
):
    """Liste les commandes, avec des filtres optionnels et une pagination."""
    filtre = {}
    if city:
        filtre["customer.city"] = city.lower()
    if status:
        filtre["status"] = status.lower()

    total = db.orders.count_documents(filtre)
    resultats = list(db.orders.find(filtre).skip(skip).limit(limit))

    return {"total": total, "skip": skip, "limit": limit, "results": resultats}


# PRODUITS


@app.get("/products/{product_id}")
def get_product(product_id: str):
    produit = db.products.find_one({"_id": product_id})
    if produit is None:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    return produit


@app.get("/products")
def list_products(
    category: str = None, skip: int = 0, limit: int = Query(default=20, le=100)
):
    filtre = {}
    if category:
        filtre["category_name_english"] = category.lower()

    total = db.products.count_documents(filtre)
    resultats = list(db.products.find(filtre).skip(skip).limit(limit))
    return {"total": total, "skip": skip, "limit": limit, "results": resultats}


# VENDEURS


@app.get("/sellers/{seller_id}")
def get_seller(seller_id: str):
    vendeur = db.sellers.find_one({"_id": seller_id})
    if vendeur is None:
        raise HTTPException(status_code=404, detail="Vendeur introuvable")
    return vendeur


@app.get("/sellers")
def list_sellers(
    city: str = None, skip: int = 0, limit: int = Query(default=20, le=100)
):
    filtre = {}
    if city:
        filtre["city"] = city.lower()

    total = db.sellers.count_documents(filtre)
    resultats = list(db.sellers.find(filtre).skip(skip).limit(limit))
    return {"total": total, "skip": skip, "limit": limit, "results": resultats}


# CLIENTS


@app.get("/customers/{customer_unique_id}")
def get_customer(customer_unique_id: str):
    client_doc = db.customers.find_one({"_id": customer_unique_id})
    if client_doc is None:
        raise HTTPException(status_code=404, detail="Client introuvable")
    return client_doc


@app.get("/customers")
def list_customers(
    min_orders: int = None, skip: int = 0, limit: int = Query(default=20, le=100)
):
    filtre = {}
    if min_orders is not None:
        filtre["orders_count"] = {"$gte": min_orders}

    total = db.customers.count_documents(filtre)
    resultats = list(db.customers.find(filtre).skip(skip).limit(limit))
    return {"total": total, "skip": skip, "limit": limit, "results": resultats}


# STATISTIQUES (résultats agrégés)


@app.get("/stats/revenue-by-state")
def revenue_by_state(limit: int = Query(default=10, le=50)):
    """Chiffre d'affaires total par état, du plus gros au plus petit."""
    pipeline = [
        {"$unwind": "$items"},
        {
            "$group": {
                "_id": "$customer.state",
                "total_revenue": {"$sum": "$items.price"},
                "nb_orders": {"$sum": 1},
            }
        },
        {"$match": {"_id": {"$ne": None}}},
        {"$sort": {"total_revenue": -1}},
        {"$limit": limit},
    ]
    return list(db.orders.aggregate(pipeline))


@app.get("/stats/reviews-by-category")
def reviews_by_category(limit: int = Query(default=10, le=50)):
    """Note moyenne des avis, par catégorie de produit."""
    pipeline = [
        {"$match": {"review": {"$type": "object"}}},
        {"$unwind": "$items"},
        {
            "$lookup": {
                "from": "products",
                "localField": "items.product_id",
                "foreignField": "_id",
                "as": "product",
            }
        },
        {"$unwind": "$product"},
        {
            "$group": {
                "_id": "$product.category_name_english",
                "avg_review_score": {"$avg": "$review.score"},
                "nb_reviews": {"$sum": 1},
            }
        },
        {"$match": {"_id": {"$ne": None}}},
        {"$sort": {"nb_reviews": -1}},
        {"$limit": limit},
    ]
    return list(db.orders.aggregate(pipeline))
