# streamlit prototype: Items Budgeting App
# Save as proto_streamlit_items_app.py and run with:
# streamlit run proto_streamlit_items_app.py

import streamlit as st
import sqlite3
from datetime import datetime, date
import pandas as pd
import json
import os

DB_PATH = "items_proto.db"

# --- Database helpers -------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE,
            items_per_period INTEGER,
            unit_value REAL,
            unit_label TEXT DEFAULT 'item'
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clicks (
            id INTEGER PRIMARY KEY,
            category_id INTEGER,
            ts TEXT,
            reason TEXT,
            amount REAL,
            FOREIGN KEY(category_id) REFERENCES categories(id)
        )
    """)
    conn.commit()
    conn.close()


def get_conn():
    return sqlite3.connect(DB_PATH)


def add_default_categories():
    conn = get_conn()
    cur = conn.cursor()
    defaults = [
        ("Burgers", 3, 16.0, 'burger'),
        ("Equipement", 3, 60.0, 'equip'),
        ("Bonbons", 20, 0.7, 'bonbon')
    ]
    for name, ip, uv, ul in defaults:
        try:
            cur.execute("INSERT INTO categories (name, items_per_period, unit_value, unit_label) VALUES (?, ?, ?, ?)", (name, ip, uv, ul))
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()


def list_categories():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, items_per_period, unit_value, unit_label FROM categories ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return rows


def create_category(name, items_per_period, unit_value, unit_label):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO categories (name, items_per_period, unit_value, unit_label) VALUES (?, ?, ?, ?)",
                (name, int(items_per_period), float(unit_value), unit_label))
    conn.commit()
    conn.close()


def record_click(category_id, reason, amount):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO clicks (category_id, ts, reason, amount) VALUES (?, ?, ?, ?)",
                (category_id, datetime.utcnow().isoformat(), reason, amount))
    conn.commit()
    conn.close()


def undo_last_click():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM clicks ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    if row:
        cur.execute("DELETE FROM clicks WHERE id = ?", (row[0],))
    conn.commit()
    conn.close()


def get_clicks_dataframe():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT c.id, cat.name, c.ts, c.reason, c.amount FROM clicks c JOIN categories cat ON c.category_id = cat.id ORDER BY c.id DESC")
    rows = cur.fetchall()
    conn.close()
    df = pd.DataFrame(rows, columns=["id", "category", "ts", "reason", "amount"]) if rows else pd.DataFrame(columns=["id", "category", "ts", "reason", "amount"])
    return df


def clicks_this_period(category_id, year=None, month=None):
    # month granularity
    if year is None or month is None:
        today = date.today()
        year, month = today.year, today.month
    conn = get_conn()
    cur = conn.cursor()
    start = date(year, month, 1).isoformat()
    # compute first day of next month
    if month == 12:
        next_month = date(year + 1, 1, 1).isoformat()
    else:
        next_month = date(year, month + 1, 1).isoformat()
    cur.execute("SELECT COUNT(*) FROM clicks WHERE category_id = ? AND ts >= ? AND ts < ?", (category_id, start, next_month))
    n = cur.fetchone()[0]
    conn.close()
    return n

# --- App UI ------------------------------------------------------------

st.set_page_config(page_title="Items Budget - Prototype", layout="wide")
init_db()
add_default_categories()

st.title("Prototype — Items budgeting (compte par items)")

# sidebar: settings + create category
with st.sidebar:
    st.header("Paramètres")
    period = st.selectbox("Période de reset", ["Mois", "Semaine"], index=0)
    st.markdown("---")
    st.subheader("Créer une catégorie")
    with st.form("new_cat", clear_on_submit=True):
        name = st.text_input("Nom (ex: Burgers)")
        items_per_period = st.number_input("Items / période", min_value=1, value=3)
        unit_value = st.number_input("Valeur unitaire (€)", min_value=0.0, value=10.0, format="%.2f")
        unit_label = st.text_input("Libellé unité (ex: burger)", value="item")
        if st.form_submit_button("Créer") and name.strip():
            create_category(name.strip(), items_per_period, unit_value, unit_label.strip() or "item")
            st.success(f"Catégorie '{name}' créée")

    st.markdown("---")
    st.subheader("Actions rapides")
    if st.button("Annuler dernier clic"):
        undo_last_click()
        st.success("Dernier clic annulé")

    if st.button("Réinitialiser la DB (supprime tout)"):
        if st.confirm := st.checkbox("Je confirme la suppression totale (cocher pour activer)"):
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)
            init_db()
            add_default_categories()
            st.experimental_rerun()

# main layout
cats = list_categories()
col1, col2 = st.columns([2, 3])

with col1:
    st.subheader("Catégories")
    reasons = ["envie", "faim", "stress", "social", "plaisir", "autre"]

    for cid, name, items_per_period, unit_value, unit_label in cats:
        # compute remaining for this month
        n_used = clicks_this_period(cid)
        remaining = max(0, items_per_period - n_used)

        with st.expander(f"{name} — {remaining}/{items_per_period} {unit_label}"):
            st.write(f"Valeur unitaire: {unit_value} €")
            st.write(f"Utilisés ce mois: {n_used}")
            cols = st.columns([2, 1, 1])
            with cols[0]:
                if st.button(f"+1 {unit_label} — {name}", key=f"btn_{cid}"):
                    # default amount = 1 item
                    record_click(cid, "—", 1.0)
                    st.success(f"{unit_label} consommé")
                    st.experimental_rerun()
            with cols[1]:
                reason = st.selectbox("Raison", reasons, key=f"reason_{cid}")
            with cols[2]:
                custom = st.number_input("qte", min_value=1, value=1, key=f"qty_{cid}")
                if st.button(f"+{custom} {unit_label}s — {name}", key=f"btn_custom_{cid}"):
                    record_click(cid, reason, float(custom))
                    st.success(f"{custom} {unit_label}(s) consommé(s)")
                    st.experimental_rerun()

with col2:
    st.subheader("Visualisation & Historique")
    df = get_clicks_dataframe()
    if df.empty:
        st.info("Aucun clic enregistré — cliquez sur une catégorie à gauche.")
    else:
        # show recent
        st.markdown("**Historique (récent en haut)**")
        st.dataframe(df)

    st.markdown("---")
    st.subheader("Vue par période")
    # aggregate remaining per category
    summary = []
    for cid, name, items_per_period, unit_value, unit_label in cats:
        used = clicks_this_period(cid)
        remaining = max(0, items_per_period - used)
        summary.append({"category": name, "items_per_period": items_per_period, "used": used, "remaining": remaining, "unit_value": unit_value, "unit_label": unit_label})
    s_df = pd.DataFrame(summary)
    st.table(s_df)

    total_value_used = sum(row[3] * row[4] for row in [(r[0], r[1], r[2], r[3], r[4]) for r in []])

    # quick export
    st.markdown("---")
    st.subheader("Exporter")
    if st.button("Télécharger l'historique CSV"):
        csv = df.to_csv(index=False)
        st.download_button("Download CSV", csv, file_name="items_history.csv", mime="text/csv")

st.markdown("---")
st.caption('Prototype - idée : items = unités de dépense. Ce code est un prototype minimal pour tester le concept.')
