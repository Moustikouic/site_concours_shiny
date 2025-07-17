from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import requests
import re
import os
import json

app = Flask(__name__)

# Config base PostgreSQL (Render)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://shiny_db_ed3c_user:Rc5Gj3RswWLfVzsfClAiEGwYg7VE1V3L@dpg-d1sd8dre5dus739irj80-a.frankfurt-postgres.render.com/shiny_db_ed3c'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Joueurs prédéfinis
PLAYERS = ["Thomas", "Théo"]

# Traduction des types
type_traductions = {
    "normal": "Normal", "fire": "Feu", "water": "Eau", "grass": "Plante",
    "electric": "Électrik", "ice": "Glace", "fighting": "Combat", "poison": "Poison",
    "ground": "Sol", "flying": "Vol", "psychic": "Psy", "bug": "Insecte",
    "rock": "Roche", "ghost": "Spectre", "dragon": "Dragon", "dark": "Ténèbres",
    "steel": "Acier", "fairy": "Fée"
}

sources_possibles = ["rencontre", "oeuf", "reset", "event"]

# Modèle SQLAlchemy pour les shiny capturés
class Shiny(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    sprite_shiny = db.Column(db.String(250))
    types = db.Column(db.String(100))  # stocke types séparés par ,
    source = db.Column(db.String(20), default="rencontre")
    nb_oeufs = db.Column(db.Integer, default=0)
    nb_resets = db.Column(db.Integer, default=0)

    def types_list(self):
        return self.types.split(",") if self.types else []

# Crée la base si besoin et vérifie la connexion
with app.app_context():
    try:
        db.create_all()
        db.session.execute("SELECT 1")
        print("Connexion à la DB OK")
    except Exception as e:
        print("Erreur DB:", e)

def get_french_pokedex(limit=493):
    cache_file = "pokedex_cache.json"
    if os.path.exists(cache_file):
        with open(cache_file, encoding="utf-8") as f:
            return json.load(f)
    url = f"https://pokeapi.co/api/v2/pokemon-species?limit={limit}"
    response = requests.get(url)
    all_species = response.json()["results"]
    pokedex = []
    for species in all_species:
        res = requests.get(species["url"])
        if res.status_code != 200:
            continue
        data = res.json()
        name_fr = next((n["name"] for n in data["names"] if n["language"]["name"] == "fr"), None)
        if name_fr:
            pokedex.append({"id": data["id"], "name": name_fr})
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(pokedex, f, ensure_ascii=False, indent=2)
    return pokedex

def get_pokemon_data(name_fr):
    # Lire le pokedex local
    cache_file = "pokedex_cache.json"
    if not os.path.exists(cache_file):
        print("Cache pokedex introuvable")
        return None

    with open(cache_file, encoding="utf-8") as f:
        pokedex_data = json.load(f)

    # Trouver le bon ID du pokémon via son nom fr
    m = re.match(r"(.+?) \(#(\d+)\)", name_fr)
    if not m:
        print("Nom Pokémon invalide :", name_fr)
        return None

    id_pokemon = m.group(2)

    # Appel PokeAPI par ID (ex: https://pokeapi.co/api/v2/pokemon/5)
    poke_api_url = f"https://pokeapi.co/api/v2/pokemon/{id_pokemon}"
    res = requests.get(poke_api_url)
    if res.status_code != 200:
        print(f"Erreur pokeapi pour ID {id_pokemon}: {res.status_code}")
        return None

    data = res.json()
    sprite = data["sprites"]["front_shiny"]
    types = [type_traductions.get(t["type"]["name"], t["type"]["name"]) for t in data["types"]]
    return {"name": name_fr, "sprite_shiny": sprite, "types": types}

@app.route("/", methods=["GET", "POST"])
def index():
    pokedex = get_french_pokedex()

    if request.method == "POST":
        player = request.form.get("player")
        pokemon_raw = request.form.get("pokemon")
        source = request.form.get("source")
        nb_oeufs = request.form.get("nb_oeufs", "0")
        nb_resets = request.form.get("nb_resets", "0")

        print(f"POST reçu : player={player}, pokemon={pokemon_raw}, source={source}, oeufs={nb_oeufs}, resets={nb_resets}")

        if player not in PLAYERS or not pokemon_raw:
            print("Player invalide ou pokemon non spécifié.")
            return redirect(url_for("index"))

        # Nettoyer pokemon_raw: on veut la partie "Nom (#id)"
        pokemon_clean = pokemon_raw.split(" (#")[0].strip()

        data = get_pokemon_data(pokemon_raw)
        if not data:
            print("Données Pokémon non trouvées, retour index.")
            return redirect(url_for("index"))

        try:
            nb_oeufs = int(nb_oeufs)
        except:
            nb_oeufs = 0
        try:
            nb_resets = int(nb_resets)
        except:
            nb_resets = 0

        shiny = Shiny(
            player=player,
            name=data["name"],
            sprite_shiny=data["sprite_shiny"],
            types=",".join(data["types"]),
            source=source if source in sources_possibles else "rencontre",
            nb_oeufs=nb_oeufs if source=="oeuf" else 0,
            nb_resets=nb_resets if source=="reset" else 0,
        )
        db.session.add(shiny)
        db.session.commit()
        print(f"Shiny ajouté : {shiny.name} pour {shiny.player}")

        return redirect(url_for("index"))

    shiny_by_player = {player: [] for player in PLAYERS}
    for s in Shiny.query.all():
        shiny_by_player[s.player].append({
            "name": s.name,
            "sprite_shiny": s.sprite_shiny,
            "types": s.types_list(),
            "source": s.source,
            "nb_oeufs": s.nb_oeufs,
            "nb_resets": s.nb_resets,
        })

    return render_template("index.html", players_list=PLAYERS, pokedex=pokedex, players=shiny_by_player)

@app.route("/remove", methods=["POST"])
def remove_pokemon():
    player = request.form.get("player")
    pokemon_name = request.form.get("pokemon_name")

    if not player or not pokemon_name:
        return redirect(url_for("index"))

    shiny_to_delete = Shiny.query.filter_by(player=player, name=pokemon_name).first()
    if shiny_to_delete:
        db.session.delete(shiny_to_delete)
        db.session.commit()
        print(f"Shiny supprimé : {pokemon_name} pour {player}")

    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)