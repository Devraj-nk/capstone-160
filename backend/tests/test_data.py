"""Curated sample posts used to exercise the pipeline end-to-end.

Not real social media data — hand-written stand-ins for the kinds of posts
the crisis-monitoring pipeline is meant to handle, covering the specific
behaviours each stage is responsible for.
"""

from __future__ import annotations

# --- Preprocessing: cleaning ---
MESSY_POST = "Flooding near MG Road! \U0001F30A\U0001F62D check https://maps.example.com/x cc @DisasterMgmt #Bangalore #flood!!"

# --- Preprocessing: invalid/empty ---
EMPTY_POSTS = ["   ", "@@@ !!! ###", ""]

# --- Preprocessing: repost tracking ---
ORIGINAL_POST = "Flooding near MG Road, send help!"
RETWEET_OF_ORIGINAL = "RT @someone: Flooding near MG Road, send help!"
SIMILAR_BUT_DISTINCT_POST = "Flooding near MG Road, water rising fast, please send help"

# --- Evidence: clustering input (already tagged with cluster_id, as the
# not-yet-implemented clustering layer would hand off) ---
CLUSTERED_POSTS = [
    {"id": "p1", "text": "Flooding near MG Road, water rising fast, need boats", "cluster_id": "flood-blr"},
    {"id": "p2", "text": "MG Road flooded, send rescue boats", "cluster_id": "flood-blr"},
    {"id": "p3", "text": "just had coffee, nice weather today", "cluster_id": "flood-blr"},
    {"id": "p4", "text": "Fire near the market, send fire trucks urgently", "cluster_id": "fire-market"},
    {"id": "p5", "text": "market fire spreading, need help", "cluster_id": "fire-market"},
]

# --- Evidence: privacy masking ---
PII_POST = "call me at 9876543210 or +91 98765 43210, I am near 123 MG Road, Bangalore"
