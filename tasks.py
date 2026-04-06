"""
tasks.py — The 3 SQL tasks with deterministic graders.

Each task has:
  - broken_query     : what the agent receives
  - schema_context   : table definitions
  - error_description: plain English hint about the bug
  - expected_behavior: what the correct query should do
  - grader()         : function(fixed_query: str) -> float (0.0 to 1.0)

Difficulty progression:
  EASY   — single syntax/logic bug, one table
  MEDIUM — N+1 / missing JOIN, two tables
  HARD   — performance + correctness issues, complex query
"""

import re
import sqlparse
from typing import Dict, Any


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

def normalize(sql: str) -> str:
    """Lowercase, strip extra whitespace, remove trailing semicolons."""
    return re.sub(r"\s+", " ", sql.strip().lower().rstrip(";"))


def contains_all(sql: str, *keywords: str) -> bool:
    s = normalize(sql)
    return all(k.lower() in s for k in keywords)


def does_not_contain(sql: str, *keywords: str) -> bool:
    s = normalize(sql)
    return all(k.lower() not in s for k in keywords)


# ─────────────────────────────────────────────────────────
# TASK 1 — EASY
# Bug: WHERE clause uses = instead of != (NOT NULL check wrong)
# ─────────────────────────────────────────────────────────

TASK_EASY = {
    "task_id": "easy_null_filter",
    "difficulty": "easy",
    "schema_context": """
Table: orders
  id          INTEGER PRIMARY KEY
  customer_id INTEGER
  status      TEXT          -- values: 'pending', 'shipped', 'cancelled'
  total       DECIMAL(10,2)
  created_at  TIMESTAMP
""".strip(),
    "broken_query": """
SELECT id, customer_id, total
FROM orders
WHERE status = NULL
ORDER BY created_at DESC;
""".strip(),
    "error_description": (
        "This query is trying to find orders where status has no value, "
        "but using '= NULL' never matches anything in SQL. "
        "NULL comparisons require a special syntax."
    ),
    "expected_behavior": (
        "Return all orders where the status column has no value (is NULL), "
        "sorted by creation date descending."
    ),
}


def grade_easy(fixed_query: str) -> tuple[float, str]:
    """
    Scoring:
      +0.5 if IS NULL is used instead of = NULL
      +0.3 if FROM orders is preserved
      +0.2 if ORDER BY created_at DESC is preserved
    """
    score = 0.0
    feedback = []

    s = normalize(fixed_query)

    # Core fix: IS NULL
    if "is null" in s:
        score += 0.5
        feedback.append("Correct: uses IS NULL.")
    elif "= null" in s or "=null" in s:
        feedback.append("Still using = NULL — this never returns rows in SQL.")
    else:
        feedback.append("Missing a NULL check entirely.")

    # Preserves table
    if "from orders" in s:
        score += 0.3
        feedback.append("Correct: queries the orders table.")
    else:
        feedback.append("Must query the orders table.")

    # Preserves sort
    if "order by created_at desc" in s:
        score += 0.2
        feedback.append("Correct: sorted by created_at DESC.")
    elif "order by" in s:
        score += 0.1
        feedback.append("Has ORDER BY but incorrect column/direction.")

    return round(score, 2), " | ".join(feedback)


# ─────────────────────────────────────────────────────────
# TASK 2 — MEDIUM
# Bug: fetching product name inside a loop (N+1 pattern)
#      simulated as a subquery inside SELECT vs proper JOIN
# ─────────────────────────────────────────────────────────

TASK_MEDIUM = {
    "task_id": "medium_n_plus_one",
    "difficulty": "medium",
    "schema_context": """
Table: order_items
  id         INTEGER PRIMARY KEY
  order_id   INTEGER
  product_id INTEGER
  quantity   INTEGER
  unit_price DECIMAL(10,2)

Table: products
  id         INTEGER PRIMARY KEY
  name       TEXT
  category   TEXT
  stock      INTEGER
""".strip(),
    "broken_query": """
SELECT
    oi.id,
    oi.order_id,
    oi.quantity,
    (SELECT name FROM products WHERE id = oi.product_id) AS product_name,
    (SELECT category FROM products WHERE id = oi.product_id) AS product_category
FROM order_items oi
WHERE oi.quantity > 5;
""".strip(),
    "error_description": (
        "This query runs a separate subquery for EACH row returned — once to get "
        "the product name and once to get the category. For 1000 order items this "
        "means 2000 extra queries. This is the classic N+1 problem. "
        "It should be rewritten to fetch all needed data in a single pass."
    ),
    "expected_behavior": (
        "Return order item id, order_id, quantity, product name, and product category "
        "for all order items with quantity > 5, using a single efficient query "
        "that joins the two tables."
    ),
}


def grade_medium(fixed_query: str) -> tuple[float, str]:
    """
    Scoring:
      +0.4 if uses JOIN (eliminates N+1)
      +0.2 if selects product name and category
      +0.2 if WHERE quantity > 5 preserved
      +0.2 if no correlated subqueries remain
    """
    score = 0.0
    feedback = []

    s = normalize(fixed_query)

    # Uses a JOIN
    if "join products" in s or "join products p" in s or "inner join products" in s:
        score += 0.4
        feedback.append("Correct: uses JOIN to eliminate N+1.")
    else:
        feedback.append("Must use a JOIN to fetch product data efficiently.")

    # Selects both name and category
    has_name = "name" in s
    has_category = "category" in s
    if has_name and has_category:
        score += 0.2
        feedback.append("Correct: selects both name and category.")
    elif has_name or has_category:
        score += 0.1
        feedback.append("Only selects one of name/category — need both.")
    else:
        feedback.append("Missing product name and category in SELECT.")

    # WHERE clause preserved
    if "quantity > 5" in s:
        score += 0.2
        feedback.append("Correct: quantity > 5 filter preserved.")
    else:
        feedback.append("Missing WHERE quantity > 5.")

    # No correlated subqueries remain
    correlated = bool(re.search(r"\(\s*select.*from products.*where.*oi\.", s))
    if not correlated:
        score += 0.2
        feedback.append("Correct: no correlated subqueries.")
    else:
        feedback.append("Correlated subqueries still present — use JOIN instead.")

    return round(score, 2), " | ".join(feedback)


# ─────────────────────────────────────────────────────────
# TASK 3 — HARD
# Bugs: (1) missing index hint via wrong column in WHERE,
#        (2) SELECT * fetches unneeded columns,
#        (3) implicit cartesian join between tables,
#        (4) wrong aggregation — COUNT(*) should be COUNT(DISTINCT customer_id)
# ─────────────────────────────────────────────────────────

TASK_HARD = {
    "task_id": "hard_multi_bug",
    "difficulty": "hard",
    "schema_context": """
Table: orders
  id          INTEGER PRIMARY KEY   -- indexed
  customer_id INTEGER               -- indexed
  status      TEXT                  -- values: 'pending','shipped','cancelled'
  total       DECIMAL(10,2)
  created_at  TIMESTAMP             -- indexed

Table: customers
  id          INTEGER PRIMARY KEY
  email       TEXT
  region      TEXT
  joined_at   TIMESTAMP
""".strip(),
    "broken_query": """
SELECT *, COUNT(*) as order_count
FROM orders, customers
WHERE orders.total > 100
GROUP BY orders.status;
""".strip(),
    "error_description": (
        "This query has four problems: "
        "(1) It uses old-style implicit JOIN (comma between tables) creating a "
        "cartesian product — every order is matched with every customer. "
        "(2) SELECT * fetches all columns including large unneeded ones. "
        "(3) COUNT(*) counts all rows including duplicates — should count distinct customers. "
        "(4) The GROUP BY is on status but the goal is per-region stats."
    ),
    "expected_behavior": (
        "For each customer region, return the region name, number of distinct customers, "
        "and total revenue from orders over 100, using an explicit JOIN between orders "
        "and customers on the correct key. Only select needed columns."
    ),
}


def grade_hard(fixed_query: str) -> tuple[float, str]:
    """
    Scoring:
      +0.25 if explicit JOIN used (no cartesian product)
      +0.25 if COUNT(DISTINCT ...) used
      +0.25 if GROUP BY region (not status)
      +0.15 if SELECT * removed (no "select *")
      +0.10 if joins on correct key (orders.customer_id = customers.id)
    """
    score = 0.0
    feedback = []

    s = normalize(fixed_query)

    # Explicit JOIN
    if re.search(r"join customers", s) or re.search(r"join orders", s):
        score += 0.25
        feedback.append("Correct: uses explicit JOIN.")
    else:
        feedback.append("Must use explicit JOIN — not comma-separated tables.")

    # COUNT(DISTINCT ...)
    if re.search(r"count\s*\(\s*distinct", s):
        score += 0.25
        feedback.append("Correct: uses COUNT(DISTINCT ...).")
    else:
        feedback.append("Should use COUNT(DISTINCT customer_id) to avoid duplicates.")

    # GROUP BY region
    if "group by" in s and "region" in s:
        score += 0.25
        feedback.append("Correct: groups by region.")
    else:
        feedback.append("Must GROUP BY region, not status.")

    # No SELECT *
    if "select *" not in s and "select oi.*" not in s:
        score += 0.15
        feedback.append("Correct: no SELECT *.")
    else:
        feedback.append("Remove SELECT * — only select needed columns.")

    # Joins on correct key
    if re.search(r"orders\.customer_id\s*=\s*customers\.id", s) or \
       re.search(r"customers\.id\s*=\s*orders\.customer_id", s):
        score += 0.10
        feedback.append("Correct: joins on orders.customer_id = customers.id.")
    else:
        feedback.append("Join condition should be orders.customer_id = customers.id.")

    return round(score, 2), " | ".join(feedback)


# ─────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────

TASKS = {
    "easy_null_filter": (TASK_EASY, grade_easy),
    "medium_n_plus_one": (TASK_MEDIUM, grade_medium),
    "hard_multi_bug": (TASK_HARD, grade_hard),
}

TASK_ORDER = ["easy_null_filter", "medium_n_plus_one", "hard_multi_bug"]