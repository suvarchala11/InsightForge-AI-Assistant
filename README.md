# InsightForge AI Assistant

**InsightForge** is a secure, **agentic** internal analytics assistant built to answer business questions by reasoning across your private structured and unstructured data.

## 🧠 How It Works

**InsightForge** is an **Agentic AI Application**. That means instead of just chatting with a pre-trained language model, the LLM acts as a "reasoning engine" that can decide to use tools to fetch your private data before answering.

Here is the exact flow when you ask a question:

1. **You ask a question** in the frontend UI.
2. **The Backend (FastAPI)** sends your question to the LLM (e.g., DeepSeek/Qianfan) alongside a list of available "Tools".
3. **The LLM decides what data it needs**:
   - If it needs **Structured Data** (metrics, revenue, ratings), it calls the query_sql_database tool. It actually writes a SQL SELECT query on the fly!
   - If it needs **Unstructured Data** (explanations, policies, reports), it calls the search_internal_documents tool. It provides a keyword to search.
4. **The Backend executes the tools**:
   - **Structured Search**: Queries the local SQLite database containing ingested .csv files (e.g., movies.csv, marketing_spend.csv).
   - **Unstructured Search**: Queries the SQLite FTS5 (Full-Text Search) index containing ingested .md and .pdf files.
5. **The LLM synthesizes the final answer** based *only* on the data returned by the tools, completely avoiding hallucination. 

### 🛡️ Graceful Fallback
If the LLM API goes down, times out, or hits a rate limit (HTTP 429), the backend automatically engages a **deterministic fallback**. It will run pre-programmed SQL and Document searches to guarantee you still get an answer and keep the system usable.

---

## 💻 How to Use It

Once **InsightForge** is running, you interact with it via the React Frontend.

### 1. The Chat Interface
Type business questions into the chat box. The assistant will reply with grounded answers. Look at the bottom of the assistant's reply for the **Sources Used** badge.
* SQL Database: The AI successfully pulled structured data from the CSVs.
* Document Search: The AI successfully pulled unstructured text from PDFs or Markdown files.

### 2. Security & Trace Panel
To ensure explainability and verify the LLM's guardrails, review the **Security & Trace** feature on the right side of the UI:
* **Filters (Release Year & Region)**: By selecting specific constraints (e.g., 2023, Middle East), these parameters are strictly injected into the prompt as guidance so the AI only retrieves permitted segments.
* **Tool-Based Restrictions**: The UI strictly limits what the AI can do on the backend, only exposing `query_sql_database(query)` and `search_internal_documents(keyword)`. The AI has no raw/unrestricted access.
* **Latest Tool Execution / Traces**: Whenever the AI generates an answer, you can view the actual SQL queries the AI wrote or the exact keywords it searched in the documents. You'll see the exact JSON traces it received back from the backend.

### 3. Dynamic Charts
When the AI pulls structured data that includes numeric comparisons (like a list of movies and their revenues), the UI will automatically render a **Chart** using Recharts to visualize the SQL results perfectly.

---

## 🚀 Setup & Installation

### Prerequisites
- Python 3.11+
- Node.js 18+

### Step 1: Environment Variables
Create a .env file in the root directory:
`ash
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://qianfan.baidubce.com/v2/coding  # Or any OpenAI-compatible endpoint
LLM_MODEL=deepseek-v3.2
`

### Step 2: Backend Setup
Install the dependencies, generate the dummy PDFs, and ingest all the data into the local SQLite database.
`ash
# 1. Install dependencies
python -m pip install -r requirements.txt

# 2. Generate Demo PDFs 
python tools/generate_demo_pdfs.py

# 3. Ingest CSVs, MDs, and PDFs into SQLite
python backend/database.py

# 4. Start the Backend Server
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
`
*(Note: If you get a Windows socket/access error on port 8000, ensure no other python/uvicorn process is running in the background).*

### Step 3: Frontend Setup
Open a new terminal window to start the Vite/React frontend.
`ash
cd frontend
npm install
npm run dev
`
Open the http://localhost:5173/ link in your browser.

---

## 🎯 Example Questions to Try

To see both the SQL tool and the Document Search tool working together, try these prompts:

1. **"Which titles performed best in 2025?"**
   *(Expects: SQL query on movies/revenue).*
2. **"Why is Stellar Run trending recently?"**
   *(Expects: Document search to find the marketing report).*
3. **"Compare Dark Orbit vs Last Kingdom."**
   *(Expects: SQL queries for ratings/revenue PLUS Document search for qualitative context).*
4. **"What explains weak comedy performance?"**
   *(Expects: Both data types to explain market saturation).*
5. **"Which city had the strongest engagement last month?"**
   *(Expects: SQL query on the watch_activity table).*

---

## 🏗️ Repo Structure

- /backend — FastAPI application, AI agent logic (\gent.py\), and SQLite ingestion logic (\database.py\).
- /data — The raw source files (\.csv\, \.md\, \.pdf\).
- /frontend — React + Vite UI containing the chat, trace visualizer, and charting components.
- /tools — Helper scripts.
