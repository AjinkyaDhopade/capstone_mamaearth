
-- Mamaearth capstone seed-data stage.
-- Run from the repository root:
--   python sql/load_data.py
--
-- The Python loader imports the original CSV files, converts blank
-- discount_pct and rating cells to SQL NULL, and checks row counts.
-- It is safe to rerun because the loader clears the existing tables
-- before inserting the source data again.
--
-- After loading, run these validation queries:

SELECT COUNT(*) AS total_customers FROM customers;
SELECT COUNT(*) AS total_products FROM products;
SELECT COUNT(*) AS total_orders FROM orders;

SELECT
    SUM(CASE WHEN discount_pct IS NULL THEN 1 ELSE 0 END)
        AS missing_discounts,
    SUM(CASE WHEN rating IS NULL THEN 1 ELSE 0 END)
        AS missing_ratings
FROM orders;
