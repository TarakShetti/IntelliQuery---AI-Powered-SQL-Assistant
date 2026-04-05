import streamlit as st
import pandas as pd
import sqlite3
from google import genai
import json

# ---------------------------
# CONFIG
# ---------------------------
st.set_page_config(page_title="IntelliQuery - AI SQL Assistant", layout="wide")
st.title("📊 IntelliQuery: AI-Powered SQL Insights")

# ---------------------------
# API KEY
# ---------------------------
api_key = ""
client = genai.Client(api_key=api_key)

# ---------------------------
# DATABASE CACHE
# ---------------------------
@st.cache_resource
def create_db(df):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    df.to_sql("data", conn, index=False, if_exists="replace")
    return conn

# ---------------------------
# JSON FLATTENER
# ---------------------------
def flatten_json(data):
    if isinstance(data, dict):
        for key in data:
            if isinstance(data[key], list):
                return pd.json_normalize(data[key])
        return pd.json_normalize([data])
    elif isinstance(data, list):
        return pd.json_normalize(data)
    return pd.DataFrame()

# ---------------------------
# FILE UPLOAD
# ---------------------------
uploaded_file = st.file_uploader(
    "Upload your dataset (Excel, CSV, JSON, XML, SQL)",
    type=["xlsx", "csv", "json", "xml", "sql"]
)

if uploaded_file:
    file_name = uploaded_file.name.lower()
    
    try:
        if file_name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)

        elif file_name.endswith(".xlsx"):
            df = pd.read_excel(uploaded_file)

        elif file_name.endswith(".json"):
            data = json.load(uploaded_file)
            df = flatten_json(data)

        elif file_name.endswith(".xml"):
            df = pd.read_xml(uploaded_file)

        elif file_name.endswith(".sql"):
            sql_text = uploaded_file.read().decode("utf-8")
            conn = sqlite3.connect(":memory:", check_same_thread=False)
            conn.executescript(sql_text)

            tables = pd.read_sql_query(
                "SELECT name FROM sqlite_master WHERE type='table';", conn
            )
            if len(tables) == 0:
                st.error("⚠️ No tables found in SQL file.")
                st.stop()

            table_name = tables.iloc[0, 0]
            df = pd.read_sql_query(f"SELECT * FROM {table_name} LIMIT 1000", conn)

        else:
            st.error("⚠️ Unsupported file format.")
            st.stop()

    except Exception as e:
        st.error(f"❌ Failed to read file: {e}")
        st.stop()

    # ---------------------------
    # CLEAN DATA
    # ---------------------------
    if df.empty:
        st.error("⚠️ Uploaded file is empty.")
        st.stop()

    df.columns = df.columns.str.replace(" ", "_")
    df.columns = df.columns.str.replace(r"[^\w]", "", regex=True)
    df = df.head(1000)

    st.subheader("🔍 Dataset Preview")
    st.dataframe(df.head())

    if 'conn' not in locals():
        conn = create_db(df)

    # ---------------------------
    # SCHEMA
    # ---------------------------
    column_info = "\n".join([f"{col} ({dtype})" for col, dtype in zip(df.columns, df.dtypes)])
    sample_data = df.head(3).to_string(index=False)

    schema_context = f"""
Table Name: data

Columns:
{column_info}

Sample Rows:
{sample_data}
"""

    st.subheader("📌 Dataset Schema")
    st.code(schema_context)

    # ---------------------------
    # USER INPUT
    # ---------------------------
    user_question = st.text_input("💬 Ask a question about your dataset")

    if user_question:
        with st.spinner("Generating SQL query..."):

            prompt = f"""
You are a strict SQLite SQL generator.

Rules:
- Only SELECT statements
- ALWAYS return a COMPLETE query
- MUST include FROM clause
- Use COUNT(*) for "how many" questions
- Use exact column names
- No incomplete SQL

Examples:
Q: how many males are there?
A: SELECT COUNT(*) FROM data WHERE gender = 'male'

Q: list people above 30
A: SELECT * FROM data WHERE age > 30

{schema_context}

Question: {user_question}

SQL:
"""

            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt
                )

                sql_query = response.text.replace("```sql", "").replace("```", "").strip()

                # Extract SELECT lines
                lines = [line.strip() for line in sql_query.splitlines() if line.strip().lower().startswith("select")]

                if lines:
                    sql_query = " ".join(lines)
                else:
                    sql_query = ""

                # VALIDATION
                if (
                    not sql_query.lower().startswith("select")
                    or len(sql_query.split()) < 4
                    or "from" not in sql_query.lower()
                ):
                    sql_query = "SELECT * FROM data LIMIT 5"

                st.subheader("🧾 Generated SQL")
                st.code(sql_query, language="sql")

                # ---------------------------
                # EXECUTE
                # ---------------------------
                result = pd.read_sql_query(sql_query, conn)

                st.subheader("📊 Query Result")
                st.dataframe(result)

                # ---------------------------
                # RESPONSE
                # ---------------------------
                with st.spinner("Generating human-friendly answer..."):
                    answer_prompt = f"""
User Question: {user_question}

SQL Query:
{sql_query}

SQL Result:
{result.head(10).to_string(index=False)}

Give a simple, clear, human-readable answer.
"""
                    answer = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=answer_prompt
                    )

                st.subheader("🤖 AI Answer")
                st.success(answer.text)

            except Exception as e:
                st.error(f"❌ Error: {e}")
