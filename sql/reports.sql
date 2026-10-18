
-- Mamaearth Returns & Growth Intelligence Pipeline
-- Run after: python sql/load_data.py

-- (a) Order totals
-- Expected: 180 | 99860.20 | 554.78
SELECT
    COUNT(*) AS total_orders,
    ROUND(SUM(o.quantity * p.price *
        (1 - COALESCE(o.discount_pct, 0) / 100.0)), 2)
        AS total_revenue,
    ROUND(AVG(o.quantity * p.price *
        (1 - COALESCE(o.discount_pct, 0) / 100.0)), 2)
        AS avg_order_value
FROM orders o
JOIN products p ON p.product_id = o.product_id;

-- (b) COUNT(*) versus COUNT(rating)
-- Expected: 180 | 165 | 15
SELECT
    COUNT(*) AS all_orders,
    COUNT(rating) AS rated_orders,
    COUNT(*) - COUNT(rating) AS unrated_orders
FROM orders;

-- (c1) Customers with zero orders using LEFT JOIN
-- Expected: C045 | Vihaan
SELECT c.customer_id, c.name
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.name
HAVING COUNT(o.order_id) = 0;

-- (c2) Independent NOT IN confirmation
-- Expected: C045 | Vihaan
SELECT customer_id, name
FROM customers
WHERE customer_id NOT IN (
    SELECT DISTINCT customer_id FROM orders
);

-- (d) City return rates
-- Expected: Jaipur 19 8 42.1; Lucknow 49 15 30.6;
-- Bangalore 33 8 24.2
WITH city_stats AS (
    SELECT
        c.city,
        COUNT(*) AS total_orders,
        SUM(o.returned) AS returned_orders,
        ROUND(100.0 * SUM(o.returned) / COUNT(*), 1)
            AS return_rate_pct
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
    GROUP BY c.city
)
SELECT *
FROM city_stats
WHERE return_rate_pct > 20
ORDER BY return_rate_pct DESC;

-- (e1) Top five customers by spend
-- Tie-break: customer_id ASC makes equal-spend rankings deterministic.
SELECT
    c.customer_id,
    c.name,
    ROUND(SUM(o.quantity * p.price *
        (1 - COALESCE(o.discount_pct, 0) / 100.0)), 2)
        AS total_spend
FROM orders o
JOIN products p ON p.product_id = o.product_id
JOIN customers c ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.name
ORDER BY total_spend DESC, c.customer_id ASC
LIMIT 5;

-- (e2) Ranks 3–5, using the same ranking order
SELECT
    c.customer_id,
    c.name,
    ROUND(SUM(o.quantity * p.price *
        (1 - COALESCE(o.discount_pct, 0) / 100.0)), 2)
        AS total_spend
FROM orders o
JOIN products p ON p.product_id = o.product_id
JOIN customers c ON c.customer_id = o.customer_id
GROUP BY c.customer_id, c.name
ORDER BY total_spend DESC, c.customer_id ASC
LIMIT 3 OFFSET 2;

-- (f) Three-table join and category revenue
-- Expected: Haircare 54 44956.10; Skincare 60 27346.00;
-- Babycare 30 16805.00; PersonalCare 36 10753.10
SELECT
    p.category,
    COUNT(*) AS order_count,
    ROUND(SUM(o.quantity * p.price *
        (1 - COALESCE(o.discount_pct, 0) / 100.0)), 2)
        AS category_revenue
FROM orders o
JOIN products p ON p.product_id = o.product_id
JOIN customers c ON c.customer_id = o.customer_id
GROUP BY p.category
ORDER BY category_revenue DESC;

-- (g) Names beginning with A
-- Expected: 10 rows
SELECT customer_id, name
FROM customers
WHERE name LIKE 'A%'
ORDER BY customer_id;

-- (h) Distinct acquisition sources
-- Expected: Ad, Organic, Referral, Social
SELECT DISTINCT acquisition_source
FROM customers
ORDER BY acquisition_source;

-- (i) Loyalty tier
-- Run this section once on a fresh database.
ALTER TABLE customers ADD COLUMN loyalty_tier VARCHAR(10);

UPDATE customers
SET loyalty_tier = CASE
    WHEN city_tier = 1 THEN 'Gold'
    ELSE 'Silver'
END;

-- Expected: Gold 28; Silver 17
SELECT loyalty_tier, COUNT(*) AS customer_count
FROM customers
GROUP BY loyalty_tier
ORDER BY loyalty_tier;
