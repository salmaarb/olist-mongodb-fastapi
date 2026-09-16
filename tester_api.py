"""
Petit script pour vérifier "à la main" que l'API répond correctement.

Avant de lancer ce script :
  1. Assure-toi que MongoDB tourne, avec les données déjà importées.
  2. Lance l'API dans un premier terminal :
         uvicorn main:app --reload
  3. Dans un DEUXIÈME terminal, lance ce script :
         python tester_api.py
"""

import requests

ADRESSE_API = "http://localhost:8000"


def verifier(condition, message):
    """Affiche OK ou ECHEC selon si la condition est vraie ou fausse."""
    if condition:
        print("OK    -", message)
    else:
        print("ECHEC -", message)


# --- 1. L'API répond bien à la racine ---
reponse = requests.get(f"{ADRESSE_API}/")
verifier(reponse.status_code == 200, "GET / répond 200")


# --- 2. On récupère une vraie commande depuis la liste, pour la tester ensuite ---
reponse = requests.get(f"{ADRESSE_API}/orders", params={"limit": 1})
verifier(reponse.status_code == 200, "GET /orders répond 200")

premiere_commande = reponse.json()["results"][0]
order_id = premiere_commande["_id"]


# --- 3. Détail d'une commande qui existe vraiment ---
reponse = requests.get(f"{ADRESSE_API}/orders/{order_id}")
verifier(reponse.status_code == 200, "GET /orders/{id} avec un id valide répond 200")
verifier("items" in reponse.json(), "la réponse contient bien la liste 'items'")


# --- 4. Détail d'une commande qui n'existe PAS ---
reponse = requests.get(f"{ADRESSE_API}/orders/ce_id_n_existe_pas")
verifier(reponse.status_code == 404, "GET /orders/{id} avec un id invalide répond 404")


# --- 5. La pagination refuse une limite trop grande ---
reponse = requests.get(f"{ADRESSE_API}/orders", params={"limit": 500})
verifier(reponse.status_code == 422, "GET /orders avec limit=500 est bien refusé (422)")


# --- 6. Un filtre par ville fonctionne ---
reponse = requests.get(f"{ADRESSE_API}/orders", params={"city": "sao paulo", "limit": 5})
verifier(reponse.status_code == 200, "GET /orders?city=sao paulo répond 200")
verifier(reponse.json()["total"] > 0, "il y a bien des commandes à Sao Paulo")


# --- 7. Un endpoint agrégé répond avec des résultats ---
reponse = requests.get(f"{ADRESSE_API}/stats/revenue-by-state")
verifier(reponse.status_code == 200, "GET /stats/revenue-by-state répond 200")
verifier(len(reponse.json()) > 0, "GET /stats/revenue-by-state renvoie des résultats")


print("\nTests terminés.")
