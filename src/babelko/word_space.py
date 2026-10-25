"""Build a bounded, local-only 3D word graph from PDF text.

This module runs in a separate process from the Qt workbench. Positions are a
visual encoding of observed word co-occurrence, not semantic embeddings.
"""

import argparse
from collections import Counter, defaultdict
import json
import math
import os
from pathlib import Path
import re

import networkx as nx
import numpy as np
import pymupdf


REVISION = "word-space-1"
MAX_TERMS = 480
MAX_GRAPH_EDGES = 1400
MAX_VISIBLE_EDGES = 280
TOKEN = re.compile(r"[^\W\d_][\w]*", re.UNICODE)
STOPWORDS = frozenset("""
a about above after again against all am an and any are as at be because been before
being below between both but by can cannot could did do does doing down during each
few for from further had has have having he her here hers herself him himself his how
i if in into is it its itself just may me more most my myself no nor not of off on
once only or other our ours ourselves out over own same she should so some such than
that the their theirs them themselves then there these they this those through to too
under until up very was we were what when where which while who whom why will with
would you your yours yourself yourselves also however therefore thus using used use
et al one two three four five six seven eight nine ten
""".split())


def _tokens(raw):
    result = []
    for match in TOKEN.finditer(raw):
        word = match.group().casefold()
        if (len(word) >= 3 or (len(word) >= 2 and match.group().isupper())) and word not in STOPWORDS:
            result.append(word)
    return result


def _words_for_page(page, page_number, ocr_dir):
    native = page.get_text("words", sort=True)
    if len(native) >= 5 or not ocr_dir:
        return native, False
    replacement = ocr_dir / f"page-{page_number}.pdf"
    if not replacement.is_file():
        return native, False
    try:
        with pymupdf.open(replacement) as ocr:
            recognized = ocr[0].get_text("words", sort=True)
        if len(recognized) > len(native):
            return recognized, True
    except (OSError, RuntimeError, ValueError):
        pass
    return native, False


def _cooccurrences(blocks, vocabulary, counts):
    selected = set(vocabulary)
    pairs = Counter()
    for block in blocks:
        retained = [word for word in block if word in selected]
        for index, word in enumerate(retained):
            for distance in range(1, 6):
                later = index + distance
                if later >= len(retained):
                    break
                other = retained[later]
                if word != other:
                    pairs[tuple(sorted((word, other)))] += 1 / distance
    scored = [(a, b, weight / math.sqrt(counts[a] * counts[b]))
              for (a, b), weight in pairs.items()]
    scored.sort(key=lambda row: (-row[2], row[0], row[1]))
    return scored[:MAX_GRAPH_EDGES]


def _layout(vocabulary, edges, mean_page, page_count):
    graph = nx.Graph()
    graph.add_nodes_from(vocabulary)
    graph.add_weighted_edges_from(edges)
    if len(vocabulary) == 1:
        positions = {vocabulary[0]: np.zeros(3)}
    else:
        positions = nx.spring_layout(graph, dim=3, seed=18, iterations=65,
                                     weight="weight", scale=1.0)
    if edges:
        communities = nx.community.louvain_communities(graph, weight="weight", seed=18)
    else:
        communities = [set(vocabulary)]
    communities.sort(key=lambda group: (-len(group), min(group)))
    cluster = {word: index for index, group in enumerate(communities) for word in group}
    coordinates = {}
    for word in vocabulary:
        x, y, z = positions[word]
        chronology = (mean_page[word] / max(1, page_count - 1) - 0.5) * 2
        coordinates[word] = (round(float(x) * 255, 2),
                             round(float(y) * 195, 2),
                             round(float(z) * 125 + chronology * 100, 2))
    return coordinates, cluster, graph


def _edge_geometry(left, right):
    a = np.asarray(left, dtype=float)
    b = np.asarray(right, dtype=float)
    diff = b - a
    length = float(np.linalg.norm(diff))
    direction = diff / max(length, 1e-6)
    axis = np.cross(np.array([0.0, 1.0, 0.0]), direction)
    quaternion = np.array([1.0 + direction[1], *axis])
    norm = float(np.linalg.norm(quaternion))
    if norm < 1e-6:
        quaternion = np.array([0.0, 0.0, 0.0, 1.0])
    else:
        quaternion /= norm
    middle = (a + b) / 2
    return [round(float(value), 3) for value in middle], round(length, 3), [
        round(float(value), 5) for value in quaternion]


def build(source, *, ocr_dir=None, max_terms=MAX_TERMS):
    """Extract word occurrences and lay out a bounded co-occurrence graph."""
    source = Path(source)
    ocr_dir = Path(ocr_dir) if ocr_dir else None
    counts = Counter()
    pages = defaultdict(set)
    page_sum = Counter()
    blocks = []
    processed_tokens = 0
    ocr_pages = 0
    blank_pages = 0
    with pymupdf.open(source) as document:
        total_pages = len(document)
        for page_index, page in enumerate(document):
            raw_words, used_ocr = _words_for_page(page, page_index + 1, ocr_dir)
            ocr_pages += int(used_ocr)
            if not raw_words:
                blank_pages += 1
            grouped = defaultdict(list)
            for raw in raw_words:
                for word in _tokens(str(raw[4])):
                    grouped[raw[5]].append(word)
                    counts[word] += 1
                    pages[word].add(page_index + 1)
                    page_sum[word] += page_index
                    processed_tokens += 1
            blocks.extend(group for group in grouped.values() if group)

    vocabulary = sorted(counts, key=lambda word: (
        -counts[word] * math.log1p(len(pages[word]) + 1), -counts[word], word))[:max_terms]
    if not vocabulary:
        return {"revision": REVISION, "status": "empty", "total_pages": total_pages,
                "analyzed_tokens": 0, "unique_words": 0, "ocr_pages": ocr_pages,
                "blank_pages": blank_pages, "points": [], "edges": [], "clusters": []}

    scored_edges = _cooccurrences(blocks, vocabulary, counts)
    mean_page = {word: page_sum[word] / counts[word] for word in vocabulary}
    positions, communities, graph = _layout(vocabulary, scored_edges, mean_page, total_pages)
    indices = {word: index for index, word in enumerate(vocabulary)}
    palette = ["#70EEE0", "#C6A6FF", "#FFD482", "#FF9F8D",
               "#86BDFF", "#9FE6A9", "#EBA5D3", "#B7D0E0"]
    points = []
    for word in vocabulary:
        x, y, z = positions[word]
        neighbors = sorted(graph[word].items(), key=lambda item: -item[1]["weight"])[:5]
        points.append({"word": word, "count": counts[word], "page_hits": len(pages[word]),
                       "first_page": min(pages[word]), "last_page": max(pages[word]),
                       "x": x, "y": y, "z": z,
                       "radius": round(min(9.0, 2.1 + math.sqrt(counts[word]) * 0.72), 2),
                       "color": palette[communities[word] % len(palette)],
                       "cluster": communities[word],
                       "neighbors": [other for other, _ in neighbors]})

    clusters = []
    for cluster_id in sorted(set(communities.values()))[:8]:
        members = [positions[word] for word in vocabulary if communities[word] == cluster_id]
        center = np.mean(np.asarray(members), axis=0)
        spread = np.percentile(np.linalg.norm(np.asarray(members) - center, axis=1), 70)
        clusters.append({"id": cluster_id, "x": round(float(center[0]), 2),
                         "y": round(float(center[1]), 2), "z": round(float(center[2]), 2),
                         "radius": round(float(min(160, max(35, spread + 18))), 2),
                         "count": len(members), "color": palette[cluster_id % len(palette)]})

    visible_edges = []
    for a, b, weight in scored_edges[:MAX_VISIBLE_EDGES]:
        middle, length, rotation = _edge_geometry(positions[a], positions[b])
        visible_edges.append({"a": indices[a], "b": indices[b],
                              "x": middle[0], "y": middle[1], "z": middle[2],
                              "length": length, "qw": rotation[0], "qx": rotation[1],
                              "qy": rotation[2], "qz": rotation[3],
                              "strength": round(weight, 4)})
    return {"revision": REVISION, "status": "ready", "total_pages": total_pages,
            "analyzed_tokens": processed_tokens, "unique_words": len(counts),
            "ocr_pages": ocr_pages, "blank_pages": blank_pages,
            "points": points, "edges": visible_edges, "clusters": clusters,
            "scope": "Top terms from local PDF text; distance reflects observed co-occurrence, not meaning"}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--ocr-dir")
    args = parser.parse_args(argv)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result = build(args.source, ocr_dir=args.ocr_dir)
    temporary = output.with_name(f"{output.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
