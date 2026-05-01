import asyncio
import json
import logging
import os
import re
from typing import Any

import requests
from dotenv import load_dotenv
from .database import execute_sql, search_documents

# Explicitly point to the .env file in the root directory
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path, override=True)

# Ensure the API key does not have trailing spaces or quotes
api_key = os.getenv("OPENAI_API_KEY", "").strip().strip('"').strip("'")
base_url = os.getenv("OPENAI_BASE_URL", "").strip().strip('"').strip("'")

logger = logging.getLogger("secure_insights")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

logger.info(
    "Loaded AI config: api_key_present=%s api_key_len=%s base_url=%s model=%s",
    bool(api_key),
    len(api_key),
    base_url,
    os.getenv("LLM_MODEL", "xiaomi-mimo-2.5-pro"),
)


def get_sanitized_config():
    """Return non-sensitive runtime configuration for debugging."""
    return {
        "api_key_present": bool(api_key),
        "api_key_len": len(api_key),
        "base_url": base_url,
        "model": os.getenv("LLM_MODEL", "xiaomi-mimo-2.5-pro"),
    }


def _chat_completions_url() -> str:
    return f"{base_url.rstrip('/')}/chat/completions"


def _post_chat_completions(payload: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        _chat_completions_url(),
        headers=headers,
        json=payload,
        timeout=30,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Chat completion request failed with status {response.status_code}: {response.text}"
        )

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"Chat completion response was not valid JSON: {response.text}") from exc


async def _call_chat_completions(payload: dict[str, Any]) -> dict[str, Any]:
    return await asyncio.to_thread(_post_chat_completions, payload)

# Define tools for the AI
tools = [
    {
        "type": "function",
        "function": {
            "name": "query_sql_database",
            "description": "Runs a SQL SELECT query against the internal SQLite database to get structured business data. "
                           "The SQLite DB is built by ingesting data/*.csv, so each CSV becomes a table. "
                           "Common demo tables: movies (title, genre, release_year, revenue_millions, rating), "
                           "viewers (user_id, age_group, subscription_tier, country, active_days_last_month), "
                           "watch_activity (activity_month, region, city, title, watch_hours, avg_engagement_score, unique_viewers), "
                           "reviews (title, review_count, avg_review_rating, common_feedback), "
                           "marketing_spend (campaign_name, channel, spend_thousands, conversions, roi_percent), "
                           "regional_performance (region, total_viewers, avg_engagement_score, top_genre).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A valid SQLite SELECT query."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_internal_documents",
            "description": "Searches internal documents (Markdown and PDFs, if present) for unstructured insights, context, or explanations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "The search term or keyword to look for in the documents (e.g. 'Stellar Run', 'policy', 'comedy')."
                    }
                },
                "required": ["keyword"]
            }
        }
    }
]


def _fallback_answer_from_traces(traces: list[dict[str, Any]]) -> str:
    if not traces:
        return "I couldn't retrieve any data to answer that."

    tool_names: list[str] = []
    for trace in traces:
        tool = trace.get("tool")
        if isinstance(tool, str) and tool and tool not in tool_names:
            tool_names.append(tool)

    tools_used = ", ".join(tool_names) if tool_names else "the available tools"
    return (
        "I retrieved data using "
        f"{tools_used}, but the model returned an empty final response. "
        "Please review the tool traces panel for the raw results."
    )


_INVOKE_RE = re.compile(r"<invoke\s+name=\"([^\"]+)\">(.*?)</invoke>", re.IGNORECASE | re.DOTALL)
_PARAM_RE = re.compile(r"<parameter\s+name=\"([^\"]+)\"[^>]*>(.*?)</parameter>", re.IGNORECASE | re.DOTALL)


def _extract_xml_tool_calls(text: str) -> list[dict[str, Any]]:
    """Extract tool calls from models that emit XML-style tool syntax in message content.

    Example:
      <function_calls>
        <invoke name="search_internal_documents">
          <parameter name="keyword">Stellar Run</parameter>
        </invoke>
      </function_calls>
    """
    if not isinstance(text, str) or "<invoke" not in text:
        return []

    calls: list[dict[str, Any]] = []
    for invoke_match in _INVOKE_RE.finditer(text):
        function_name = (invoke_match.group(1) or "").strip()
        invoke_body = invoke_match.group(2) or ""

        args: dict[str, Any] = {}
        for param_match in _PARAM_RE.finditer(invoke_body):
            param_name = (param_match.group(1) or "").strip()
            param_value = (param_match.group(2) or "").strip()
            if param_name:
                args[param_name] = param_value

        if function_name:
            calls.append({"name": function_name, "arguments": args})

    return calls


def _sanitize_final_answer(text: str) -> str:
    """Ensure the frontend receives clean plain text.

    Removes:
    - Markdown bold markers (**)
    - XML tool call markup that some model gateways may emit
    """
    t = (text or "")
    t = t.replace("**", "")

    # Remove tool-call markup blocks if they leak into final content.
    t = re.sub(r"<function_calls>.*?</function_calls>", "", t, flags=re.IGNORECASE | re.DOTALL)
    t = re.sub(r"<invoke\b.*?</invoke>", "", t, flags=re.IGNORECASE | re.DOTALL)
    t = re.sub(r"<parameter\b.*?</parameter>", "", t, flags=re.IGNORECASE | re.DOTALL)

    # Remove any stray tags if malformed/unclosed.
    t = re.sub(r"</?function_calls\b[^>]*>", "", t, flags=re.IGNORECASE)
    t = re.sub(r"</?invoke\b[^>]*>", "", t, flags=re.IGNORECASE)
    t = re.sub(r"</?parameter\b[^>]*>", "", t, flags=re.IGNORECASE)

    return t.strip()


def _summarize_llm_error(exc: Exception) -> str:
    msg = str(exc) if exc is not None else ""
    status_match = re.search(r"status\s+(\d{3})", msg, flags=re.IGNORECASE)
    status = status_match.group(1) if status_match else None

    code_match = re.search(r"\"code\"\s*:\s*\"([^\"]+)\"", msg)
    code = code_match.group(1) if code_match else None

    parts: list[str] = []
    if status:
        parts.append(f"HTTP {status}")
    if code:
        parts.append(code)
    return " ".join(parts) if parts else (type(exc).__name__ or "LLM error")


def _is_http_429(exc: Exception) -> bool:
    msg = str(exc) if exc is not None else ""
    return bool(re.search(r"status\s+429\b", msg, flags=re.IGNORECASE))


def _sources_used_from_traces(traces: list[dict[str, Any]]) -> str:
    tool_names: list[str] = []
    for trace in traces:
        tool = trace.get("tool")
        if isinstance(tool, str) and tool and tool not in tool_names:
            tool_names.append(tool)
    return ", ".join(tool_names) if tool_names else "(none)"


def _compact_result_for_llm(result: Any, *, max_rows: int = 25, max_chars: int = 1200) -> Any:
    """Make tool results safe/compact for an LLM context window."""
    if result is None:
        return None

    if isinstance(result, str):
        s = result.strip()
        return s[:max_chars] + ("..." if len(s) > max_chars else "")

    if isinstance(result, list):
        rows = result[:max_rows]
        compact_rows: list[Any] = []
        for r in rows:
            if isinstance(r, dict):
                compact_row: dict[str, Any] = {}
                for k, v in list(r.items())[:30]:
                    if isinstance(v, str):
                        vv = v.strip()
                        compact_row[k] = vv[:400] + ("..." if len(vv) > 400 else "")
                    else:
                        compact_row[k] = v
                compact_rows.append(compact_row)
            else:
                compact_rows.append(r)
        if len(result) > max_rows:
            compact_rows.append({"_truncated": f"{len(result) - max_rows} more rows"})
        return compact_rows

    if isinstance(result, dict):
        compact: dict[str, Any] = {}
        for k, v in list(result.items())[:50]:
            compact[k] = _compact_result_for_llm(v, max_rows=max_rows, max_chars=max_chars)
        if len(result) > 50:
            compact["_truncated"] = f"{len(result) - 50} more keys"
        return compact

    return result


def _compact_traces_for_llm(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    for t in traces:
        if not isinstance(t, dict):
            continue
        compacted.append(
            {
                "tool": t.get("tool"),
                "query": t.get("query"),
                "result": _compact_result_for_llm(t.get("result")),
            }
        )
    return compacted


_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _numbers_in_text(text: str) -> set[str]:
    return set(_NUMBER_RE.findall(text or ""))


def _looks_like_nonfinal_response(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True

    starters = (
        "let me ",
        "i'll ",
        "i will ",
        "i am going to ",
        "one moment",
        "give me ",
        "i can help ",
        "sure, ",
    )
    if t.startswith(starters):
        # Many tool-calling models emit a planning sentence; treat as non-final.
        return True

    if len(t) < 80 and any(w in t for w in ("search", "check", "look up", "query", "pull data")):
        return True

    return False


async def _summarize_with_llm_from_traces(
    user_message: str,
    traces: list[dict[str, Any]],
    *,
    model_name: str,
    draft_answer: str | None = None,
) -> str | None:
    """Ask the LLM to summarize already-retrieved tool results (no tool-calling)."""

    compacted = _compact_traces_for_llm(traces)
    traces_json = json.dumps(compacted, ensure_ascii=False)

    system_prompt = (
        "You are InsightForge, an internal analytics assistant for an entertainment company. "
        "You will be given tool outputs from a SQL database and document search. "
        "The tools have already been executed; you MUST produce the final answer now. "
        "Answer the user's question using ONLY the provided tool outputs. "
        "Do not invent facts, numbers, or claims. "
        "Do not say you will search/check/query or request additional tools. "
        "If the tool outputs are insufficient, say so and explain what is missing. "
        "If a draft answer is provided, rewrite it for clarity WITHOUT introducing any new numbers or specific claims beyond the draft. "
        "Output must be plain text (no Markdown formatting such as **bold**)."
    )

    draft_block = ""
    if isinstance(draft_answer, str) and draft_answer.strip():
        draft_block = f"\n\nDraft answer (derived from tool outputs):\n{draft_answer.strip()}"

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"User question:\n{user_message}\n\n"
                    f"Tool outputs (JSON):\n{traces_json}"
                    f"{draft_block}"
                ),
            },
        ],
        "temperature": 0.2,
    }

    try:
        resp = await _call_chat_completions(payload)
    except Exception:
        return None

    msg = resp.get("choices", [{}])[0].get("message", {})
    text = msg.get("content")
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not text:
        return None
    if _looks_like_nonfinal_response(text):
        return None

    if isinstance(draft_answer, str) and draft_answer.strip():
        allowed_numbers = _numbers_in_text(draft_answer) | _numbers_in_text(user_message) | {str(i) for i in range(1, 11)}
        out_numbers = _numbers_in_text(text)
        extra = {n for n in out_numbers if n not in allowed_numbers}
        if extra:
            return None
    return text


def _fallback_without_llm(user_message: str, error_message: str | None = None) -> dict[str, Any]:
    """Deterministic fallback when the LLM is unavailable (quota/network).

    This keeps the system usable and still enforces tool-based access boundaries.
    """

    traces: list[dict[str, Any]] = []
    question = (user_message or "").strip()
    q_lower = question.lower()

    def run_sql(query: str) -> Any:
        result = execute_sql(query)
        traces.append({"tool": "SQL Database", "query": query, "result": result})
        return result

    def run_docs(keyword: str) -> Any:
        result = search_documents(keyword)
        traces.append({"tool": "Document Search", "query": keyword, "result": result})
        return result

    def safe_first_row_value(rows: Any, key: str) -> Any:
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return rows[0].get(key)
        return None

    # Common helpers
    year_match = re.search(r"\b(20\d{2})\b", question)
    year = int(year_match.group(1)) if year_match else None

    titles_rows = run_sql("SELECT title FROM movies")
    known_titles = [r.get("title") for r in (titles_rows or []) if isinstance(r, dict) and r.get("title")]
    matched_titles = [t for t in known_titles if t.lower() in q_lower]

    latest_month_rows = run_sql("SELECT MAX(activity_month) AS latest_month FROM watch_activity")
    latest_month = safe_first_row_value(latest_month_rows, "latest_month")

    # 1) City engagement questions
    if "city" in q_lower and ("engagement" in q_lower or "strong" in q_lower or "highest" in q_lower):
        if latest_month:
            top_cities = run_sql(
                "SELECT city, region, avg_engagement_score, watch_hours, unique_viewers "
                "FROM watch_activity "
                f"WHERE activity_month = '{latest_month}' "
                "ORDER BY avg_engagement_score DESC, watch_hours DESC "
                "LIMIT 5"
            )
            if isinstance(top_cities, list) and top_cities:
                best = top_cities[0]
                answer_lines = [
                    f"Strongest city engagement for {latest_month}: {best.get('city')} ({best.get('region')})",
                    f"- Avg engagement score: {best.get('avg_engagement_score')}",
                    f"- Watch hours: {best.get('watch_hours')}",
                    f"- Unique viewers: {best.get('unique_viewers')}",
                    "",
                    "Sources Used: SQL Database (watch_activity)",
                ]
                if error_message:
                    answer_lines.append(f"Note: LLM unavailable ({error_message}); used tool-only fallback.")
                return {"answer": "\n".join(answer_lines).strip(), "traces": traces}

        answer = "I could not determine the latest month from watch_activity, so I can't compute strongest city engagement. Sources Used: SQL Database."
        if error_message:
            answer += f"\nNote: LLM unavailable ({error_message}); used tool-only fallback."
        return {"answer": answer, "traces": traces}

    # 1b) Region engagement questions
    if "region" in q_lower and ("engagement" in q_lower or "strong" in q_lower or "highest" in q_lower):
        if latest_month:
            top_regions = run_sql(
                "SELECT region, AVG(avg_engagement_score) AS avg_engagement_score, "
                "SUM(watch_hours) AS watch_hours, SUM(unique_viewers) AS unique_viewers "
                "FROM watch_activity "
                f"WHERE activity_month = '{latest_month}' "
                "GROUP BY region "
                "ORDER BY avg_engagement_score DESC, watch_hours DESC "
                "LIMIT 5"
            )
            if isinstance(top_regions, list) and top_regions:
                best = top_regions[0]
                answer_lines = [
                    f"Strongest region engagement for {latest_month}: {best.get('region')}",
                    f"- Avg engagement score: {best.get('avg_engagement_score')}",
                    f"- Watch hours: {best.get('watch_hours')}",
                    f"- Unique viewers: {best.get('unique_viewers')}",
                    "",
                    "Sources Used: SQL Database (watch_activity)",
                ]
                if error_message:
                    answer_lines.append(f"Note: LLM unavailable ({error_message}); used tool-only fallback.")
                return {"answer": "\n".join(answer_lines).strip(), "traces": traces}

        answer = "I could not determine the latest month from watch_activity, so I can't compute strongest region engagement. Sources Used: SQL Database."
        if error_message:
            answer += f"\nNote: LLM unavailable ({error_message}); used tool-only fallback."
        return {"answer": answer, "traces": traces}

    # 2) Trending / why questions
    if "trending" in q_lower or q_lower.startswith("why") or "why " in q_lower:
        # Use document search as primary explanation source.
        docs = run_docs(question)
        # If a specific title is mentioned, pull metrics too.
        if matched_titles:
            title = matched_titles[0]
            escaped_title = title.replace("'", "''")
            run_sql(
                "SELECT title, genre, release_year, revenue_millions, rating "
                f"FROM movies WHERE title = '{escaped_title}'"
            )
            run_sql(
                "SELECT campaign_name, channel, spend_thousands, conversions, roi_percent "
                "FROM marketing_spend "
                f"WHERE campaign_name LIKE '%{escaped_title}%'"
            )

        snippet = None
        if isinstance(docs, list) and docs:
            snippet = docs[0].get("content") if isinstance(docs[0], dict) else None

        answer_lines = [
            "Based on internal documents, here is the likely explanation:",
        ]
        if snippet:
            answer_lines.append(f"- {snippet.strip()}")
        else:
            answer_lines.append("- I did not find a matching explanation in the indexed documents.")
        answer_lines.append("")
        answer_lines.append("Sources Used: Document Search" + (", SQL Database" if matched_titles else ""))
        if error_message:
            answer_lines.append(f"Note: LLM unavailable ({error_message}); used tool-only fallback.")
        return {"answer": "\n".join(answer_lines).strip(), "traces": traces}

    # 2b) Genre performance explanations (e.g., "weak comedy performance")
    if "comedy" in q_lower and any(w in q_lower for w in ("weak", "underperform", "performance", "explain")):
        docs = run_docs("comedy performance")

        where_year = f" AND release_year = {year}" if year else ""
        comedy_movies = run_sql(
            "SELECT title, genre, release_year, revenue_millions, rating "
            "FROM movies "
            f"WHERE genre = 'Comedy'{where_year} "
            "ORDER BY revenue_millions DESC"
        )
        comedy_reviews = run_sql(
            "SELECT r.title, r.review_count, r.avg_review_rating, r.common_feedback "
            "FROM reviews r JOIN movies m ON r.title = m.title "
            f"WHERE m.genre = 'Comedy'{where_year} "
            "ORDER BY r.avg_review_rating ASC"
        )
        comedy_marketing = run_sql(
            "SELECT campaign_name, channel, spend_thousands, conversions, roi_percent "
            "FROM marketing_spend "
            "WHERE campaign_name LIKE '%Comedy%' "
            "ORDER BY roi_percent ASC"
        )

        snippet = None
        if isinstance(docs, list) and docs:
            for d in docs:
                if isinstance(d, dict) and isinstance(d.get("content"), str):
                    s = d["content"].strip()
                    if s:
                        snippet = s
                        break

        answer_lines = ["Comedy performance appears weak based on the available internal data:"]

        if isinstance(comedy_movies, list) and comedy_movies:
            top = comedy_movies[0]
            answer_lines.append(
                f"- Title: {top.get('title')} ({top.get('release_year')}) revenue=${top.get('revenue_millions')}M, rating={top.get('rating')}"
            )

        if isinstance(comedy_reviews, list) and comedy_reviews:
            r0 = comedy_reviews[0]
            answer_lines.append(
                f"- Reviews: avg_review_rating={r0.get('avg_review_rating')} across {r0.get('review_count')} reviews; common feedback: {r0.get('common_feedback')}"
            )

        if isinstance(comedy_marketing, list) and comedy_marketing:
            m0 = comedy_marketing[0]
            answer_lines.append(
                f"- Marketing: {m0.get('campaign_name')} ({m0.get('channel')}) ROI={m0.get('roi_percent')}% on spend={m0.get('spend_thousands')}k"
            )

        if snippet:
            answer_lines.append("")
            answer_lines.append("Document context (excerpt):")
            answer_lines.append(snippet[:800] + ("..." if len(snippet) > 800 else ""))

        answer_lines.append("")
        answer_lines.append("Sources Used: SQL Database, Document Search")
        if error_message:
            answer_lines.append(f"Note: LLM unavailable ({error_message}); used tool-only fallback.")
        return {"answer": "\n".join(answer_lines).strip(), "traces": traces}

    # 3) Compare / vs questions
    if "compare" in q_lower or " vs " in q_lower or "versus" in q_lower:
        if len(matched_titles) >= 2:
            a, b = matched_titles[0], matched_titles[1]
            a_escaped = a.replace("'", "''")
            b_escaped = b.replace("'", "''")
            movies = run_sql(
                "SELECT title, genre, release_year, revenue_millions, rating "
                f"FROM movies WHERE title IN ('{a_escaped}', '{b_escaped}')"
            )
            reviews = run_sql(
                "SELECT title, review_count, avg_review_rating, common_feedback "
                f"FROM reviews WHERE title IN ('{a_escaped}', '{b_escaped}')"
            )
            watch_rows = None
            if latest_month:
                watch_rows = run_sql(
                    "SELECT title, region, SUM(watch_hours) AS total_watch_hours, AVG(avg_engagement_score) AS avg_engagement "
                    "FROM watch_activity "
                    f"WHERE activity_month = '{latest_month}' AND title IN ('{a_escaped}', '{b_escaped}') "
                    "GROUP BY title, region "
                    "ORDER BY total_watch_hours DESC"
                )

            run_docs(f"{a} {b}")
            run_docs(f"{a} vs {b}")

            def index_by_title(rows: Any) -> dict[str, dict[str, Any]]:
                by_title: dict[str, dict[str, Any]] = {}
                if isinstance(rows, list):
                    for r in rows:
                        if isinstance(r, dict) and isinstance(r.get("title"), str):
                            by_title[r["title"]] = r
                return by_title

            movies_by_title = index_by_title(movies)
            reviews_by_title = index_by_title(reviews)

            a_movie = movies_by_title.get(a, {})
            b_movie = movies_by_title.get(b, {})
            a_review = reviews_by_title.get(a, {})
            b_review = reviews_by_title.get(b, {})

            def safe_float(v: Any) -> float | None:
                try:
                    if v is None:
                        return None
                    return float(v)
                except (TypeError, ValueError):
                    return None

            a_rating = safe_float(a_movie.get("rating"))
            b_rating = safe_float(b_movie.get("rating"))
            a_review_rating = safe_float(a_review.get("avg_review_rating"))
            b_review_rating = safe_float(b_review.get("avg_review_rating"))
            a_revenue = safe_float(a_movie.get("revenue_millions"))
            b_revenue = safe_float(b_movie.get("revenue_millions"))

            # Simple heuristic: prefer higher user sentiment (reviews + rating), then revenue.
            def score(title_rating: float | None, review_rating: float | None, revenue: float | None) -> float:
                s = 0.0
                if title_rating is not None:
                    s += title_rating * 10
                if review_rating is not None:
                    s += review_rating * 10
                if revenue is not None:
                    s += revenue
                return s

            a_score = score(a_rating, a_review_rating, a_revenue)
            b_score = score(b_rating, b_review_rating, b_revenue)
            winner = a if a_score >= b_score else b

            answer_lines = [
                f"Comparison: {a} vs {b}",
                "",
                "Structured metrics:",
                f"- {a}: rating={a_movie.get('rating')}, revenue_millions={a_movie.get('revenue_millions')}, avg_review_rating={a_review.get('avg_review_rating')}, review_count={a_review.get('review_count')}",
                f"- {b}: rating={b_movie.get('rating')}, revenue_millions={b_movie.get('revenue_millions')}, avg_review_rating={b_review.get('avg_review_rating')}, review_count={b_review.get('review_count')}",
            ]

            if latest_month and isinstance(watch_rows, list) and watch_rows:
                answer_lines += [
                    "",
                    f"Audience engagement snapshot ({latest_month}): see tool traces for region breakdown.",
                ]

            answer_lines += [
                "",
                f"Overall (based on available structured metrics), {winner} looks stronger.",
                "",
                "Sources Used: SQL Database (movies, reviews, watch_activity), Document Search",
            ]

            if error_message:
                answer_lines.append(f"Note: LLM unavailable ({error_message}); used tool-only fallback.")
            return {"answer": "\n".join(answer_lines).strip(), "traces": traces}

    # 4) Best/performance questions by year
    if ("performed best" in q_lower or "best" in q_lower or "top" in q_lower) and year:
        movies_yr = run_sql(
            "SELECT title, genre, release_year, revenue_millions, rating "
            f"FROM movies WHERE release_year = {year} ORDER BY revenue_millions DESC"
        )
        run_sql(
            "SELECT r.title, r.review_count, r.avg_review_rating, r.common_feedback, m.revenue_millions, m.rating "
            "FROM reviews r JOIN movies m ON r.title = m.title "
            f"WHERE m.release_year = {year} ORDER BY m.revenue_millions DESC"
        )
        docs = run_docs(str(year))

        if isinstance(movies_yr, list) and movies_yr:
            best = movies_yr[0]
            answer_lines = [
                f"Best-performing titles in {year} (by revenue):",
                f"1) {best.get('title')} - ${best.get('revenue_millions')}M revenue, rating {best.get('rating')}",
            ]
            for i, row in enumerate(movies_yr[1:5], start=2):
                answer_lines.append(
                    f"{i}) {row.get('title')} - ${row.get('revenue_millions')}M revenue, rating {row.get('rating')}"
                )

            # Add a short, relevant document snippet when available for the "why" context.
            doc_snippet = None
            if isinstance(docs, list):
                for d in docs:
                    if isinstance(d, dict) and isinstance(d.get("content"), str):
                        content = d["content"].strip()
                        if len(content) >= 120:
                            doc_snippet = content
                            break
            if isinstance(doc_snippet, str) and doc_snippet:
                answer_lines.append("")
                answer_lines.append("Document context (excerpt):")
                answer_lines.append(doc_snippet[:800] + ("..." if len(doc_snippet) > 800 else ""))

            answer_lines.append("")
            answer_lines.append("Sources Used: SQL Database, Document Search")
            if error_message:
                answer_lines.append(f"Note: LLM unavailable ({error_message}); used tool-only fallback.")
            return {"answer": "\n".join(answer_lines).strip(), "traces": traces}

    # 5) Recommendations / leadership
    if "recommend" in q_lower or "leadership" in q_lower or "next quarter" in q_lower:
        docs = run_docs("Recommendations for Leadership")
        run_sql("SELECT campaign_name, channel, spend_thousands, roi_percent FROM marketing_spend ORDER BY roi_percent DESC")

        snippet = None
        if isinstance(docs, list) and docs:
            snippet = docs[0].get("content") if isinstance(docs[0], dict) else None

        answer_lines = ["Recommendations (from internal docs + marketing performance):"]
        if snippet:
            answer_lines.append(snippet.strip())
        answer_lines.append("")
        answer_lines.append("Sources Used: Document Search, SQL Database")
        if error_message:
            answer_lines.append(f"Note: LLM unavailable ({error_message}); used tool-only fallback.")
        return {"answer": "\n".join(answer_lines).strip(), "traces": traces}

    # Default: do a broad doc search + a small SQL preview.
    if len(q_lower) < 5 or q_lower in ("hi", "hello", "hey", "hola", "help"):
        answer = "Hello! I am InsightForge. Please ask me a specific business question about movies, regions, or viewers."
        if error_message:
            answer += f"\nNote: LLM unavailable ({error_message}); used tool-only fallback."
        return {"answer": answer, "traces": []}

    run_docs(question)
    
    # Try to apply the extracted year to the default query
    where_clause = f"WHERE release_year = {year}" if year else ""
    run_sql(f"SELECT title, release_year, revenue_millions, rating FROM movies {where_clause} ORDER BY revenue_millions DESC LIMIT 5")

    answer = "I pulled relevant internal data, but I need a more specific question (e.g., a year, a title, or a region/city). Sources Used: SQL Database, Document Search."
    if error_message:
        answer += f"\nNote: LLM unavailable ({error_message}); used tool-only fallback."
    return {"answer": answer, "traces": traces}

async def process_chat_message(user_message: str):
    """Orchestrates the LLM and tool calling."""
    
    messages = [
        {
            "role": "system",
            "content": (
                "You are InsightForge, an internal analytics assistant for an entertainment company. "
                "You must use the provided tools to answer questions about movies, viewers, and engagement. "
                "Base your answer only on the tool results you receive; do not invent facts, numbers, or claims. "
                "If the data is insufficient, say so and explain what is missing. "
                "If the user asks for comparison or analysis, use both the structured SQL database and unstructured internal documents when helpful. "
                "For city/region engagement questions, prefer the watch_activity table (it directly links title, city/region, and month). "
                "Do not claim a title performed best in a region unless the tool results include a direct title-to-region signal (e.g., watch_activity); otherwise state the limitation. "
                "In your final response, clearly indicate which sources were used. "
                "Do not output a 'planning' message like 'Let me check/search'—always produce the final answer once you have tool results. "
                "Output must be plain text (no Markdown formatting such as **bold**)."
            ),
        },
        {"role": "user", "content": user_message},
    ]
    
    traces = [] # Keep track of which tools were used and the raw data payload
    
    model_name = os.getenv("LLM_MODEL", "xiaomi-mimo-2.5-pro")

    max_tool_iterations = 8
    for _ in range(max_tool_iterations):
        request_payload = {
            "model": model_name,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }

        try:
            response = await _call_chat_completions(request_payload)
        except Exception as exc:
            logger.exception(
                "OpenAI request failed: model=%s base_url=%s api_key_present=%s api_key_len=%s error_type=%s error=%s",
                model_name,
                base_url,
                bool(api_key),
                len(api_key),
                type(exc).__name__,
                exc,
            )
            # Retrieve deterministically and (optionally) rewrite the draft using a no-tools LLM call.
            retrieved = _fallback_without_llm(user_message, None)

            llm_rewrite = None
            if _is_http_429(exc):
                llm_rewrite = await _summarize_with_llm_from_traces(
                    user_message,
                    retrieved.get("traces") or [],
                    model_name=model_name,
                    draft_answer=retrieved.get("answer") or "",
                )

            if isinstance(llm_rewrite, str) and llm_rewrite.strip():
                final_text = _sanitize_final_answer(llm_rewrite)
                if "sources used:" not in final_text.lower() and (retrieved.get("traces") or []):
                    final_text = (final_text + f"\n\nSources Used: {_sources_used_from_traces(retrieved.get('traces') or [])}").strip()
                return {"answer": final_text, "traces": retrieved.get("traces") or []}

            answer = retrieved.get("answer")
            if isinstance(answer, str):
                answer = _sanitize_final_answer(answer)
            return {"answer": answer or _fallback_answer_from_traces(retrieved.get("traces") or []), "traces": retrieved.get("traces") or []}

        response_message = response["choices"][0]["message"]

        # Handle Tool Calls
        if response_message.get("tool_calls"):
            messages.append(response_message) # append assistant's call to history
            
            for tool_call in response_message["tool_calls"]:
                function_name = tool_call["function"]["name"]
                try:
                    function_args = json.loads(tool_call["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    function_args = {}
                
                tool_result = None
                if function_name == "query_sql_database":
                    tool_result = execute_sql(function_args.get("query"))
                    traces.append({"tool": "SQL Database", "query": function_args.get("query"), "result": tool_result})
                elif function_name == "search_internal_documents":
                    tool_result = search_documents(function_args.get("keyword"))
                    traces.append({"tool": "Document Search", "query": function_args.get("keyword"), "result": tool_result})
                else:
                    tool_result = {"error": f"Unknown tool requested: {function_name}"}
                    
                messages.append({
                    "tool_call_id": tool_call["id"],
                    "role": "tool",
                    "name": function_name,
                    "content": json.dumps(tool_result)
                })
        else:
            # Some OpenAI-compatible gateways return tool calls as XML-like markup
            # inside the assistant message content instead of in `tool_calls`.
            xml_calls = _extract_xml_tool_calls(response_message.get("content") or "")
            if xml_calls:
                assistant_tool_calls = []
                for i, call in enumerate(xml_calls):
                    tool_call_id = f"xml_{len(traces)}_{i}_{call['name']}"
                    assistant_tool_calls.append(
                        {
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(call.get("arguments") or {}),
                            },
                        }
                    )

                # Append a synthetic tool-call message and execute each tool.
                messages.append({"role": "assistant", "tool_calls": assistant_tool_calls})

                for tool_call in assistant_tool_calls:
                    function_name = tool_call["function"]["name"]
                    function_args = json.loads(tool_call["function"].get("arguments") or "{}")

                    tool_result = None
                    if function_name == "query_sql_database":
                        tool_result = execute_sql(function_args.get("query"))
                        traces.append({"tool": "SQL Database", "query": function_args.get("query"), "result": tool_result})
                    elif function_name == "search_internal_documents":
                        tool_result = search_documents(function_args.get("keyword"))
                        traces.append({"tool": "Document Search", "query": function_args.get("keyword"), "result": tool_result})
                    else:
                        tool_result = {"error": f"Unknown tool requested: {function_name}"}

                    messages.append(
                        {
                            "tool_call_id": tool_call["id"],
                            "role": "tool",
                            "name": function_name,
                            "content": json.dumps(tool_result),
                        }
                    )

                # Continue the loop to let the model synthesize a final response.
                continue

            final_text = response_message.get("content")
            if isinstance(final_text, str):
                final_text = final_text.strip()

            if not final_text:
                final_text = _fallback_answer_from_traces(traces)

            if isinstance(final_text, str):
                final_text = _sanitize_final_answer(final_text)

            # Some providers occasionally return a non-final planning sentence even after tool calls.
            # If that happens, ask the LLM to summarize the existing traces without tool-calling.
            if isinstance(final_text, str) and traces and _looks_like_nonfinal_response(final_text):
                fallback = _fallback_without_llm(user_message, None)
                llm_rewrite = await _summarize_with_llm_from_traces(
                    user_message,
                    fallback.get("traces") or [],
                    model_name=model_name,
                    draft_answer=fallback.get("answer") or "",
                )
                if isinstance(llm_rewrite, str) and llm_rewrite.strip():
                    final_text = _sanitize_final_answer(llm_rewrite)
                    traces = fallback.get("traces") or []
                else:
                    ans = fallback.get("answer")
                    final_text = _sanitize_final_answer(ans) if isinstance(ans, str) else final_text
                    traces = fallback.get("traces") or []

            # Ensure sources are stated when traces exist.
            if isinstance(final_text, str) and traces and "sources used:" not in final_text.lower():
                final_text = (final_text + f"\n\nSources Used: {_sources_used_from_traces(traces)}").strip()

            if not final_text:
                final_text = _fallback_answer_from_traces(traces)

            return {"answer": final_text, "traces": traces}

    # If the model keeps requesting tools, stop the loop and return a deterministic answer.
    # (Some gateways/models get stuck in tool-call loops; also calling the LLM with the full
    # message history can be token-expensive and more likely to hit quota.)
    logger.warning("Maximum tool iterations reached; returning a deterministic tool-based answer.")
    fallback = _fallback_without_llm(user_message, None)

    llm_summary = await _summarize_with_llm_from_traces(
        user_message,
        fallback.get("traces") or [],
        model_name=model_name,
        draft_answer=fallback.get("answer") or "",
    )

    if isinstance(llm_summary, str) and llm_summary.strip():
        final_text = _sanitize_final_answer(llm_summary)
        if "sources used:" not in final_text.lower():
            final_text = (final_text + f"\n\nSources Used: {_sources_used_from_traces(fallback.get('traces') or [])}").strip()
        return {"answer": final_text, "traces": fallback.get("traces") or []}

    # No LLM summary available; return tool-only deterministic answer.
    answer = fallback.get("answer")
    if isinstance(answer, str):
        answer = _sanitize_final_answer(answer)
    return {"answer": answer or _fallback_answer_from_traces(fallback.get("traces") or []), "traces": fallback.get("traces") or []}