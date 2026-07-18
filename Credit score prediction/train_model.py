"""
train_model.py  —  FinScore AI
Trained on: dataset.xlsx (4269 loan records with real CIBIL scores)
Columns used:
    income_annum, loan_amount, loan_term, cibil_score,
    no_of_dependents, self_employed, education,
    residential_assets_value, commercial_assets_value,
    luxury_assets_value, bank_asset_value
Target: loan_status (Approved=1 / Rejected=0)
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.preprocessing import LabelEncoder
import joblib
import warnings
warnings.filterwarnings("ignore")

DATASET_PATH = "dataset.xlsx"
MODEL_PATH   = "credit_score_model.pkl"

# ── Feature columns the model will use ───────────────────────────────────────
# cibil_score is included as a direct feature — it IS the real credit signal
# app.py will also need to pass it (derived from ML proba for uploaded statements)
FEATURE_COLS = [
    "monthly_income",
    "monthly_expense",
    "net_savings",
    "savings_rate",
    "avg_balance",
    "emi_count",
    "salary_frequency",
    "debit_credit_ratio",
    "cash_withdrawal_ratio",
    "loan_payment_history",
    "cibil_score",             # real CIBIL from dataset — key predictor
]
LABEL_COL = "creditworthy"

print("=" * 60)
print("  FinScore AI — Training Pipeline")
print("  Dataset: dataset.xlsx")
print("=" * 60)

# ══════════════════════════════════════════════════════════════
# STEP 1 — Load and clean dataset.xlsx
# ══════════════════════════════════════════════════════════════
print("\n[1/5] Loading dataset.xlsx ...")

df = pd.read_excel(DATASET_PATH)
df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

print(f"      Rows loaded  : {len(df):,}")
print(f"      Columns      : {list(df.columns)}")

# Drop rows with nulls in key columns
df = df.dropna(subset=["income_annum", "cibil_score", "loan_status"])

# Clean numeric columns
for col in ["income_annum","loan_amount","loan_term","cibil_score",
            "residential_assets_value","commercial_assets_value",
            "luxury_assets_value","bank_asset_value","no_of_dependents"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

print(f"      After clean  : {len(df):,}")
print(f"      Approved     : {(df['loan_status'].str.strip()=='Approved').sum():,}")
print(f"      Rejected     : {(df['loan_status'].str.strip()=='Rejected').sum():,}")
print(f"      CIBIL range  : {df['cibil_score'].min():.0f} – {df['cibil_score'].max():.0f}")
print(f"      Avg income   : Rs.{df['income_annum'].mean():,.0f} /year")


# ══════════════════════════════════════════════════════════════
# STEP 2 — Feature Engineering
# Map dataset.xlsx columns → 10 standard features used by app.py
# ══════════════════════════════════════════════════════════════
print("\n[2/5] Engineering features ...")

# Monthly income from annual
df["monthly_income"] = (df["income_annum"] / 12).astype(int)

# Estimated monthly expense based on:
#   - dependents (each adds ~Rs.5000/month)
#   - self_employed has higher expenses
#   - loan term length implies higher commitment
dep_cost   = df["no_of_dependents"].clip(0, 6) * 5000
self_empl  = (df["self_employed"].astype(str).str.strip().str.lower() == "yes").astype(int)
base_ratio = 0.45 + (self_empl * 0.10) + (df["no_of_dependents"].clip(0,5) * 0.02)
df["monthly_expense"] = ((df["monthly_income"] * base_ratio) + dep_cost).astype(int)
df["monthly_expense"] = df["monthly_expense"].clip(upper=df["monthly_income"] * 0.92)

# Net savings
df["net_savings"]  = (df["monthly_income"] - df["monthly_expense"]).clip(lower=0)

# Savings rate
df["savings_rate"] = (df["net_savings"] / df["monthly_income"].clip(lower=1)).clip(0, 1)

# Average bank balance — use bank_asset_value as proxy
df["avg_balance"]  = df["bank_asset_value"].clip(lower=0)

# EMI count — estimated from loan_term (longer term = more EMIs running)
df["emi_count"]    = (df["loan_term"] / 12).clip(0, 8).astype(int)

# Salary frequency (1 = monthly salaried; 0 = irregular/self-employed)
df["salary_frequency"] = (self_empl == 0).astype(int)

# Debit/credit ratio — expense vs income
df["debit_credit_ratio"] = (df["monthly_expense"] / df["monthly_income"].clip(lower=1)).clip(0.05, 1.5)

# Cash withdrawal ratio — luxury_assets as proxy for cash-heavy lifestyle
total_assets = (df["residential_assets_value"] +
                df["commercial_assets_value"]  +
                df["luxury_assets_value"]       +
                df["bank_asset_value"]).clip(lower=1)
df["cash_withdrawal_ratio"] = (df["luxury_assets_value"] / total_assets).clip(0, 1)

# Loan payment history — derived from assets & loan term (not from CIBIL, avoids circular logic)
# High assets + short loan term = good repayment history proxy
asset_ratio = (df["bank_asset_value"] / df["loan_amount"].clip(lower=1)).clip(0, 5)
df["loan_payment_history"] = (asset_ratio >= 0.3).astype(int)

# Target label — Approved=1, Rejected=0
df[LABEL_COL] = (df["loan_status"].astype(str).str.strip() == "Approved").astype(int)

# Final dataset
data = df[FEATURE_COLS + [LABEL_COL]].copy()
data["real_cibil"] = df["cibil_score"].values
data = data.dropna().reset_index(drop=True)
print(f"      Feature rows : {len(data):,}")
print(f"      Label split  — Creditworthy: {data[LABEL_COL].sum():,} | Not: {(data[LABEL_COL]==0).sum():,}")


# ══════════════════════════════════════════════════════════════
# STEP 3 — Train / Test Split
# ══════════════════════════════════════════════════════════════
print("\n[3/5] Splitting data ...")

X = data[FEATURE_COLS]
y = data[LABEL_COL]

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
print(f"      Train : {len(X_train):,}  |  Test : {len(X_test):,}")


# ══════════════════════════════════════════════════════════════
# STEP 4 — Train Model
# ══════════════════════════════════════════════════════════════
print("\n[4/5] Training RandomForest ...")

model = RandomForestClassifier(
    n_estimators=300,
    max_depth=12,
    min_samples_leaf=5,
    max_features="sqrt",
    class_weight="balanced",
    random_state=42,
    n_jobs=-1,
)
model.fit(X_train, y_train)

acc      = model.score(X_test, y_test)
cv       = cross_val_score(model, X, y, cv=5, scoring="accuracy", n_jobs=-1)

print(f"      Test Accuracy : {acc * 100:.2f}%")
print(f"      5-Fold CV     : {cv.mean()*100:.2f}% (+/- {cv.std()*100:.2f}%)")
print()
print("      Classification Report:")
report = classification_report(
    y_test, model.predict(X_test),
    target_names=["Not Creditworthy", "Creditworthy"]
)
for line in report.split("\n"):
    print(f"        {line}")

# Feature importances
print("      Top Feature Importances:")
importances = sorted(zip(FEATURE_COLS, model.feature_importances_),
                     key=lambda x: x[1], reverse=True)
for feat, imp in importances:
    bar = "#" * int(imp * 60)
    print(f"        {feat:<30} {imp:.4f}  {bar}")


# ══════════════════════════════════════════════════════════════
# STEP 5 — Sanity Check (same hybrid formula as app.py)
# ══════════════════════════════════════════════════════════════
print("\n[5/5] Sanity check against real CIBIL score profiles ...")

def estimate_final_score(feats_dict, proba):
    """Hybrid ML + rule-based score — identical to predict_credit() in app.py"""
    base = 300 + proba * 550
    sr = feats_dict["savings_rate"]
    ab = feats_dict["avg_balance"]
    ec = feats_dict["emi_count"]
    lh = feats_dict["loan_payment_history"]
    cw = feats_dict["cash_withdrawal_ratio"]
    mi = feats_dict["monthly_income"]

    if   sr >= 0.40: base += 40
    elif sr >= 0.25: base += 20
    elif sr >= 0.15: base += 10

    if   ab >= 80000:  base += 30
    elif ab >= 40000:  base += 20
    elif ab >= 20000:  base += 10

    if   ec == 0:  base += 20
    elif ec <= 2:  base += 10
    elif ec >= 5:  base -= 20

    if lh == 1:        base += 15
    if cw <= 0.05:     base += 10
    elif cw >= 0.35:   base -= 15

    if   mi >= 100000: base += 15
    elif mi >= 60000:  base += 8

    return int(np.clip(base, 300, 900))

# Sample a few real rows from dataset at various CIBIL ranges
sample_ranges = [
    ("CIBIL 750+ (Excellent)", data[data["cibil_score"] >= 750].copy().reset_index(drop=True).head(1)),
    ("CIBIL 700-749 (Good)",   data[(data["cibil_score"] >= 700) & (data["cibil_score"] < 750)].copy().reset_index(drop=True).head(1)),
    ("CIBIL 650-699 (Fair)",   data[(data["cibil_score"] >= 650) & (data["cibil_score"] < 700)].copy().reset_index(drop=True).head(1)),
    ("CIBIL 550-649 (Average)",data[(data["cibil_score"] >= 550) & (data["cibil_score"] < 650)].copy().reset_index(drop=True).head(1)),
    ("CIBIL <550   (Poor)",    data[data["cibil_score"] < 550].copy().reset_index(drop=True).head(1)),
]

print(f"\n  {'Profile':<28} {'Real CIBIL':>10}  {'ML Proba':>8}  {'Our Score':>9}  {'Loan':>22}")
print("  " + "-" * 82)

for label, subset in sample_ranges:
    if subset.empty:
        continue
    row       = subset[FEATURE_COLS].iloc[0]
    real_cibil= int(subset["cibil_score"].iloc[0])
    proba     = model.predict_proba(subset[FEATURE_COLS])[0][1]
    score     = estimate_final_score(row.to_dict(), proba)

    if score >= 750:   loan = "Approved"
    elif score >= 700: loan = "Approved"
    elif score >= 650: loan = "Conditionally Approved"
    elif score >= 600: loan = "Conditionally Approved"
    else:              loan = "Not Approved"

    print(f"  {label:<28} {real_cibil:>10}  {proba:>8.2f}  {score:>9}  {loan:>22}")

# ── Save model ────────────────────────────────────────────────
joblib.dump(model, MODEL_PATH)

print()
print("=" * 60)
print(f"  Model saved -> {MODEL_PATH}")
print(f"  Trained on {len(data):,} real loan records")
print(f"  Accuracy   {acc*100:.2f}%  |  CV {cv.mean()*100:.2f}%")
print("  Restart app.py to use the new model.")
print("=" * 60)
