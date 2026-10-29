"""Coordinates of every entity for the web page's star map (D128).

Each entity type is a nebula. Inside it, FastRP (a random projection of the adjacency, mean of
the neighbours over a few steps) places connected entities near each other, and each body
region (from HPO organ systems, MONDO body systems, and for a drug the region of most of its
indications) gathers on the same bearing in every nebula. Positions show closeness in the
graph, not medical meaning.
"""

import base64
import hashlib

import numpy as np

TYPES = ['Drug', 'Disease', 'Phenotype', 'Gene']
CENTRES = np.array([[-1.0, 0.15, 0.2], [1.0, 0.0, -0.1], [0.05, -0.15, 1.0], [0.0, 0.1, -1.0]]) * 0.95
REGIONS = ['Brain and nerves', 'Eyes', 'Ears and balance', 'Head, nose and teeth', 'Breathing',
           'Heart and circulation', 'Blood', 'Immune system', 'Digestion and liver', 'Metabolism and fluids',
           'Hormones', 'Kidneys and urinary tract', 'Reproduction', 'Skin and nails', 'Muscles and bones',
           'Growth and development', 'General', 'Tumours']
GENERAL = REGIONS.index('General')   # General and Tumours only when no body system is closer
# Children of HP:0000118 (and the two branches of the genitourinary system).
HPO = {'HP:0000707': 0, 'HP:0000478': 1, 'HP:0000598': 2, 'HP:0000152': 3, 'HP:0001608': 3, 'HP:0002086': 4,
       'HP:0045027': 4, 'HP:0001626': 5, 'HP:0001871': 6, 'HP:0002715': 7, 'HP:0025031': 8, 'HP:0001939': 9,
       'HP:0000818': 10, 'HP:0000079': 11, 'HP:0000078': 12, 'HP:0000769': 12, 'HP:0001574': 13, 'HP:0033127': 14,
       'HP:0040064': 14, 'HP:0001507': 15, 'HP:0001197': 15, 'HP:0025142': 16, 'HP:0002664': 17}
# Children of "disease by body system or component", nutritional and metabolic disease, cancer.
MONDO = {'MONDO:0005071': 0, 'MONDO:0024458': 1, 'MONDO:0002022': 1, 'MONDO:0002409': 2, 'MONDO:0024623': 3,
         'MONDO:0006858': 3, 'MONDO:0005087': 4, 'MONDO:0004995': 5, 'MONDO:0005570': 6, 'MONDO:0005046': 7,
         'MONDO:0004335': 8, 'MONDO:0005137': 9, 'MONDO:0005066': 9, 'MONDO:0005151': 10, 'MONDO:0002118': 11,
         'MONDO:0005039': 12, 'MONDO:0002657': 12, 'MONDO:0002051': 13, 'MONDO:0002081': 14, 'MONDO:0003900': 14,
         'MONDO:0045024': 17}


def nearest(start: str, terms: dict, table: dict) -> int:
    """The region of the closest classified ancestor, -1 when there is none."""
    frontier, seen = [start], {start}
    while frontier:
        hits = sorted({table[t] for t in frontier if t in table}, key=lambda r: (r >= GENERAL, r))
        if hits:
            return hits[0]
        frontier = [p for t in frontier if t in terms for p in terms[t].parents if p not in seen]
        seen.update(frontier)
    return -1


def regions(catalog: list[dict], edges: list[dict], hp: dict, mondo: dict) -> np.ndarray:
    index = {e['uid']: i for i, e in enumerate(catalog)}
    region = np.full(len(catalog), -1, dtype=np.int64)
    for i, e in enumerate(catalog):
        if e['label'] == 'Phenotype':
            region[i] = nearest('HP:' + e['node_id'].removeprefix('HP:').zfill(7), hp, HPO)
        elif e['label'] == 'Disease':
            ids = ['MONDO:' + part.removeprefix('MONDO:').zfill(7) for part in e['node_id'].split('_')]
            region[i] = next((r for r in (nearest(x, mondo, MONDO) for x in ids) if r >= 0), -1)
    votes: dict[int, list[int]] = {}
    for e in edges:
        if e['type'] != 'INDICATED_FOR' or e['a'] not in index or e['b'] not in index:
            continue
        drug, disease = index[e['a']], index[e['b']]
        if catalog[drug]['label'] != 'Drug':
            drug, disease = disease, drug
        if catalog[drug]['label'] == 'Drug' and region[disease] >= 0:
            votes.setdefault(drug, []).append(int(region[disease]))
    for drug, found in votes.items():
        region[drug] = np.bincount(found).argmax()
    return region


def fastrp(n: int, pairs: np.ndarray, dim: int = 48, seed: int = 7) -> np.ndarray:
    src, dst = np.concatenate([pairs[:, 0], pairs[:, 1]]), np.concatenate([pairs[:, 1], pairs[:, 0]])
    deg = np.bincount(src, minlength=n).astype(np.float64) + 1
    x = np.random.default_rng(seed).choice([-1.0, 0.0, 1.0], size=(n, dim), p=[1 / 6, 2 / 3, 1 / 6])
    weight = 1.0 / deg[src]

    def propagate(v):
        # The mean of the neighbours and itself, so hubs do not swamp everything.
        out = np.empty_like(v)
        for d in range(v.shape[1]):
            out[:, d] = np.bincount(dst, weights=v[src, d] * weight, minlength=n)
        return (out + v / deg[:, None]) / 2

    emb = np.zeros_like(x)
    for step_weight in (0.0, 1.0, 1.0, 0.6):
        x = propagate(x)
        if step_weight:
            emb += step_weight * x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-9)
    return emb / (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9)


def positions(types: np.ndarray, region: np.ndarray, emb: np.ndarray, seed: int = 7) -> np.ndarray:
    largest = max(int((types == t).sum()) for t in range(len(TYPES))) or 1
    pos = np.zeros((len(types), 3))
    for t in range(len(TYPES)):
        m = types == t
        if m.sum() < 3:
            pos[m] = CENTRES[t]
            continue
        e = emb[m] - emb[m].mean(axis=0)
        _, _, vt = np.linalg.svd(e, full_matrices=False)
        p = e @ vt[:3].T
        p /= np.percentile(np.linalg.norm(p, axis=1), 90) + 1e-9
        # A dense core spread into a softer disk.
        r = np.linalg.norm(p, axis=1)
        rank = r.argsort().argsort() / max(1, len(r) - 1)
        p *= ((0.06 + rank ** 0.75) / (r + 1e-9))[:, None]
        # Each region on its bearing; the unclassified stay in the middle.
        has = region[m] >= 0
        bearing = 2 * np.pi * region[m][has] / len(REGIONS)
        p[has] = 0.42 * p[has] + 0.58 * np.stack([0.68 * np.cos(bearing), np.zeros(has.sum()), 0.68 * np.sin(bearing)], 1)
        p[:, 1] *= 0.55
        # A gentle spiral twist.
        twist = 2.2 * np.linalg.norm(p[:, [0, 2]], axis=1)
        c, s = np.cos(twist), np.sin(twist)
        p[:, 0], p[:, 2] = c * p[:, 0] - s * p[:, 2], s * p[:, 0] + c * p[:, 2]
        pos[m] = p * 0.82 * (m.sum() / largest) ** (1 / 3) + CENTRES[t]
    return pos + np.random.default_rng(seed).normal(0, 0.006, pos.shape)


def b64(array: np.ndarray) -> str:
    return base64.b64encode(array.tobytes()).decode()


def build(catalog: list[dict], edges: list[dict], hp: dict, mondo: dict) -> tuple[dict, list[str]]:
    """The page's payload (positions, types, regions and their centres) and the uid of each point."""
    index = {e['uid']: i for i, e in enumerate(catalog)}
    types = np.array([TYPES.index(e['label']) for e in catalog], dtype=np.uint8)
    pairs = np.array([(index[e['a']], index[e['b']]) for e in edges if e['a'] in index and e['b'] in index],
                     dtype=np.int64).reshape(-1, 2)
    region = regions(catalog, edges, hp, mondo)
    pos = positions(types, region, fastrp(len(catalog), pairs))
    areas = []
    for t in range(len(TYPES)):
        for r, name in enumerate(REGIONS):
            m = (types == t) & (region == r)
            if m.sum() >= 40:
                areas.append([t, name, *np.round(pos[m].mean(axis=0), 4).tolist(), int(m.sum())])
    uids = [e['uid'] for e in catalog]
    payload = {'count': len(catalog), 'types': TYPES, 'regions': REGIONS, 'areas': areas,
               'pos': b64(pos.astype(np.float32)), 'type': b64(types), 'region': b64((region + 1).astype(np.uint8)),
               'catalog_sha256': hashlib.sha256('\n'.join(uids).encode()).hexdigest()}
    return payload, uids
