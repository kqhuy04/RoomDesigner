import os
import json
import networkx as nx
from collections import Counter

# ==========================================
# 🔹 1. KNOWLEDGE BASE & CONFIGURATION
# ==========================================

STYLE_MAP = {
    "minimalist": "modern", "contemporary": "modern", "scandinavian": "modern",
    "japandi": "modern", "modern": "modern",
    "vintage": "classic", "retro": "classic", "luxury": "classic",
    "industrial": "industrial", "loft": "industrial",
    "rustic": "nature", "boho": "nature"
}

SOFT_COMPATIBLE_STYLES = {
    tuple(sorted(["modern", "industrial"])): 0.7,
    tuple(sorted(["modern", "nature"])): 0.5,
    tuple(sorted(["classic", "luxury"])): 0.8,
    tuple(sorted(["modern", "classic"])): 0.2
}

MATERIAL_GROUPS = {
    "wood": ["oak", "walnut", "pine", "wood", "mdf", "veneer"],
    "metal": ["iron", "steel", "chrome", "aluminum"],
    "fabric": ["linen", "velvet", "leather", "cotton"]
}

VALID_RELATIONS_RAW = {
    "sofa": ["coffee_table", "tv_stand", "rug", "lamp", "armchair"],
    "bed": ["nightstand", "wardrobe", "rug", "lamp", "desk"],
    "dining_table": ["chair", "kitchen_cabinet", "refrigerator", "lamp"],
    "tv_stand": ["tv", "speaker"],
    "desk": ["chair", "lamp", "bookshelf"],
    "wardrobe": ["mirror"],
    "toilet": ["sink", "bathtub", "mirror", "cabinet"]
}

WEIGHT_FACTORS = {
    "style": 0.4,
    "color": 0.2,
    "material": 0.2,
    "dimension": 0.2
}

WEIGHT_THRESHOLD = 15


# ==========================================
# 🔹 2. HELPER FUNCTIONS
# ==========================================

def build_symmetric_relations(raw):
    sym = {}
    for k, vs in raw.items():
        sym.setdefault(k, set()).update(vs)
        for v in vs:
            sym.setdefault(v, set()).add(k)
    return sym

VALID_RELATIONS = build_symmetric_relations(VALID_RELATIONS_RAW)


def get_group_similarity(val1, val2, group_dict):
    if not val1 or not val2:
        return 0.2
    if val1 == val2:
        return 1.0
    for members in group_dict.values():
        if val1 in members and val2 in members:
            return 0.8
    return 0.0


def get_style_score(m1, m2):
    s1, s2 = m1.get('style'), m2.get('style')

    if not s1 or not s2:
        return 0.2

    g1, g2 = STYLE_MAP.get(s1), STYLE_MAP.get(s2)

    if not g1 or not g2:
        return 0.2

    if g1 == g2:
        return 1.0 if s1 == s2 else 0.9

    key = tuple(sorted([g1, g2]))
    return SOFT_COMPATIBLE_STYLES.get(key, 0.0)


def get_dimensions_from_json(json_path):
    try:
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f).get('dimensions', {})
    except:
        pass
    return {"width": 0, "length": 0, "height": 0}


# ==========================================
# 🔹 3. SCORING ENGINE
# ==========================================

def calculate_edge_weight(node1, node2):
    m1, m2 = node1['meta'], node2['meta']

    # Style
    style_sim = get_style_score(m1, m2)

    # Color
    c1 = {c.strip() for c in m1.get('color', '').split(',') if c.strip()}
    c2 = {c.strip() for c in m2.get('color', '').split(',') if c.strip()}
    color_sim = 1.0 if c1 & c2 else 0.0

    # Material
    mat1, mat2 = m1.get('material'), m2.get('material')
    mat_sim = get_group_similarity(mat1, mat2, MATERIAL_GROUPS)

    # Dimension (symmetric rule)
    dim_sim = 1.0
    d1, d2 = node1.get('dimensions', {}), node2.get('dimensions', {})

    if d1 and d2:
        cats = {node1['category'], node2['category']}

        if cats == {'sofa', 'coffee_table'}:
            sofa = node1 if node1['category'] == 'sofa' else node2
            table = node2 if node2['category'] == 'coffee_table' else node1

            dim_sim = 1.0 if table['dimensions'].get('height', 0) <= sofa['dimensions'].get('height', 0) else 0.1

    total = (
        style_sim * WEIGHT_FACTORS["style"] +
        color_sim * WEIGHT_FACTORS["color"] +
        mat_sim * WEIGHT_FACTORS["material"] +
        dim_sim * WEIGHT_FACTORS["dimension"]
    ) * 100

    return total if style_sim > 0.1 else total - 10


# ==========================================
# 🔹 4. GRAPH BUILDER
# ==========================================

def build_scene_graph(candidates_dict):
    G = nx.Graph()

    for cat, items in candidates_dict.items():
        for item in items:
            dims = get_dimensions_from_json(item.get('path', ''))
            G.add_node(
                f"{cat}_{item['uid']}",
                category=cat,
                uid=item['uid'],
                meta={k: str(v).lower().strip() for k, v in item.get('meta', {}).items()},
                dimensions=dims
            )

    nodes = list(G.nodes(data=True))

    for i, (id_a, data_a) in enumerate(nodes):
        for id_b, data_b in nodes[i+1:]:
            if data_b['category'] in VALID_RELATIONS.get(data_a['category'], []):
                weight = calculate_edge_weight(data_a, data_b)
                if weight > WEIGHT_THRESHOLD:
                    G.add_edge(id_a, id_b, weight=weight)

    return G


# ==========================================
# 🔹 5. ROOM CONSTRAINTS
# ==========================================

def check_room_capacity(cand_node, selected_nodes_data, room_dim):
    if not room_dim:
        return True

    r_w, r_l = room_dim.get('width', 9999), room_dim.get('length', 9999)
    r_area = r_w * r_l

    c_w = cand_node['dimensions'].get('width', 0)
    c_l = cand_node['dimensions'].get('length', 0)

    if c_w > r_w or c_l > r_l:
        return False

    IGNORE_AREA_TYPES = {"rug", "lamp", "mirror"}

    current_area = sum(
        n['dimensions'].get('width', 0) * n['dimensions'].get('length', 0)
        for n in selected_nodes_data
        if n['category'] not in IGNORE_AREA_TYPES
    )

    if cand_node['category'] not in IGNORE_AREA_TYPES:
        current_area += c_w * c_l

    return current_area <= r_area * 0.5


# ==========================================
# 🔹 6. CORE SELECTION
# ==========================================

def select_best_core(G, core_nodes):
    def score(n):
        edges = list(G.edges(n, data=True))
        if not edges:
            return 0
        return sum(d['weight'] for _, _, d in edges) / len(edges)

    return max(core_nodes, key=score)


# ==========================================
# 🔹 7. SOLVER
# ==========================================

def solve_optimal_subgraph(G, room_type, ROOM_RULES_CONFIG, room_dimensions=None):
    rules = ROOM_RULES_CONFIG.get(room_type)
    if not rules:
        return []

    core_nodes = [n for n, d in G.nodes(data=True) if d['category'] == rules["core"]]
    if not core_nodes:
        return []

    best_core = select_best_core(G, core_nodes)

    selected_ids = [best_core]
    selected_nodes_data = [G.nodes[best_core]]

    color_history = Counter([
        c for c in G.nodes[best_core]['meta'].get('color', '').split(',') if c.strip()
    ])

    all_cats = rules["required"] + rules["optional"]

    for cat in [c for c in all_cats if c not in {n['category'] for n in selected_nodes_data}]:
        candidates = [n for n, d in G.nodes(data=True) if d['category'] == cat]
        if not candidates:
            continue

        best_cand, max_score = None, -999

        for cand in candidates:
            cand_data = G.nodes[cand]

            if not check_room_capacity(cand_data, selected_nodes_data, room_dimensions):
                continue

            rel_score = sum(
                G[cand][sel]['weight'] if G.has_edge(cand, sel) else -5
                for sel in selected_ids
            )

            for c in [c for c in cand_data['meta'].get('color', '').split(',') if c.strip()]:
                if color_history[c] >= 2:
                    rel_score -= 15

            if rel_score > max_score:
                max_score, best_cand = rel_score, cand

        if best_cand and (max_score > 0 or cat in rules["required"]):
            selected_ids.append(best_cand)
            selected_nodes_data.append(G.nodes[best_cand])

            color_history.update([
                c for c in G.nodes[best_cand]['meta'].get('color', '').split(',') if c.strip()
            ])

    return selected_nodes_data