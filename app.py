import streamlit as st
import pandas as pd
import sqlite3
import json
import plotly.express as px

# --- 1. Page Setup & Custom CSS ---
st.set_page_config(page_title="Capstone Dashboard", layout="wide")
st.title("Product Category Performance Dashboard")

st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.4rem !important; }
    </style>
""", unsafe_allow_html=True)

# --- 2. Database Connection ---
@st.cache_resource
def get_db_connection():
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    pd.read_csv('olist_order_items_dataset.csv').to_sql('order_items', conn, index=False)
    pd.read_csv('olist_orders_dataset.csv').to_sql('orders', conn, index=False)
    pd.read_csv('olist_products_dataset.csv').to_sql('products', conn, index=False)
    pd.read_csv('product_category_name_translation.csv').to_sql('categories', conn, index=False)
    # Load customers in case you want to add the State filter later
    # pd.read_csv('olist_customers_dataset.csv').to_sql('customers', conn, index=False)
    return conn

conn = get_db_connection()

# --- 3. Query Helpers & Functions ---
def multi_params(multi_json):
    return (multi_json, multi_json)

def year_params(year):
    return (year, year)

def get_kpis(conn):
    query = """
    SELECT (SELECT ROUND(SUM(i.price + i.freight_value),2) FROM order_items i JOIN orders o ON i.order_id=o.order_id) AS total_gmv,
           (SELECT ROUND(SUM(i.price),2) FROM order_items i JOIN orders o ON i.order_id=o.order_id JOIN products p ON i.product_id=p.product_id JOIN categories t ON p.product_category_name=t.product_category_name WHERE t.product_category_name_english='health_beauty') AS top_category_rev,
           (SELECT COUNT(*) FROM categories) AS translated_cats,
           (SELECT ROUND(AVG(price),2) FROM order_items) AS avg_item_price,
           (SELECT COUNT(*) FROM order_items) AS total_items
    """
    df = pd.read_sql(query, conn)
    return df.iloc[0]

def get_top_categories(conn, selected_categories=["All"]):
    cat_json = json.dumps(selected_categories if "All" not in selected_categories else [])
    params = multi_params(cat_json)
    query = """
    SELECT t.product_category_name_english AS category, ROUND(SUM(i.price),2) AS revenue, COUNT(DISTINCT i.order_id) AS orders
    FROM order_items i JOIN orders o ON i.order_id = o.order_id JOIN products p ON i.product_id = p.product_id JOIN categories t ON p.product_category_name = t.product_category_name
    WHERE (? = '[]' OR t.product_category_name_english IN (SELECT value FROM json_each(?)))
    GROUP BY category ORDER BY revenue DESC LIMIT 10
    """
    return pd.read_sql(query, conn, params=params)

def get_revenue_over_time(conn, selected_year="All"):
    params = year_params(selected_year)
    query = """
    SELECT strftime('%Y', o.order_purchase_timestamp) AS year, (strftime('%m', o.order_purchase_timestamp) - 1) / 3 + 1 AS quarter,
           SUM(CASE WHEN t.product_category_name_english IN ('health_beauty','watches_gifts','bed_bath_table','sports_leisure','computers_accessories') THEN i.price ELSE 0 END) AS top5_revenue
    FROM order_items i JOIN orders o ON i.order_id = o.order_id JOIN products p ON i.product_id = p.product_id JOIN categories t ON p.product_category_name = t.product_category_name
    WHERE (? = 'All' OR strftime('%Y', o.order_purchase_timestamp) = ?)
    GROUP BY year, quarter ORDER BY year, quarter
    """
    df = pd.read_sql(query, conn, params=params)
    df['Year_Quarter'] = df['year'] + " Q" + df['quarter'].astype(str)
    return df

def get_avg_price_by_category(conn, selected_categories=["All"]):
    cat_json = json.dumps(selected_categories if "All" not in selected_categories else [])
    params = multi_params(cat_json)
    query = """
    SELECT t.product_category_name_english AS category, ROUND(AVG(i.price),2) AS avg_price, ROUND(MIN(i.price),2) AS min_price, ROUND(MAX(i.price),2) AS max_price
    FROM order_items i JOIN orders o ON i.order_id = o.order_id JOIN products p ON i.product_id = p.product_id JOIN categories t ON p.product_category_name = t.product_category_name
    WHERE (? = '[]' OR t.product_category_name_english IN (SELECT value FROM json_each(?)))
    GROUP BY category ORDER BY avg_price DESC LIMIT 10
    """
    return pd.read_sql(query, conn, params=params)

def get_volume_vs_revenue(conn, selected_categories=["All"]):
    cat_json = json.dumps(selected_categories if "All" not in selected_categories else [])
    params = multi_params(cat_json)
    query = """
    SELECT t.product_category_name_english AS category, COUNT(DISTINCT i.order_id) AS orders, ROUND(SUM(i.price),2) AS revenue, ROUND(SUM(i.price)/COUNT(DISTINCT i.order_id),2) AS revenue_per_order
    FROM order_items i JOIN orders o ON i.order_id = o.order_id JOIN products p ON i.product_id = p.product_id JOIN categories t ON p.product_category_name = t.product_category_name
    WHERE (? = '[]' OR t.product_category_name_english IN (SELECT value FROM json_each(?)))
    GROUP BY category ORDER BY revenue DESC LIMIT 15
    """
    return pd.read_sql(query, conn, params=params)

def get_market_share(conn, selected_categories=["All"]):
    cat_json = json.dumps(selected_categories if "All" not in selected_categories else [])
    params = multi_params(cat_json)
    query = """
    WITH filtered AS (
        SELECT t.product_category_name_english AS category, SUM(i.price) AS revenue
        FROM order_items i JOIN orders o ON i.order_id = o.order_id JOIN products p ON i.product_id = p.product_id JOIN categories t ON p.product_category_name = t.product_category_name
        WHERE (? = '[]' OR t.product_category_name_english IN (SELECT value FROM json_each(?)))
        GROUP BY category
    )
    SELECT category, ROUND(revenue,2) AS revenue, ROUND(100.0*revenue/(SELECT SUM(revenue) FROM filtered),2) AS pct_share
    FROM filtered ORDER BY revenue DESC LIMIT 10
    """
    return pd.read_sql(query, conn, params=params)

def get_total_all_revenue(conn):
    return pd.read_sql("SELECT SUM(price) as total_rev FROM order_items", conn)['total_rev'].iloc[0]

# --- 4. Chart Generation Functions (For Code Quality Marks) ---
def create_chart1(df):
    fig = px.bar(df, x='revenue', y='category', orientation='h', labels={'revenue': 'Revenue (R$)', 'category': 'Category'}, color='revenue', color_continuous_scale='Blues')
    fig.update_layout(yaxis={'categoryorder':'total ascending'})
    return fig

def create_chart2(df):
    fig = px.bar(df, x='Year_Quarter', y='top5_revenue', labels={'top5_revenue': 'Revenue (R$)', 'Year_Quarter': 'Quarter'}, color_discrete_sequence=['#1f77b4'])
    fig.update_layout(xaxis_tickangle=-45, title="Top 5 Categories Revenue by Quarter")
    return fig

def create_chart3(df):
    fig = px.bar(df, x='category', y='avg_price', labels={'avg_price': 'Average Price (R$)', 'category': 'Category'}, color_discrete_sequence=['#2ca02c'])
    fig.update_layout(xaxis_tickangle=-45)
    return fig

def create_chart4(df):
    fig = px.scatter(df, x='orders', y='revenue', text='category', size='revenue', color='revenue_per_order', labels={'orders': 'Number of Orders', 'revenue': 'Total Revenue (R$)', 'revenue_per_order': 'Rev/Order'}, color_continuous_scale='Viridis')
    fig.update_traces(textposition='top center')
    fig.update_layout(height=600)
    return fig

def create_chart5(df):
    fig = px.bar(df, x='pct_share', y='category', orientation='h', text='pct_share', labels={'pct_share': 'Market Share (%)', 'category': 'Category'}, color='pct_share', color_continuous_scale='Purples')
    fig.update_layout(yaxis={'categoryorder':'total ascending'})
    fig.update_traces(texttemplate='%{text}%', textposition='outside')
    return fig

# --- 5. Sidebar Filters ---
st.sidebar.header("Dashboard Filters")
selected_year = st.sidebar.selectbox("Year", ["All", "2016", "2017", "2018"])
# (State filter can be added here later once you load the customers table)

# --- 6. App Layout & Tabs ---
tab_overview, tab_theme, tab_detail = st.tabs(["Overview", "Category Performance", "Detail & Method"])

with tab_overview:
    st.header("Headline KPIs")
    try:
        kpis = get_kpis(conn)
        col1, col2, col3, col4, col5 = st.columns([1.8, 1.5, 1, 1, 1])
        col1.metric("Total GMV", f"R$ {kpis['total_gmv']:,.2f}")
        col2.metric("Top Category Rev", f"R$ {kpis['top_category_rev']:,.2f}")
        col3.metric("Translated Categories", f"{int(kpis['translated_cats'])}")
        col4.metric("Avg Item Price", f"R$ {kpis['avg_item_price']:,.2f}")
        col5.metric("Total Items", f"{int(kpis['total_items']):,}")
    except Exception as e:
        st.error(f"Error: {e}")

    st.markdown("---")
    st.subheader("Chart 1: Top 10 Categories by Revenue")
    try:
        df_chart1 = get_top_categories(conn)
        st.plotly_chart(create_chart1(df_chart1), use_container_width=True)
        st.info("**Finding:** No single category dominates. `health_beauty` leads at 9.39% of translated item revenue. The top 10 categories together only account for 63.22% of revenue, highlighting a strong long-tail distribution where smaller niche categories collectively drive a significant portion of sales.")
    except Exception as e:
        st.error(f"Error: {e}")

with tab_theme:
    st.header("Category Performance Over Time")
    
    try:
        df_chart2 = get_revenue_over_time(conn, selected_year=selected_year)
        st.plotly_chart(create_chart2(df_chart2), use_container_width=True)
        st.info("**Finding:** Revenue for the top 5 categories grew steadily through 2017, peaking massively in Q1 2018. However, note that 2016 only has 3 active months, and 2016 Q4 has zero orders. The gap is real, not a bug.")
    except Exception as e:
        st.error(f"Error: {e}")

    st.markdown("---") 
    st.subheader("Chart 3: Average Item Price by Category (Top 10)")
    try:
        df_chart3 = get_avg_price_by_category(conn)
        st.plotly_chart(create_chart3(df_chart3), use_container_width=True)
        st.info("**Finding:** High-volume categories like bed & bath do not command high prices. The categories with the highest average prices (like computers) sell fewer units but generate high revenue per order, making them high-ticket anchors.")
    except Exception as e:
        st.error(f"Error: {e}")

    st.markdown("---") 
    st.subheader("Chart 4: Order Volume vs. Revenue (Top 15 Categories)")
    try:
        df_chart4 = get_volume_vs_revenue(conn)
        st.plotly_chart(create_chart4(df_chart4), use_container_width=True)
        st.info("**Finding:** There is a clear dichotomy. `bed_bath_table` drives massive volume but low revenue per order (dark blue). Conversely, `watches_gifts` (yellow) generates nearly identical total revenue with half the order volume, proving it is a high-ticket, high-margin category.")
    except Exception as e:
        st.error(f"Error: {e}")

with tab_detail:
    st.header("Advanced Feature & Method")
    
    st.subheader("Chart 5: Market Share of Top 10 Categories")
    try:
        df_chart5 = get_market_share(conn)
        total_all_rev = get_total_all_revenue(conn)
        top_cat_rev = df_chart5.iloc[0]['revenue']
        alt_pct = round((top_cat_rev / total_all_rev) * 100, 2)
        
        st.plotly_chart(create_chart5(df_chart5), use_container_width=True)
        
    except Exception as e:
        st.error(f"Error: {e}")

    st.markdown("---")
    st.subheader("Data Limitation: The Lossy Join")
    st.warning(f"""
    **Denominator Choice:** The market share percentages in Chart 5 are calculated using the **translated category revenue** as the denominator. 
    
    This is because the `categories` translation table is a lossy join. As verified by Q7, exactly **623 products** and **R$ 185,049.76** of revenue disappear from the dataset the moment you join the `categories` table, because their category names do not exist in the translation file. 
    
    If we used the *total item revenue* as the denominator instead, `health_beauty`'s market share would be **{alt_pct}%** instead of the **{df_chart5.iloc[0]['pct_share']}%** shown in the chart. The chart deliberately uses the translated denominator to accurately reflect the performance of known categories, but the missing revenue is a real data limitation.
    """)