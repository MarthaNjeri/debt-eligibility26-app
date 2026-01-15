import io
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Debt Eligibility App", layout="wide")
st.title("Debt Eligibility Checker")

st.caption("Upload an Excel/CSV, select Member No, Route, and 3 month balance columns. Then run eligibility.")

def compute_debt_eligibility(df: pd.DataFrame, col_m1: str, col_m2: str, col_m3: str) -> pd.DataFrame:
    df = df.copy()

    # Coalesce nulls to 0 (like COALESCE), force numeric safely
    def to_num(s: pd.Series) -> pd.Series:
        return pd.to_numeric(s, errors="coerce").fillna(0)

    m1 = to_num(df[col_m1])
    m2 = to_num(df[col_m2])
    m3 = to_num(df[col_m3])

    # Match your SWITCH(TRUE()) order
    zero_all = (m1 == 0) & (m2 == 0) & (m3 == 0)
    strictly_increasing = (m1 < m2) & (m2 < m3)
    strictly_decreasing = (m1 > m2) & (m2 > m3)
    constant = (m1 == m2) & (m2 == m3)

    df["DebtEligibility"] = np.select(
        [zero_all, strictly_increasing, strictly_decreasing, constant],
        ["Eligible", "Ineligible", "Eligible", "Dormant"],
        default="Ineligible"
    )

    df["Reason"] = np.select(
        [zero_all, strictly_increasing, strictly_decreasing, constant],
        ["Zero balance across selected months",
         "Strictly increasing debt across selected months",
         "Strictly decreasing debt across selected months",
         "Constant balance across selected months (Dormant)"],
        default="Mixed behaviour"
    )

    return df

def guess_balance_columns(df: pd.DataFrame) -> list[str]:
    """
    Suggest likely balance columns: numeric-ish columns excluding common ID/text fields.
    """
    exclude_keywords = ["member", "route", "name", "date", "month", "year", "id", "clerk", "zone"]
    candidates = []
    for c in df.columns:
        c_low = str(c).lower()
        if any(k in c_low for k in exclude_keywords):
            continue
        # Keep columns that are numeric OR can be coerced into numeric reasonably
        series = pd.to_numeric(df[c], errors="coerce")
        non_null_ratio = series.notna().mean()
        if non_null_ratio > 0.3:  # heuristic
            candidates.append(c)
    # Fallback: if none found, just return all columns
    return candidates if candidates else list(df.columns)

uploaded = st.file_uploader("Upload file", type=["xlsx", "xls", "csv"])

if uploaded:
    try:
        if uploaded.name.lower().endswith(".csv"):
            df = pd.read_csv(uploaded)
        else:
            df = pd.read_excel(uploaded)

        st.subheader("Data Preview")
        st.dataframe(df.head(20), use_container_width=True)

        st.divider()
        st.subheader("Map your columns")

        all_cols = list(df.columns)

        # Member No + Route selectors
        # Try to auto-suggest
        member_guess = next((c for c in all_cols if str(c).lower().replace(" ", "") in ["memberno", "member_no", "membernumber"]), None)
        route_guess = next((c for c in all_cols if "route" in str(c).lower()), None)

        col_member = st.selectbox("Select Member No column", all_cols, index=all_cols.index(member_guess) if member_guess in all_cols else 0)
        col_route = st.selectbox("Select Route column", all_cols, index=all_cols.index(route_guess) if route_guess in all_cols else (1 if len(all_cols) > 1 else 0))

        # Month/balance columns selector (3 columns)
        balance_candidates = guess_balance_columns(df)
        st.caption("Select 3 balance columns in chronological order (e.g., Nov → Dec → Jan).")

        # Attempt to preselect first 3 candidates if available
        def idx_or_zero(cols, val):
            return cols.index(val) if val in cols else 0

        default_m1 = balance_candidates[0] if len(balance_candidates) > 0 else all_cols[0]
        default_m2 = balance_candidates[1] if len(balance_candidates) > 1 else all_cols[min(1, len(all_cols)-1)]
        default_m3 = balance_candidates[2] if len(balance_candidates) > 2 else all_cols[min(2, len(all_cols)-1)]

        col_m1 = st.selectbox("Month 1 balance column", balance_candidates, index=idx_or_zero(balance_candidates, default_m1))
        col_m2 = st.selectbox("Month 2 balance column", balance_candidates, index=idx_or_zero(balance_candidates, default_m2))
        col_m3 = st.selectbox("Month 3 balance column", balance_candidates, index=idx_or_zero(balance_candidates, default_m3))

        # Basic validation
        if len({col_m1, col_m2, col_m3}) < 3:
            st.warning("Please select 3 DIFFERENT balance columns.")
        else:
            if st.button("Run eligibility"):
                out = compute_debt_eligibility(df, col_m1, col_m2, col_m3)

                # Keep only what matters in the final output (plus any other columns you want later)
                result_cols = [col_member, col_route, col_m1, col_m2, col_m3, "DebtEligibility", "Reason"]
                # Only keep cols that exist (safe)
                result_cols = [c for c in result_cols if c in out.columns]

                results = out[result_cols].copy()

                st.subheader("Results")
                st.dataframe(results, use_container_width=True)

                st.subheader("Summary")
                summary = results["DebtEligibility"].value_counts(dropna=False).reset_index()
                summary.columns = ["DebtEligibility", "Count"]
                st.dataframe(summary, use_container_width=True)

                # Download Excel (2 sheets)
                towrite = io.BytesIO()
                with pd.ExcelWriter(towrite, engine="openpyxl") as writer:
                    results.to_excel(writer, index=False, sheet_name="Results")
                    summary.to_excel(writer, index=False, sheet_name="Summary")
                towrite.seek(0)

                st.download_button(
                    "Download results (Excel)",
                    data=towrite,
                    file_name="debt_eligibility_results.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

    except Exception as e:
        st.error(f"Error: {e}")
