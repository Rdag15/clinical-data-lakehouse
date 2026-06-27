#!/usr/bin/env python3
"""Train and evaluate diabetes-phenotype classifiers on the patient feature table.

Predicts type-2 diabetes from demographics + general healthcare utilization (see
build_features.py for the leakage-aware feature/target design). Trains an interpretable
logistic-regression baseline and a gradient-boosting model, evaluates on a held-out test
set, and writes metrics + figures to ml/ and ml/figures/.

Usage:
    python ml/build_features.py        # produces patient_features.csv
    python ml/train_diabetes_model.py
"""
import os
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import (roc_curve, auc, average_precision_score, confusion_matrix,
                             precision_score, recall_score, f1_score, accuracy_score)

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
os.makedirs(FIG, exist_ok=True)
RANDOM_STATE = 42

FEATURES = ["age", "is_male", "income", "healthcare_expenses", "healthcare_coverage",
            "encounter_count", "procedure_count", "observation_count"]
TARGET = "has_diabetes"


def main():
    df = pd.read_csv(os.path.join(HERE, "patient_features.csv"))
    X, y = df[FEATURES], df[TARGET]
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.25, stratify=y, random_state=RANDOM_STATE)

    models = {
        "Logistic Regression": Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(class_weight="balanced", max_iter=1000,
                                       random_state=RANDOM_STATE)),
        ]),
        "Gradient Boosting": Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("clf", GradientBoostingClassifier(random_state=RANDOM_STATE)),
        ]),
    }

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    results, roc_data = {}, {}

    for name, model in models.items():
        cv_auc = cross_val_score(model, X_tr, y_tr, cv=cv, scoring="roc_auc")
        model.fit(X_tr, y_tr)
        proba = model.predict_proba(X_te)[:, 1]
        pred = model.predict(X_te)
        fpr, tpr, _ = roc_curve(y_te, proba)
        test_auc = auc(fpr, tpr)
        roc_data[name] = (fpr, tpr, test_auc)
        results[name] = {
            "cv_auc_mean": round(float(cv_auc.mean()), 3),
            "cv_auc_std": round(float(cv_auc.std()), 3),
            "test_auc": round(float(test_auc), 3),
            "test_avg_precision": round(float(average_precision_score(y_te, proba)), 3),
            "test_accuracy": round(float(accuracy_score(y_te, pred)), 3),
            "test_precision": round(float(precision_score(y_te, pred, zero_division=0)), 3),
            "test_recall": round(float(recall_score(y_te, pred, zero_division=0)), 3),
            "test_f1": round(float(f1_score(y_te, pred, zero_division=0)), 3),
        }
        print(f"{name:22s} CV-AUC={results[name]['cv_auc_mean']:.3f}"
              f"±{results[name]['cv_auc_std']:.3f}  test-AUC={test_auc:.3f}"
              f"  recall={results[name]['test_recall']:.3f}")

    # ---- ROC curves ----
    plt.figure(figsize=(6, 6))
    for name, (fpr, tpr, a) in roc_data.items():
        plt.plot(fpr, tpr, lw=2, label=f"{name} (AUC = {a:.3f})")
    plt.plot([0, 1], [0, 1], "k--", lw=1, alpha=0.5)
    plt.xlabel("False positive rate"); plt.ylabel("True positive rate")
    plt.title("Diabetes phenotype classifier — ROC")
    plt.legend(loc="lower right"); plt.tight_layout()
    plt.savefig(os.path.join(FIG, "roc_curves.png"), dpi=130); plt.close()

    # ---- Feature importance (gradient boosting) + LR coefficients ----
    gb = models["Gradient Boosting"].named_steps["clf"]
    lr = models["Logistic Regression"].named_steps["clf"]
    order = np.argsort(gb.feature_importances_)
    fig, ax = plt.subplots(1, 2, figsize=(12, 5))
    ax[0].barh(np.array(FEATURES)[order], gb.feature_importances_[order], color="#2a6f97")
    ax[0].set_title("Gradient Boosting — feature importance")
    coef = lr.coef_[0]
    co = np.argsort(coef)
    colors = ["#c1121f" if c < 0 else "#2a9d8f" for c in coef[co]]
    ax[1].barh(np.array(FEATURES)[co], coef[co], color=colors)
    ax[1].set_title("Logistic Regression — standardized coefficients")
    ax[1].axvline(0, color="k", lw=0.8)
    plt.tight_layout(); plt.savefig(os.path.join(FIG, "feature_importance.png"), dpi=130); plt.close()

    # ---- Confusion matrix (best model by test AUC) ----
    best = max(results, key=lambda k: results[k]["test_auc"])
    pred = models[best].predict(X_te)
    cm = confusion_matrix(y_te, pred)
    plt.figure(figsize=(4.6, 4.2))
    plt.imshow(cm, cmap="Blues")
    for (i, j), v in np.ndenumerate(cm):
        plt.text(j, i, str(v), ha="center", va="center",
                 color="white" if v > cm.max() / 2 else "black", fontsize=13)
    plt.xticks([0, 1], ["No diabetes", "Diabetes"]); plt.yticks([0, 1], ["No diabetes", "Diabetes"])
    plt.xlabel("Predicted"); plt.ylabel("Actual"); plt.title(f"Confusion matrix — {best}")
    plt.tight_layout(); plt.savefig(os.path.join(FIG, "confusion_matrix.png"), dpi=130); plt.close()

    # ---- EDA: prevalence by age band, expenses by status ----
    df["age_band"] = pd.cut(df["age"], [0, 30, 45, 65, 80, 200],
                            labels=["<30", "30-44", "45-64", "65-79", "80+"])
    prev = df.groupby("age_band", observed=True)[TARGET].mean()
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
    ax[0].bar(prev.index.astype(str), prev.values * 100, color="#2a6f97")
    ax[0].set_ylabel("Diabetes prevalence (%)"); ax[0].set_xlabel("Age band")
    ax[0].set_title("Diabetes prevalence by age band")
    grp = [df.loc[df[TARGET] == k, "healthcare_expenses"].dropna() for k in (0, 1)]
    ax[1].boxplot(grp, tick_labels=["No diabetes", "Diabetes"], showfliers=False)
    ax[1].set_ylabel("Lifetime healthcare expenses ($)")
    ax[1].set_title("Healthcare expenses by diabetes status")
    plt.tight_layout(); plt.savefig(os.path.join(FIG, "eda_cohort.png"), dpi=130); plt.close()

    summary = {
        "n_patients": int(len(df)),
        "n_features": len(FEATURES),
        "features": FEATURES,
        "target": TARGET,
        "diabetes_prevalence": round(float(y.mean()), 3),
        "n_train": int(len(X_tr)), "n_test": int(len(X_te)),
        "best_model": best,
        "models": results,
    }
    with open(os.path.join(HERE, "metrics.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nbest model: {best} (test AUC {results[best]['test_auc']})")
    print(f"wrote metrics.json and {len(os.listdir(FIG))} figures to ml/figures/")


if __name__ == "__main__":
    main()
