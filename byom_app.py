"""
Cortex REST API Demo
Multi-turn chat demo using the Snowflake Cortex Inference REST API.
BYOM models (registered in MODELS.PUBLIC) are called directly via their
SPCS ingress endpoint using the dataframe_split format.
"""

import json
import os

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Cortex REST API Demo",
    page_icon="❄️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Built-in Cortex models
# ---------------------------------------------------------------------------
CORTEX_MODELS = [
    "mistral-large2",
    "llama3.1-70b",
    "llama3.1-8b",
    "llama3.3-70b",
    "snowflake-arctic-instruct",
    "mixtral-8x7b",
    "gemma-7b",
    "claude-3-5-sonnet",
    "claude-3-haiku",
]


# ---------------------------------------------------------------------------
# Snowflake connection helpers
# ---------------------------------------------------------------------------
@st.cache_resource
def get_session():
    """Return a Snowpark session — works locally and inside SiS."""
    try:
        from snowflake.snowpark.context import get_active_session  # noqa: PLC0415

        return get_active_session()
    except Exception:
        conn = st.connection("snowflake")
        return conn.session()


def get_rest_token(session) -> str:
    try:
        return session._conn._conn._rest._token
    except AttributeError:
        return session._conn._rest._token


def get_account_host(session) -> str:
    try:
        return session._conn._conn._rest._host
    except AttributeError:
        return session._conn._rest._host


def get_pat() -> str | None:
    """
    Return a Programmatic Access Token for BYOM SPCS endpoint calls.
    SPCS public endpoints require PAT auth; session tokens are rejected.
    Configure in .streamlit/secrets.toml:
      [snowflake]
      pat = "<your PAT>"
    Or set env var SNOWFLAKE_PAT.
    """
    # Check env var first
    pat = os.getenv("SNOWFLAKE_PAT", "")
    if pat:
        return pat
    # Then check secrets.toml
    try:
        return st.secrets["snowflake"]["pat"]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# BYOM model discovery
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def fetch_byom_models() -> list[dict]:
    """
    Return model-backed SPCS services from MODELS.PUBLIC with their ingress URLs.
    Each entry:
      label      — display string
      value      — unique key used as selectbox value (service name)
      service    — bare service name, e.g. GEMMA_3_4B_IT_V_2026_06_18__10_53_22_SERVICE
      status     — RUNNING / SUSPENDED / etc.
      ingress    — public ingress hostname, e.g. xyz-account.snowflakecomputing.app
    """
    session = get_session()
    try:
        svc_rows = session.sql("SHOW SERVICES IN SCHEMA MODELS.PUBLIC").collect()
    except Exception:
        return []

    results = []
    for row in svc_rows:
        row_dict = {k.lower(): v for k, v in row.as_dict().items()}
        if row_dict.get("managing_object_domain") != "Model" or str(row_dict.get("is_job", "")) == "true":
            continue
        svc_name = row_dict["name"]
        status = row_dict.get("status", "UNKNOWN")

        # Discover the ingress URL for this service
        ingress = None
        try:
            ep_rows = session.sql(
                f"SHOW ENDPOINTS IN SERVICE MODELS.PUBLIC.{svc_name}"
            ).collect()
            for ep in ep_rows:
                ep_dict = {k.lower(): v for k, v in ep.as_dict().items()}
                if str(ep_dict.get("is_public", "")).lower() == "true" and ep_dict.get("ingress_url"):
                    ingress = ep_dict["ingress_url"]
                    break
        except Exception:
            pass

        results.append(
            {
                "label": f"{svc_name}  [{status}]",
                "value": svc_name,          # used as selectbox key
                "service": svc_name,
                "status": status,
                "ingress": ingress,         # may be None if ingress not enabled
                # Fully-qualified uppercase name for AI_COMPLETE
                "ai_model": f"MODELS.PUBLIC.{svc_name}",
            }
        )
    return results


def is_byom(selected_value: str) -> bool:
    return selected_value not in CORTEX_MODELS and selected_value != "__separator__"


def build_model_options(byom_models: list[dict]) -> tuple[list[str], list[str]]:
    labels: list[str] = []
    values: list[str] = []
    if byom_models:
        for m in byom_models:
            labels.append(m["label"])
            values.append(m["value"])
        labels.append("──── Cortex built-in models ────")
        values.append("__separator__")
    labels.extend(CORTEX_MODELS)
    values.extend(CORTEX_MODELS)
    return labels, values


# ---------------------------------------------------------------------------
# API call — Cortex /complete (built-in models)
# ---------------------------------------------------------------------------
def cortex_complete(
    host: str,
    token: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> tuple[requests.Response, dict, dict]:
    url = f"https://{host}/api/v2/cortex/inference:complete"
    headers = {
        "Authorization": f'Snowflake Token="{token}"',
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    safe_headers = {**headers, "Authorization": 'Snowflake Token="<redacted>"'}
    resp = requests.post(url, headers=headers, json=body, timeout=120)
    return resp, body, safe_headers


def parse_cortex_response(resp_json: dict) -> tuple[str, dict]:
    """Return (answer_text, usage_dict)."""
    answer = resp_json["choices"][0]["message"]["content"]
    usage = resp_json.get("usage", {})
    return answer, usage


# ---------------------------------------------------------------------------
# API call — BYOM SPCS service (direct ingress)
# ---------------------------------------------------------------------------
def byom_call(
    ingress: str,
    token: str,  # must be a PAT; session tokens don't work for SPCS ingress
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> tuple[requests.Response, dict, dict]:
    """
    Call a BYOM model's SPCS ingress endpoint using the data array format.
    Format: {"data": [[row_index, arg1, arg2, ...]]}
    __CALL__ args: MESSAGES, TEMPERATURE, MAX_COMPLETION_TOKENS, STOP, N,
                   STREAM, TOP_P, FREQUENCY_PENALTY, PRESENCE_PENALTY
    URL path: underscores replaced by dashes → /--call--
    """
    url = f"https://{ingress}/--call--"
    headers = {
        "Authorization": f'Snowflake Token="{token}"',
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = {
        "data": [[
            0,            # row index
            messages,     # MESSAGES ARRAY
            temperature,  # TEMPERATURE FLOAT
            max_tokens,   # MAX_COMPLETION_TOKENS NUMBER
            None,         # STOP ARRAY (null = no stop sequences)
            1,            # N NUMBER
            False,        # STREAM BOOLEAN
            1.0,          # TOP_P FLOAT
            0.0,          # FREQUENCY_PENALTY FLOAT
            0.0,          # PRESENCE_PENALTY FLOAT
        ]]
    }
    safe_headers = {**headers, "Authorization": 'Snowflake Token="<PAT_redacted>"'}
    resp = requests.post(url, headers=headers, json=body, timeout=120)
    return resp, body, safe_headers


def parse_byom_response(resp_json: dict) -> tuple[str, dict]:
    """
    Parse the data-array response from the SPCS endpoint.
    Format: {"data": [[row_index, result_object], ...]}
    The result_object is OpenAI-compatible with 'choices' and 'usage'.
    """
    if "dataframe_split" in resp_json:
        obj = resp_json["dataframe_split"]["data"][0][0]
    # data array format: [[row_index, result_object], ...]
    elif "data" in resp_json:
        obj = resp_json["data"][0][1]
    else:
        obj = resp_json  # unexpected — return as-is

    if isinstance(obj, dict) and "choices" in obj:
        answer = obj["choices"][0]["message"]["content"]
        usage = obj.get("usage", {})
    else:
        answer = str(obj)
        usage = {}
    return answer, usage


# ---------------------------------------------------------------------------
# SQL: AI_COMPLETE call path
# ---------------------------------------------------------------------------
def ai_complete_sql(
    session,
    model: str,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> tuple[str, dict, str]:
    """
    Call AI_COMPLETE via Snowpark SQL using bind parameters (?).
    Works for both built-in Cortex models and BYOM service names.
    Returns (answer_text, usage_dict, sql_shown).
    """
    messages_json = json.dumps(messages)
    options_json = json.dumps({"temperature": temperature, "max_tokens": max_tokens})

    sql = "SELECT AI_COMPLETE(?, PARSE_JSON(?), PARSE_JSON(?)) AS response"

    # Display-friendly version shown in the inspector (not executed)
    sql_shown = (
        f"SELECT AI_COMPLETE(\n"
        f"  '{model}',\n"
        f"  PARSE_JSON('{messages_json}'),\n"
        f"  PARSE_JSON('{options_json}')\n"
        f") AS response"
    )

    rows = session.sql(sql, params=[model, messages_json, options_json]).collect()
    raw = rows[0]["RESPONSE"]

    if isinstance(raw, str):
        raw = json.loads(raw)

    if isinstance(raw, dict) and "choices" in raw:
        answer = raw["choices"][0]["message"]["content"]
        usage = raw.get("usage", {})
    else:
        answer = str(raw)
        usage = {}
    return answer, usage, sql_shown


# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------
for key, default in [
    ("messages", []),
    ("last_req", None),
    ("last_resp", None),
    ("last_model", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ---------------------------------------------------------------------------
# Boot the Snowflake session
# ---------------------------------------------------------------------------
try:
    session = get_session()
    host = get_account_host(session)
    current_user = session.get_current_user().strip('"')
    current_account = session.get_current_account().strip('"')
except Exception as exc:
    st.error(f"Could not connect to Snowflake: {exc}")
    st.stop()

pat = get_pat()  # PAT required for BYOM SPCS calls


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
byom_models = fetch_byom_models()
byom_by_value = {m["value"]: m for m in byom_models}
model_labels, model_values = build_model_options(byom_models)

with st.sidebar:
    st.title("Settings")
    st.caption(f"**User:** {current_user}  \n**Account:** {current_account}")
    st.divider()

    raw_idx = st.selectbox(
        "Model",
        options=range(len(model_labels)),
        format_func=lambda i: model_labels[i],
        index=0,
        help="Built-in Cortex models + BYOM services from MODELS.PUBLIC",
    )
    selected_model = model_values[raw_idx]
    if selected_model == "__separator__":
        st.warning("Select a model above or below the separator.")
        selected_model = CORTEX_MODELS[0]

    call_method = st.radio(
        "Call method",
        options=["SQL: AI_COMPLETE", "REST API"],
        index=0,
        help=(
            "**SQL: AI_COMPLETE** — runs `AI_COMPLETE(model, messages)` "
            "via Snowpark; no PAT needed.  \n"
            "**REST API** — calls the Cortex /complete endpoint (built-in models) "
            "or SPCS ingress directly (BYOM; PAT required)."
        ),
    )

    st.divider()

    temperature = st.slider("Temperature", 0.0, 1.0, 0.7, 0.05)
    max_tokens = st.number_input("Max tokens", 64, 4096, 512, 64)

    st.divider()
    system_prompt = st.text_area(
        "System prompt",
        value="You are a helpful assistant.",
        height=100,
    )

    st.divider()
    # Show which API endpoint will be used
    if is_byom(selected_model):
        meta = byom_by_value.get(selected_model, {})
        ingress = meta.get("ingress", "")
        ep_display = f"POST https://{ingress}/--call--" if ingress else "ingress URL not available"
    else:
        ep_display = f"POST https://{host}\n/api/v2/cortex/inference:complete"
    st.markdown("**Active endpoint**")
    if call_method == "SQL: AI_COMPLETE":
        st.code(f"AI_COMPLETE('{selected_model}', messages)", language="sql")
    else:
        st.code(ep_display, language="text")

    # PAT status for BYOM
    if byom_models:
        st.divider()
        if pat:
            st.success("PAT configured ✓ (BYOM calls ready)")
        else:
            st.warning(
                "**PAT required for BYOM models.**  \n"
                "Add to `.streamlit/secrets.toml`:\n"
                "```toml\n[snowflake]\npat = \"<your_PAT>\"\n```\n"
                "Create one in Snowsight: **Admin → Users → your user → "
                "Programmatic Access Tokens → Generate new token**"
            )

    show_api_panel = st.toggle("Show API inspector", value=True)

    if st.button("Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.last_req = None
        st.session_state.last_resp = None
        st.session_state.last_model = None
        st.rerun()


# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------
chat_col, api_col = st.columns([3, 2] if show_api_panel else [1, 0])

# ── Chat column ──────────────────────────────────────────────────────────────
with chat_col:
    st.title("❄️ Cortex REST API Demo")

    model_type = "BYOM (SPCS)" if is_byom(selected_model) else "Cortex Inference"
    st.caption(f"Model: **{selected_model}**  •  Type: {model_type}")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_input := st.chat_input("Ask anything…"):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        api_messages: list[dict] = []
        if system_prompt.strip():
            api_messages.append({"role": "system", "content": system_prompt.strip()})
        api_messages.extend(st.session_state.messages)

        with st.chat_message("assistant"):
            with st.spinner(f"Calling {selected_model}…"):
                try:
                    # ── SQL: AI_COMPLETE path ─────────────────────────────
                    if call_method == "SQL: AI_COMPLETE":
                        # BYOM: use fully-qualified uppercase service name
                        # Built-in: use model name as-is
                        if is_byom(selected_model):
                            ai_model = byom_by_value[selected_model].get(
                                "ai_model", f"MODELS.PUBLIC.{selected_model}"
                            )
                        else:
                            ai_model = selected_model
                        answer, usage, sql_shown = ai_complete_sql(
                            session, ai_model, api_messages,
                            temperature, max_tokens,
                        )
                        st.session_state.last_req = {
                            "type": "sql",
                            "sql": sql_shown,
                        }
                        st.session_state.last_resp = {
                            "status_code": 200,
                            "body": {"answer": answer, "usage": usage},
                        }

                    # ── REST API path ─────────────────────────────────────
                    else:
                        token = get_rest_token(session)
                        if is_byom(selected_model):
                            meta = byom_by_value[selected_model]
                            ingress = meta.get("ingress")
                            if not ingress:
                                st.error("No public ingress URL found for this service.")
                                st.stop()
                            if not pat:
                                st.error(
                                    "BYOM REST calls require a PAT.  \n"
                                    "Add `pat = \"...\"` under `[snowflake]` in "
                                    "`.streamlit/secrets.toml`.  \n"
                                    "Or switch to **SQL: AI_COMPLETE** which uses "
                                    "the session token."
                                )
                                st.stop()
                            resp, req_body, safe_headers = byom_call(
                                ingress, pat, api_messages, temperature, max_tokens
                            )
                            req_url = f"https://{ingress}/--call--"
                        else:
                            resp, req_body, safe_headers = cortex_complete(
                                host, token, selected_model, api_messages,
                                temperature, max_tokens,
                            )
                            req_url = f"https://{host}/api/v2/cortex/inference:complete"

                        st.session_state.last_req = {
                            "type": "rest",
                            "url": req_url,
                            "method": "POST",
                            "headers": safe_headers,
                            "body": req_body,
                        }
                        try:
                            resp_body = resp.json()
                        except Exception:
                            resp_body = resp.text
                        st.session_state.last_resp = {
                            "status_code": resp.status_code,
                            "body": resp_body,
                        }

                        if resp.status_code != 200:
                            st.error(f"HTTP {resp.status_code}: {resp.text[:600]}")
                            st.stop()

                        if is_byom(selected_model):
                            answer, usage = parse_byom_response(resp.json())
                        else:
                            answer, usage = parse_cortex_response(resp.json())

                    # ── Render answer (shared) ────────────────────────────
                    st.session_state.last_model = selected_model
                    st.markdown(answer)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": answer}
                    )
                    if usage:
                        st.caption(
                            f"Tokens — prompt: {usage.get('prompt_tokens', '?')}  "
                            f"completion: {usage.get('completion_tokens', '?')}  "
                            f"total: {usage.get('total_tokens', '?')}"
                        )

                except Exception as exc:
                    st.error(f"Request failed: {exc}")


# ── API inspector column ──────────────────────────────────────────────────────
if show_api_panel:
    with api_col:
        st.subheader("API Inspector")

        if not st.session_state.last_req:
            st.info("Send a message to see the request and response here.")
        else:
            req = st.session_state.last_req
            resp_data = st.session_state.last_resp

            if req.get("type") == "sql":
                # ── SQL mode ──────────────────────────────────────────────
                with st.expander("▶ SQL executed", expanded=True):
                    st.code(req["sql"], language="sql")

                with st.expander("◀ Response", expanded=True):
                    body = resp_data["body"]
                    if isinstance(body, dict):
                        st.json(body)
                    else:
                        st.code(body, language="text")

            else:
                # ── REST mode ─────────────────────────────────────────────
                with st.expander("▶ Request", expanded=True):
                    st.code(f"POST  {req['url']}", language="text")
                    st.markdown("**Headers**")
                    st.json(req["headers"])
                    st.markdown("**Body**")
                    st.json(req["body"])

                with st.expander("◀ Response", expanded=True):
                    status = resp_data["status_code"]
                    colour = "green" if status == 200 else "red"
                    st.markdown(f"**Status:** :{colour}[{status}]")
                    body = resp_data["body"]
                    if isinstance(body, dict):
                        st.json(body)
                    else:
                        st.code(body, language="text")

                with st.expander("📋 cURL equivalent", expanded=False):
                    curl = (
                        f"curl -X POST \\\n"
                        f'  "{req["url"]}" \\\n'
                        f"  -H 'Authorization: Snowflake Token=\"<your_token>\"' \\\n"
                        f"  -H 'Content-Type: application/json' \\\n"
                        f"  -d '{json.dumps(req['body'], indent=2)}'"
                    )
                    st.code(curl, language="bash")
