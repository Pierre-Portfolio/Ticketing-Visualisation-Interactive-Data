<h1 align="center">Ticketing Graph</h1>

---

# Ticketing Graph — Visualisation interactive d'une base NoSQL (graphe)

## Aperçu
Projet **pédagogique** pour explorer le fonctionnement des **bases de données NoSQL orientées graphe** sur un cas concret simple : un jeu de données de **ticketing** (tickets, messages, utilisateurs, clients, tags) modélisé en **nœuds** et **relations**, puis rendu sous forme de **graphe interactif** directement dans le navigateur. Aucun serveur requis : la visualisation est un fichier HTML statique généré depuis deux fichiers CSV.

L'objectif n'est pas de produire une application finie, mais de **comprendre** comment on passe d'une table relationnelle classique à un modèle graphe (entités → nœuds, jointures → arêtes typées) et comment on l'interroge/visualise.

## Objectif pédagogique
- Modéliser un domaine métier (le support / ticketing) en **graphe de propriétés** : nœuds typés + relations typées + attributs
- Comparer le modèle **graphe** au modèle **relationnel** (une jointure devient une arête)
- Manipuler le jeu de données avec différents outils NoSQL (import dans une base graphe type Neo4j, exploration en Python…)
- Visualiser et **explorer interactivement** la structure (voisinage, densité, hubs)

## Fonctionnalités

### Modèle de données (graphe de propriétés)
- **5 types de nœuds** : `ticket`, `message`, `user`, `client`, `tag` — chacun avec une couleur et une taille dédiées
- **7 types de relations** : `a_créé`, `a_envoyé`, `appartient_à`, `assigné_à`, `gère`, `lié_à`, `tagué`
- Chaque nœud porte 3 attributs libres (`attribute1/2/3`) dont le sens dépend du type (ex. pour un ticket : statut / date / priorité)
- Chaque arête porte un `weight` (poids de la relation)

### Visualisation interactive
- Rendu **vis.js** (moteur de graphe WebGL/Canvas) avec disposition par force (barnesHut)
- **Mise en évidence du voisinage au clic** : sélectionner un nœud éclaire son voisinage (profondeur réglable) et grise le reste, **arêtes comprises**
- **Tooltips** au survol : type du nœud et ses attributs (texte brut — pas d'injection HTML)
- Zoom, déplacement, **boutons de navigation** et contrôle clavier
- **Barre de chargement** pendant la stabilisation, puis **physique coupée** pour une interaction fluide

### Panneau d'exploration (interface intégrée)
- **Recherche** d'un nœud par `id` ou libellé (centrage + mise en évidence)
- **Filtres** par type de nœud et par type de relation (cases à cocher)
- **Filtre temporel** : ne garder que les nœuds datés dans une plage (du / au)
- **Coloration** par type *ou* par priorité (tickets : low → critical)
- **Profondeur de voisinage** réglable au clic (1, 2 ou 3 degrés)
- **Panneau de détails** : attributs du nœud cliqué + liste cliquable des voisins
- **Statistiques** : volumes nœuds/arêtes et top des nœuds les plus connectés (hubs)
- **Légende** des couleurs par type
- **Export** : capture **PNG** du graphe et export **JSON** du sous-graphe sélectionné

### Génération reproductible
- `generate_graph.py` reconstruit le HTML depuis les CSV : le dépôt est **régénérable** d'un bout à l'autre
- Constante `MAX_NODES` pour produire un graphe complet (par défaut) ou un échantillon plus léger/lisible

## Technologies
- **Python 3** + [`pyvis`](https://pyvis.readthedocs.io/) `0.3.2` (génération du HTML)
- **vis-network 9.1.2** (rendu du graphe, chargé via CDN avec **SRI**)
- **Bootstrap 5** (mise en page légère, via CDN avec SRI)
- Données plates en **CSV** (`nodes.csv` / `edges.csv`) — aucune dépendance à un serveur
- Hébergement statique possible sur **GitHub Pages**

## Installation

```bash
# 1. Récupérer le dépôt
git clone https://github.com/Pierre-Portfolio/Ticketing-Visualisation-Interactive-Data.git
cd Ticketing-Visualisation-Interactive-Data

# 2. Installer les dépendances Python
pip install -r requirements.txt

# 3. (Re)générer la visualisation
python generate_graph.py

# 4. Ouvrir le résultat dans un navigateur
#    -> ticketing_graph.html
```

Démo en ligne (statique) :

👉 **https://pierre-portfolio.github.io/Ticketing-Visualisation-Interactive-Data/ticketing_graph.html**

## Structure du projet
```
Ticketing-Visualisation-Interactive-Data/
  nodes.csv             → Nœuds du graphe (5000 entités : tickets, messages, users, clients, tags)
  edges.csv             → Arêtes du graphe (5000 relations typées + poids)
  generate_graph.py     → Génère ticketing_graph.html depuis les CSV (pyvis)
  ticketing_graph.html  → Visualisation interactive (sortie générée, vis.js)
  requirements.txt      → Dépendances Python (pyvis)
```

## Schéma des données (modèle graphe)

```text
# nodes.csv
id, label, type, attribute1, attribute2, attribute3
  id          → identifiant unique du nœud (ex. T03406, M00763, U0012)
  label       → libellé affiché
  type        → ticket | message | user | client | tag
  attribute1  → ex. ticket: statut · message: direction (inbound/outbound)
  attribute2  → ex. date (YYYY-MM-DD)
  attribute3  → ex. ticket: priorité (low/medium/high/critical)

# edges.csv
source, target, relation, weight
  source   → id du nœud d'origine
  target   → id du nœud de destination
  relation → a_créé | a_envoyé | appartient_à | assigné_à | gère | lié_à | tagué
  weight   → poids de la relation (entier)
```

## Explorations utiles

### En Python (pandas) — comprendre le jeu de données
```python
import pandas as pd
nodes = pd.read_csv("nodes.csv")
edges = pd.read_csv("edges.csv")

# Répartition des types de nœuds
print(nodes["type"].value_counts())

# Répartition des relations
print(edges["relation"].value_counts())

# Nœuds les plus connectés (hubs)
deg = pd.concat([edges["source"], edges["target"]]).value_counts()
print(deg.head(10))
```

### Charger dans une base graphe (Neo4j — Cypher)
```cypher
// Importer les nœuds
LOAD CSV WITH HEADERS FROM 'file:///nodes.csv' AS row
CREATE (:Entity {id: row.id, label: row.label, type: row.type,
                 a1: row.attribute1, a2: row.attribute2, a3: row.attribute3});

// Importer les relations
LOAD CSV WITH HEADERS FROM 'file:///edges.csv' AS row
MATCH (s:Entity {id: row.source}), (t:Entity {id: row.target})
CREATE (s)-[:REL {type: row.relation, weight: toInteger(row.weight)}]->(t);

// Exemple : tous les tickets assignés à un utilisateur
MATCH (u:Entity {type:'user'})<-[r {type:'assigné_à'}]-(t:Entity {type:'ticket'})
RETURN u.label, count(t) AS tickets ORDER BY tickets DESC LIMIT 10;
```

## Aperçu de l'interface
Ouvrir `ticketing_graph.html` dans un navigateur (ou la [démo en ligne](https://pierre-portfolio.github.io/Ticketing-Visualisation-Interactive-Data/ticketing_graph.html)) : le graphe s'affiche sur fond sombre, chaque type de nœud ayant sa couleur. Cliquer un nœud met en évidence son voisinage et grise le reste.

## Auteur
- [Pierre-Portfolio](https://github.com/Pierre-Portfolio/)

---

<p align="center">Projet réalisé en 2026.</p>
