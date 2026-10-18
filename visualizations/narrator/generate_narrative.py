
from pathlib import Path
import json
import os
import re

ROOT = Path(__file__).resolve().parents[1]
NARRATOR = ROOT / "narrator"
FINDINGS_PATH = NARRATOR / "findings.json"
SAMPLE_PATH = NARRATOR / "sample_output.txt"

SYSTEM_INSTRUCTION = """
You are a senior data analyst writing for Mamaearth's regional ops
and finance heads.

Write exactly three labeled sections:
Situation, Complication, and Resolution.

Every number in the narrative must come from the supplied findings
and must appear with the same value. Do not invent statistics,
causal claims, or unsupported numerical estimates. Explain findings
clearly for business decision-makers and make practical recommendations.
"""


def money(value):
    return f"{float(value):,.2f}"


def generate_scr_narrative_offline(findings: dict) -> dict:
    """Deterministic SCR narrative; requires no API or network."""
    try:
        cleaned = money(findings["cleaned_total_revenue_inr"])
        raw = money(findings["raw_total_revenue_inr"])
        delta = money(findings["duplicate_reconciliation_delta_inr"])

        rates = findings["return_rate_by_payment"]
        cod = rates["COD"]
        card = rates["CARD"]
        upi = rates["UPI"]

        segment = findings["highest_risk_segment"]
        segment_rate = segment["return_rate_pct"]
        tier = segment["city_tier"]

        peak = findings["true_peak_month"]
        peak_month = peak["month"]
        peak_revenue = money(peak["revenue_inr"])
        
    month_names = {
    "01": "January", "02": "February", "03": "March",
    "04": "April", "05": "May", "06": "June",
    "07": "July", "08": "August", "09": "September",
    "10": "October", "11": "November", "12": "December",
}
    
month_name = month_names[peak_month.split("-")[1]]

        inflated = findings["outlier_inflated_month"]
        inflated_month = inflated["month"]
        inflated_revenue = money(inflated["apparent_revenue_inr"])
        corrected_revenue = money(inflated["corrected_revenue_inr"])

        narrative = f"""
Situation

The cleaned order analysis reports total revenue of INR {cleaned}.
The raw source reports INR {raw}. The analysis covers payment methods,
city tiers, product categories, and monthly revenue.

Complication

COD has a return rate of {cod:.1f}%, compared with {card:.1f}% for CARD
and {upi:.1f}% for UPI. The highest-risk segment is COD in Tier-{tier}
cities, where the return rate is {segment_rate:.1f}%. This concentration
deserves investigation by regional operations. The difference between
raw and cleaned revenue is INR {delta}; the reconciliation attributes
this difference to duplicate orders, not rating imputation.

The apparent revenue for {inflated_month} is INR {inflated_revenue},
while the outlier-corrected value is INR {corrected_revenue}. Bulk
orders can distort monthly comparisons and should be reviewed separately.

Resolution

Prioritize a review of COD returns in Tier-{tier} cities. Examine return
reasons, delivery outcomes, and product-level patterns before changing
payment or marketing policies. Add duplicate-order controls to ingestion
and monitor return rates by payment method and city tier.

The verified outlier-corrected peak is {month_name}, with revenue of
INR {peak_revenue}. Use the corrected trend for monthly comparisons.
Treat the observed associations as diagnostic signals, not proof of
causation, and revalidate them as new orders arrive.
""".strip()

        return {"status": "success", "narrative": narrative, "tokens": 0}
    except Exception as err:
        return {
            "status": "error",
            "narrative": None,
            "message": str(err),
        }


def generate_scr_narrative(findings: dict) -> dict:
    """Use Gemini when configured; otherwise use offline fallback."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return generate_scr_narrative_offline(findings)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=30000),
        )

        # Build the prompt from the input findings; do not hardcode metrics.
        contents = (
            "Create the required SCR business narrative using only these "
            "verified findings. Preserve every numeric value exactly:\n"
            + json.dumps(findings, indent=2)
        )

        # Temperature 0.0 is used for factual, reproducible business reporting.
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.0,
                max_output_tokens=600,
            ),
        )

        text = response.text or ""
        usage = getattr(response, "usage_metadata", None)
        tokens = getattr(usage, "total_token_count", 0) if usage else 0

        if not text.strip():
            raise ValueError("Gemini returned an empty narrative.")

        return {
            "status": "success",
            "narrative": text,
            "tokens": tokens,
        }
    except Exception as err:
        print(f"Gemini unavailable; using offline fallback: {err}")
        return generate_scr_narrative_offline(findings)


def check_numeric_accuracy(narrative: str, findings: dict) -> bool:
    """Check the five mandatory figures and print each result."""
    normalized = narrative.replace(",", "")
    peak = findings["true_peak_month"]
    month_name = peak["month"].split("-")[1]

    # Include the written month name as well as its verified month label.
    month_names = {
        "01": "January", "02": "February", "03": "March",
        "04": "April", "05": "May", "06": "June",
        "07": "July", "08": "August", "09": "September",
        "10": "October", "11": "November", "12": "December",
    }
    required = [
        ("Cleaned revenue", money(findings["cleaned_total_revenue_inr"])),
        ("COD return rate", f'{findings["return_rate_by_payment"]["COD"]:.1f}'),
        ("Highest-risk segment",
         f'{findings["highest_risk_segment"]["return_rate_pct"]:.1f}'),
        ("Duplicate reconciliation delta",
         money(findings["duplicate_reconciliation_delta_inr"])),
        ("March peak revenue", money(peak["revenue_inr"])),
    ]

    passed = True
    for label, value in required:
        ok = value.replace(",", "") in normalized
        if label == "March peak revenue":
            ok = ok and month_names[month_name] in narrative
        print(f"{'PASS' if ok else 'FAIL'}: {label} ({value})")
        passed = passed and ok

    return passed


def main():
    if not FINDINGS_PATH.exists():
        raise FileNotFoundError(
            "Run python analysis/clean_and_eda.py first."
        )

    findings = json.loads(FINDINGS_PATH.read_text(encoding="utf-8"))
    result = generate_scr_narrative(findings)

    if result["status"] != "success":
        raise RuntimeError(result.get("message", "Narrative generation failed"))

    narrative = result["narrative"]
    print("\n=== SCR NARRATIVE ===\n")
    print(narrative)

    if not check_numeric_accuracy(narrative, findings):
        print("Numeric checker failed; replacing output with offline version.")
        result = generate_scr_narrative_offline(findings)
        narrative = result["narrative"]
        if not check_numeric_accuracy(narrative, findings):
            raise AssertionError("Offline narrative failed numeric validation.")

    SAMPLE_PATH.write_text(narrative + "\n", encoding="utf-8")
    print(f"\nSaved verified narrative to {SAMPLE_PATH}")


if __name__ == "__main__":
    main()
