# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Pure-Python port of the official WorfBench evaluator (WorfEval).

Reimplements ``evaluator/graph_evaluator.py`` from zjunlp/WorfBench (MIT)
without numpy/networkx/sentence-transformers dependencies:

- ``t_eval_nodes``: enumerate gold topological orders (cap 20, shortcut for
  graphs with >= 10 nodes incl. START/END markers), match predicted nodes to
  each order and score the best Longest-Increasing-Subsequence alignment;
- ``t_eval_graph``: max-weight node matching, then precision/recall from the
  largest connected component over matched nodes joined by public edges;

Node similarity: the official protocol embeds nodes with
``all-mpnet-base-v2`` (cosine, threshold 0.6). That model is not available
offline, so ``char_ngram_cosine`` (character bigram TF cosine) is the default
substitute — a stricter approximation, reported numbers are therefore a lower
bound relative to the published protocol. Pass a custom ``sim_fn`` to swap in
embeddings when they become available.

The index-space public-edge comparison of the official implementation is kept
for ``eval_graph`` (``mode="official"``); a semantically-intended variant
comparing mapped pred edges against gold edges is provided as
``mode="mapped"``. Both are reported side by side.
"""

import re
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

START_MARK = "START"
END_MARK = "END"

SimFn = Callable[[str, str], float]


# ---------------------------------------------------------------------------
# node similarity
# ---------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def char_ngram_cosine(a: str, b: str, n: int = 2) -> float:
    """Cosine over character n-gram count vectors of normalized text."""
    left = normalize_text(a)
    right = normalize_text(b)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0

    def counts(text: str) -> Dict[str, int]:
        grams: Dict[str, int] = defaultdict(int)
        padded = f" {text} "
        for i in range(len(padded) - n + 1):
            grams[padded[i:i + n]] += 1
        return grams

    left_counts, right_counts = counts(left), counts(right)
    dot = sum(value * right_counts.get(key, 0) for key, value in left_counts.items())
    if dot == 0:
        return 0.0
    left_norm = sum(value * value for value in left_counts.values()) ** 0.5
    right_norm = sum(value * value for value in right_counts.values()) ** 0.5
    return dot / (left_norm * right_norm)


# ---------------------------------------------------------------------------
# bipartite max-weight matching (exact DP for small sides, greedy fallback)
# ---------------------------------------------------------------------------


def match_nodes(
    pred_nodes: List[str],
    gt_nodes: List[str],
    sim_fn: SimFn = char_ngram_cosine,
    threshold: float = 0.6,
) -> Dict[int, int]:
    """Map each pred index to its matched gt index (-1 when unmatched).

    Mirrors the official ``match_node``: candidate pairs need similarity
    strictly above the threshold; among them the maximum total weight is
    selected (official code uses networkx max_weight_matching).
    """
    len_pred, len_gt = len(pred_nodes), len(gt_nodes)
    mapping: Dict[int, int] = {i: -1 for i in range(len_pred)}
    if len_pred == 0 or len_gt == 0:
        return mapping

    weights: List[List[float]] = [
        [sim_fn(pred, gt) for gt in gt_nodes] for pred in pred_nodes
    ]
    edges: List[List[Tuple[int, float]]] = []
    for i in range(len_pred):
        edges.append(
            [(j, weights[i][j]) for j in range(len_gt) if weights[i][j] > threshold]
        )

    small_side = min(len_pred, len_gt)
    if small_side <= 12:
        mapping = _exact_max_weight(len_pred, len_gt, edges)
    else:
        mapping = _greedy_max_weight(len_pred, edges)
    return {i: mapping.get(i, -1) for i in range(len_pred)}


def _exact_max_weight(
    len_pred: int, len_gt: int, edges: List[List[Tuple[int, float]]]
) -> Dict[int, int]:
    """Exact assignment DP over gt-side subsets (small len_gt)."""
    best: Dict[int, Tuple[float, List[Tuple[int, int]]]] = {0: (0.0, [])}
    for pred_index in range(len_pred):
        nxt: Dict[int, Tuple[float, List[Tuple[int, int]]]] = {}
        for mask, (weight, pairs) in best.items():
            # skip this pred node
            if mask not in nxt or nxt[mask][0] < weight:
                nxt[mask] = (weight, pairs)
            for gt_index, w in edges[pred_index]:
                bit = 1 << gt_index
                if mask & bit:
                    continue
                new_mask = mask | bit
                cand = (weight + w, pairs + [(pred_index, gt_index)])
                if new_mask not in nxt or nxt[new_mask][0] < cand[0]:
                    nxt[new_mask] = cand
        best = nxt
    # best assignment = entry with max weight overall
    weight, pairs = max(best.values(), key=lambda item: item[0])
    return dict(pairs)


def _greedy_max_weight(len_pred: int, edges: List[List[Tuple[int, float]]]) -> Dict[int, int]:
    """Greedy fallback for large graphs: take heaviest pairs first."""
    candidates: List[Tuple[float, int, int]] = []
    for pred_index, pairs in enumerate(edges):
        for gt_index, w in pairs:
            candidates.append((w, pred_index, gt_index))
    candidates.sort(reverse=True)
    assigned: Dict[int, int] = {}
    used_gt: Set[int] = set()
    for _, pred_index, gt_index in candidates:
        if pred_index in assigned or gt_index in used_gt:
            continue
        assigned[pred_index] = gt_index
        used_gt.add(gt_index)
    return assigned


# ---------------------------------------------------------------------------
# gold topological orders (official shortcut + cap preserved)
# ---------------------------------------------------------------------------


def all_topological_sorts(
    nodes: Sequence[str], edges: Sequence[Tuple[int, int]], max_sorts: int = 20
) -> List[List[str]]:
    """Enumerate topological orders of the index graph.

    Official behavior: graphs with >= 10 nodes (incl. START/END markers) skip
    enumeration and yield the listed order once; enumeration results are
    capped at the first 20.
    """
    total = len(nodes)
    if total >= 10:
        return [list(nodes)]
    successors: Dict[int, List[int]] = {i: [] for i in range(total)}
    indegree: Dict[int, int] = {i: 0 for i in range(total)}
    for u, v in edges:
        if u in successors and v in indegree:
            successors[u].append(v)
            indegree[v] += 1
    results: List[List[int]] = []

    def backtrack(order: List[int], remaining: Set[int]) -> None:
        if len(results) >= max_sorts:
            return
        if not remaining:
            results.append(list(order))
            return
        for node in sorted(remaining):
            if indegree[node] == 0:
                order.append(node)
                for succ in successors[node]:
                    indegree[succ] -= 1
                backtrack(order, remaining - {node})
                for succ in successors[node]:
                    indegree[succ] += 1
                order.pop()
                if len(results) >= max_sorts:
                    return

    backtrack([], set(range(total)))
    return [[nodes[i] for i in order] for order in results]


# ---------------------------------------------------------------------------
# official metrics
# ---------------------------------------------------------------------------


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0


def eval_plan(
    pred_plan: List[str], gt_plan: List[str], sim_fn: SimFn = char_ngram_cosine,
    threshold: float = 0.6,
) -> Dict[str, float]:
    """Sequence metric with LIS alignment (official ``t_eval_plan``, order=True)."""
    mapping = match_nodes(pred_plan, gt_plan, sim_fn, threshold)
    len_pred, len_gt = len(pred_plan), len(gt_plan)
    if len_pred == 0 or len_gt == 0:
        return {"precision": 0.0, "recall": 0.0, "f1_score": 0.0}
    dp = [1.0] * len_pred
    for i in range(len_pred):
        for j in range(i):
            if mapping[i] == -1 or mapping[j] == -1:
                continue
            if mapping[i] > mapping[j]:
                dp[i] = max(dp[i], dp[j] + 1)
    correct = int(max(dp))
    recall = correct / len_gt
    precision = correct / len_pred
    return {"precision": precision, "recall": recall, "f1_score": _f1(precision, recall)}


def eval_nodes(
    pred_nodes: List[str],
    gt_nodes: List[str],
    gt_edges: Sequence[Tuple[int, int]],
    sim_fn: SimFn = char_ngram_cosine,
    threshold: float = 0.6,
) -> Dict[str, float]:
    """Best topological-order sequence metric (official ``t_eval_nodes``)."""
    orders = all_topological_sorts(gt_nodes, gt_edges)
    best = {"precision": 0.0, "recall": 0.0, "f1_score": 0.0}
    for order in orders:
        result = eval_plan(pred_nodes, order, sim_fn, threshold)
        if result["f1_score"] > best["f1_score"]:
            best = result
    return best


def _largest_component_size(nodes: Sequence[int], edges: Sequence[Tuple[int, int]]) -> int:
    if not nodes:
        return 0
    parent = {node: node for node in nodes}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for u, v in edges:
        if u in parent and v in parent:
            ru, rv = find(u), find(v)
            if ru != rv:
                parent[ru] = rv
    counts: Dict[int, int] = defaultdict(int)
    for node in nodes:
        counts[find(node)] += 1
    return max(counts.values())


def eval_graph(
    pred_nodes: List[str],
    pred_edges: Sequence[Tuple[int, int]],
    gt_nodes: List[str],
    gt_edges: Sequence[Tuple[int, int]],
    sim_fn: SimFn = char_ngram_cosine,
    threshold: float = 0.6,
    mode: str = "official",
) -> Dict[str, float]:
    """Subgraph metric (official ``t_eval_graph``).

    ``mode="official"`` keeps the index-space public-edge comparison of the
    reference implementation; ``mode="mapped"`` compares mapped pred edges
    against gold edges (the semantically intended variant).
    """
    mapping = match_nodes(pred_nodes, gt_nodes, sim_fn, threshold)
    if not pred_nodes or not gt_nodes:
        return {"precision": 0.0, "recall": 0.0, "f1_score": 0.0}

    matched_pred = [i for i, j in mapping.items() if j != -1]
    matched_gt = [mapping[i] for i in matched_pred]

    matched_pred_edges = [
        (u, v) for u, v in pred_edges if u in matched_pred and v in matched_pred
    ]
    matched_gt_edges = [
        (u, v) for u, v in gt_edges if u in matched_gt and v in matched_gt
    ]
    if mode == "mapped":
        mapped_pred_edges = [(mapping[u], mapping[v]) for u, v in matched_pred_edges]
        public_pred = [e for e in mapped_pred_edges if e in set(matched_gt_edges)]
        public_gt = list(public_pred)  # already in gt index space
    else:
        pred_set = set(matched_pred_edges)
        public_pred = [e for e in matched_pred_edges if e in set(matched_gt_edges)]
        public_gt = [e for e in matched_gt_edges if e in pred_set]

    pred_lcc = _largest_component_size(matched_pred, public_pred)
    gt_lcc = _largest_component_size(matched_gt, public_gt)
    precision = pred_lcc / len(pred_nodes)
    recall = gt_lcc / len(gt_nodes)
    return {"precision": precision, "recall": recall, "f1_score": _f1(precision, recall)}
