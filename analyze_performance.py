"""
Analyse de performance MongoDB : est-ce qu'un index sert vraiment à quelque chose ?

L'idée du script :
  1. On choisit un produit qui a été acheté dans plusieurs commandes.
  2. On regarde comment MongoDB exécute la requête "trouve les commandes
     contenant ce produit" SANS index (ça doit lire toute la collection :
     un "COLLSCAN").
  3. On crée un index sur ce champ.
  4. On relance la même requête : MongoDB doit cette fois utiliser l'index
     directement, sans tout relire (un "IXSCAN").
  5. On compare : nombre de documents lus, temps d'exécution.

Pour le lancer, modifie si besoin les 2 premières lignes de configuration,
puis :
    python analyze_performance.py
"""

from pymongo import MongoClient


# CONFIGURATION

ADRESSE_MONGO = "mongodb://localhost:27017"
NOM_BASE = "olist"


# CONNEXION

client = MongoClient(ADRESSE_MONGO)
db = client[NOM_BASE]

nb_commandes = db.orders.count_documents({})
if nb_commandes == 0:
    print("La collection 'orders' est vide. Lance d'abord le script d'import.")
    exit()

print(f"Collection 'orders' : {nb_commandes:,} documents\n")


# 1. CHOISIR UN PRODUIT À TESTER
# On veut un produit acheté entre 3 et 10 fois : ni un produit unique
# (pas assez parlant), ni un best-seller (pas représentatif).

pipeline = [
    {"$unwind": "$items"},
    {"$group": {"_id": "$items.product_id", "nb_commandes": {"$sum": 1}}},
    {"$match": {"nb_commandes": {"$gte": 3, "$lte": 10}}},
    {"$limit": 1},
]

resultat = list(db.orders.aggregate(pipeline))
if not resultat:
    print("Aucun produit trouvé avec 3 à 10 commandes.")
    exit()

produit_id = resultat[0]["_id"]
nb_commandes_produit = resultat[0]["nb_commandes"]

print(f"Produit choisi pour le test : {produit_id}")
print(f"(il apparaît dans {nb_commandes_produit} commandes)\n")

requete = {"items.product_id": produit_id}


# 2. S'ASSURER QU'IL N'Y A PAS DÉJÀ UN INDEX (pour un test "avant" propre)

index_existants = db.orders.index_information()
for nom_index, info in index_existants.items():
    if info["key"] == [("items.product_id", 1)]:
        db.orders.drop_index(nom_index)
        print(
            f"Un index existant ('{nom_index}') a été supprimé pour repartir de zéro.\n"
        )


# 3. AVANT : explain() SANS index

explication_avant = db.command(
    "explain",
    {"find": "orders", "filter": requete},
    verbosity="executionStats",
)
stats_avant = explication_avant["executionStats"]

print("--- AVANT (sans index) — on attend un COLLSCAN ---")
print(
    "Stage du plan d'exécution :",
    explication_avant["queryPlanner"]["winningPlan"]["stage"],
)
print("Documents examinés        :", stats_avant["totalDocsExamined"])
print("Temps d'exécution         :", stats_avant["executionTimeMillis"], "ms")


# 4. CRÉATION DE L'INDEX

nom_nouvel_index = db.orders.create_index("items.product_id")
print(f"\nIndex créé : {nom_nouvel_index}\n")


# 5. APRÈS : explain() AVEC l'index

explication_apres = db.command(
    "explain",
    {"find": "orders", "filter": requete},
    verbosity="executionStats",
)
stats_apres = explication_apres["executionStats"]

print(
    "--- APRÈS (avec index) — on attend un IXSCAN (ou FETCH au-dessus d'un IXSCAN) ---"
)
print(
    "Stage du plan d'exécution :",
    explication_apres["queryPlanner"]["winningPlan"]["stage"],
)
print("Documents examinés        :", stats_apres["totalDocsExamined"])
print("Temps d'exécution         :", stats_apres["executionTimeMillis"], "ms")


# 6. COMPARATIF FINAL

print("\n=== Résumé ===")
print(
    f"Documents examinés : {stats_avant['totalDocsExamined']} (avant)  ->  {stats_apres['totalDocsExamined']} (après)"
)
print(
    f"Temps d'exécution  : {stats_avant['executionTimeMillis']} ms (avant)  ->  {stats_apres['executionTimeMillis']} ms (après)"
)

if stats_apres["totalDocsExamined"] > 0:
    gain = stats_avant["totalDocsExamined"] / stats_apres["totalDocsExamined"]
    print(
        f"\n=> Grâce à l'index, MongoDB lit environ {gain:.0f} fois moins de documents."
    )
