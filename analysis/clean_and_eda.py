
from pathlib import Path
import json
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ANALYSIS = ROOT / "analysis"
NARRATOR = ROOT / "narrator"

ANALYSIS.mkdir(exist_ok=True)
NARRATOR.mkdir(exist_ok=True)

orders = pd.read_csv(DATA / "orders.csv")
customers = pd.read_csv(DATA / "customers.csv")
products = pd.read_csv(DATA / "products.csv")

print("\n=== 1. LOAD AND INSPECT ===")
print("Original orders shape:", orders.shape)
assert orders.shape == (180, 9)

print("\n=== 2. STANDARDIZE PAYMENT METHODS ===")
print("Raw payment values:", sorted(orders["payment_method"].unique()))
assert orders["payment_method"].nunique() == 7

orders["payment_method"] = (
    orders["payment_method"].astype("string").str.strip().str.upper()
)
print("Standardized payment counts:")
print(orders["payment_method"].value_counts().sort_index())

print("\n=== 3. DETECT AND REMOVE DUPLICATES ===")
natural_key = [
    "customer_id", "product_id", "order_date", "quantity",
    "discount_pct", "payment_method", "rating", "returned"
]

duplicate_mask = orders.duplicated(subset=natural_key, keep="first")
dropped = orders.loc[duplicate_mask].copy()
orders_clean = orders.loc[~duplicate_mask].copy()

print("Duplicate count:", int(duplicate_mask.sum()))
print("Dropped order IDs:", dropped["order_id"].tolist())
print("Clean shape:", orders_clean.shape)

assert dropped["order_id"].tolist() == [
    "O0176", "O0177", "O0178", "O0179", "O0180"
]
assert orders_clean.shape == (175, 9)

print("\n=== 4. IMPUTE MISSING VALUES ===")
discount_missing = int(orders_clean["discount_pct"].isna().sum())
rating_missing = int(orders_clean["rating"].isna().sum())
rating_median = float(orders_clean["rating"].median())

print("Missing discounts:", discount_missing)
print("Missing ratings:", rating_missing)
print("Rating median before imputation:", rating_median)

orders_clean["discount_pct"] = orders_clean["discount_pct"].fillna(0)
orders_clean["rating"] = orders_clean["rating"].fillna(rating_median)

print("Missing values after imputation:")
print(orders_clean[["discount_pct", "rating"]].isnull().sum().to_dict())

assert discount_missing == 12
assert rating_missing == 15
assert rating_median == 3.0
assert not orders_clean[["discount_pct", "rating"]].isnull().any().any()

print("\n=== 5. MERGE AND RECONCILE REVENUE ===")
def enrich(frame):
    result = frame.merge(products, on="product_id", how="left",
                         validate="many_to_one")
    result = result.merge(customers, on="customer_id", how="left",
                          validate="many_to_one")
    result["order_date"] = pd.to_datetime(result["order_date"])
    result["order_value"] = (
        result["quantity"] * result["price"]
        * (1 - result["discount_pct"].fillna(0) / 100)
    )
    return result

# Independently value the original five duplicate rows.
dropped_valued = enrich(dropped)
duplicate_delta = round(float(dropped_valued["order_value"].sum()), 2)

merged = enrich(orders_clean)
cleaned_revenue = round(float(merged["order_value"].sum()), 2)

raw_valued = enrich(orders)
raw_revenue = round(float(raw_valued["order_value"].sum()), 2)

print(f"Raw revenue: INR {raw_revenue:,.2f}")
print(f"Cleaned revenue: INR {cleaned_revenue:,.2f}")
print(f"Duplicate-row revenue: INR {duplicate_delta:,.2f}")
print(
    f"Reconciliation: raw revenue of INR {raw_revenue:,.2f} less "
    f"the five duplicate rows worth INR {duplicate_delta:,.2f} "
    f"equals cleaned revenue of INR {cleaned_revenue:,.2f}. "
    "Discount and rating imputation does not change revenue because "
    "missing discounts are treated as 0% in both calculations and "
    "rating does not enter the revenue formula."
)

assert round(raw_revenue - cleaned_revenue, 2) == duplicate_delta

print("\n=== 6. IQR OUTLIER DETECTION ===")
q1 = float(merged["quantity"].quantile(0.25))
q3 = float(merged["quantity"].quantile(0.75))
iqr = q3 - q1
lower = q1 - 1.5 * iqr
upper = q3 + 1.5 * iqr

merged["is_outlier"] = (
    (merged["quantity"] < lower) | (merged["quantity"] > upper)
)

print(f"Q1={q1}, Q3={q3}, IQR={iqr}, lower={lower}, upper={upper}")
print("Outlier orders:")
print(merged.loc[merged["is_outlier"], ["order_id", "quantity"]])

assert (q1, q3, iqr, lower, upper) == (1.0, 2.0, 1.0, -0.5, 3.5)
assert set(merged.loc[merged["is_outlier"], "order_id"]) == {
    "O0011", "O0098"
}

print("\n=== 7. PAYMENT RETURN-RATE HYPOTHESIS ===")
print("Hypothesis: COD has a higher return rate than CARD and UPI.")
payment_stats = (
    merged.groupby("payment_method")["returned"]
    .agg(["count", "mean"])
)
payment_stats["return_rate_pct"] = payment_stats["mean"] * 100
print(payment_stats.round(3))

rates = payment_stats["return_rate_pct"].round(1).to_dict()
print("Return rates (%):", rates)

if rates["COD"] > rates["CARD"] and rates["COD"] > rates["UPI"]:
    print("Hypothesis: Confirmed")
else:
    print("Hypothesis: Not confirmed")

# Export for visualization.
payment_stats.reset_index().to_csv(
    ANALYSIS / "payment_return_rates.csv", index=False
)

print("\n=== 8. PAYMENT METHOD AND CITY TIER ===")
segment_stats = (
    merged.groupby(["payment_method", "city_tier"])["returned"]
    .agg(["count", "mean"])
    .reset_index()
)
segment_stats["return_rate_pct"] = segment_stats["mean"] * 100
print(segment_stats.round(2).to_string(index=False))

highest = segment_stats.loc[segment_stats["return_rate_pct"].idxmax()]
print(
    "Highest-risk segment:",
    f'{highest["payment_method"]} + Tier-{int(highest["city_tier"])}',
    f'({highest["return_rate_pct"]:.1f}%, n={int(highest["count"])})'
)

assert highest["payment_method"] == "COD"
assert int(highest["city_tier"]) == 2
assert round(float(highest["return_rate_pct"]), 1) == 54.5

print("\n=== 9. CORRELATION ANALYSIS ===")
correlation_columns = [
    "rating", "returned", "discount_pct", "quantity"
]
corr = merged[correlation_columns].corr()
print(corr.round(4))

def strength(value):
    magnitude = abs(value)
    if magnitude < 0.2:
        return "negligible"
    if magnitude < 0.4:
        return "weak"
    if magnitude < 0.7:
        return "moderate"
    return "strong"

for i, col_a in enumerate(correlation_columns):
    for col_b in correlation_columns[i + 1:]:
        value = float(corr.loc[col_a, col_b])
        print(f"{col_a} vs {col_b}: r={value:.4f}, {strength(value)}")

discount_corr = float(corr.loc["discount_pct", "returned"])
print(
    "Hypothesis 'higher discounts reduce returns':",
    "Busted" if discount_corr > -0.2 else "Requires further investigation",
)

print("\n=== 10. MONTHLY REVENUE AND OUTLIER CORRECTION ===")
merged["year_month"] = merged["order_date"].dt.to_period("M").astype(str)

monthly_all = (
    merged.groupby("year_month")["order_value"].sum().round(2)
)
monthly_corrected = (
    merged.loc[~merged["is_outlier"]]
    .groupby("year_month")["order_value"].sum().round(2)
)

all_months = pd.period_range("2026-01", "2026-06", freq="M").astype(str)
monthly_all = monthly_all.reindex(all_months, fill_value=0).round(2)
monthly_corrected = monthly_corrected.reindex(
    all_months, fill_value=0
).round(2)

print("Monthly revenue including outliers:")
print(monthly_all.to_string())

print("\nMonthly revenue excluding outliers:")
print(monthly_corrected.to_string())

peak_month = str(monthly_corrected.idxmax())
peak_revenue = round(float(monthly_corrected.max()), 2)

print(
    "January's apparent revenue lead is inflated by bulk orders "
    "O0011 (2026-01-28, quantity 25) and O0098 "
    "(2026-01-10, quantity 30). After excluding these outliers, "
    f"{peak_month} is the genuine peak month."
)

monthly_frame = pd.DataFrame({
    "month": all_months,
    "revenue_including_outliers": monthly_all.values,
    "revenue_corrected": monthly_corrected.values,
})
monthly_frame.to_csv(ANALYSIS / "monthly_revenue.csv", index=False)

print("\n=== EXPORT VERIFIED FINDINGS ===")
findings = {
    "cleaned_total_revenue_inr": cleaned_revenue,
    "raw_total_revenue_inr": raw_revenue,
    "duplicate_reconciliation_delta_inr": duplicate_delta,
    "return_rate_by_payment": {
        key: float(value) for key, value in rates.items()
    },
    "highest_risk_segment": {
        "payment_method": str(highest["payment_method"]),
        "city_tier": int(highest["city_tier"]),
        "return_rate_pct": round(float(highest["return_rate_pct"]), 1),
    },
    "true_peak_month": {
        "month": peak_month,
        "revenue_inr": peak_revenue,
    },
    "outlier_inflated_month": {
        "month": str(monthly_all.idxmax()),
        "apparent_revenue_inr": round(float(monthly_all.max()), 2),
        "corrected_revenue_inr": round(
            float(monthly_corrected.loc[monthly_all.idxmax()]), 2
        ),
    },
}

findings_path = NARRATOR / "findings.json"
findings_path.write_text(
    json.dumps(findings, indent=2), encoding="utf-8"
)
print(f"Generated {findings_path}")
print(json.dumps(findings, indent=2))
