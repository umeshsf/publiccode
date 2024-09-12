import _snowflake
import json
import streamlit as st
import base64
from snowflake.snowpark.context import get_active_session
from snowflake.cortex import Complete
from typing import List
 
session = get_active_session()


DATABASE = "yourdb"
SCHEMA = "yourschema"
STAGE = "yourstage"
FILE = "yourfile.yaml"


FULLPATH = f"{DATABASE}.{SCHEMA}.{STAGE}"
user_input = ""

card_style = """
    {
        border: 1px groove #52546a;
        border-radius: 10px;
        padding-left: 25px;
        padding-top: 10px;
        padding-bottom: 10px;
        box-shadow: -6px 8px 20px 1px #00000052;
        white-space: break-spaces;
        text-wrap: wrap;
    }
"""

def stylable_container(key: str, css_styles: str ) -> "DeltaGenerator":
    # Sanitize key
    key = key.replace(" ", "-").lower()

    if isinstance(css_styles, str):
        css_styles = [css_styles]

    # Remove unneeded spacing that is added by the style markdown:
    css_styles.append(
        """
> div:first-child {
    margin-bottom: -1rem;
}
"""
    )

    style_text = """
<style>
"""

    for style in css_styles:
        style_text += f"""
div[data-testid="stVerticalBlock"]:has(> div.element-container > div.stMarkdown > \
div[data-testid="stMarkdownContainer"] > p > span.{key}) {style}
"""

    style_text += f"""
    </style>

<span class="{key}"></span>
"""

    container = st.container()
    container.markdown(style_text, unsafe_allow_html=True)
    return container


st.set_page_config(
    layout="wide")


def send_message(prompt: str) -> dict:
    """Calls the REST API and returns the response."""
    request_body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt 
                    }
                ]
            }
        ],
        "semantic_model_file": f"@{DATABASE}.{SCHEMA}.{STAGE}/{FILE}",
    }
    resp = _snowflake.send_snow_api_request(
        "POST",
        f"/api/v2/cortex/analyst/message",
        {},
        {},
        request_body,
        {},
        30000,
    )
    if resp["status"] < 400:
        return json.loads(resp["content"])
    else:
        raise Exception(
            f"Failed request with status {resp['status']}: {resp}"
        )

def process_message(prompt: str) -> None:
    """Processes a message and adds the response to the chat."""
    st.session_state.messages.append(
        {"role": "user", "content": [{"type": "text", "text": prompt}]}
    )
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Generating response..."):
            response = send_message(prompt=prompt)
            content = response["message"]["content"]
            display_content(content=content)
    st.session_state.messages.append({"role": "assistant", "content": content})


def display_content(content: list, message_index: int = None) -> None:
    """Displays a content item for a message."""
    message_index = message_index or len(st.session_state.messages)

    for item in content:
        if item["type"] == "text":
            st.markdown(item["text"])
        elif item["type"] == "suggestions":
            with st.expander("Suggestions", expanded=True):
                for suggestion_index, suggestion in enumerate(item["suggestions"]):
                    if st.button(suggestion, key=f"{message_index}_{suggestion_index}"):
                        st.session_state.active_suggestion = suggestion
        elif item["type"] == "sql":
            with st.expander("SQL Query", expanded=False):
                st.code(item["statement"], language="sql")
            with st.expander("Results", expanded=True):
                with st.spinner("Running SQL..."):
                    
                    #st.dataframe(session.sql("select current_session()").to_pandas())
                    df = session.sql(item["statement"]).to_pandas(statement_params={            "QUERY_TAG" :  "CORTEXANALYST"})
                    #df = session.sql(item["statement"]).collect()
                    #st.dataframe(df)
                    
                    if len(df.index) > 1:
                        data_tab, line_tab, bar_tab = st.tabs(
                            ["Data", "Line Chart", "Bar Chart"]
                        )
                        data_tab.dataframe(df)
                        if len(df.columns) > 1:
                            df = df.set_index(df.columns[0])
                        with line_tab:
                            st.line_chart(df)
                        with bar_tab:
                            st.bar_chart(df)
                    else:
                        tprompt=f"My question was {user_input}  and got answer in table like this: {df.to_string()} please rephrase answer in natural human readable way, only response with answer"
                        cout=Complete('snowflake-arctic',tprompt)
                        with stylable_container(
                                "respnoseblock",
                                """
                                code {
                                    white-space: pre-wrap !important;
                                }
                                """,
                            ):
                                st.code(cout)
            with st.expander("SQL Output", expanded=False):                            
                    st.dataframe(df)                

st.title("Consumption Analyst")
#st.markdown(f"Semantic Model: `{FILE}`")

if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.suggestions = []
    st.session_state.active_suggestion = None

for message_index, message in enumerate(st.session_state.messages):
    with st.chat_message(message["role"]):
        display_content(content=message["content"], message_index=message_index)

if user_input := st.chat_input("What is your question?"):
    process_message(prompt=user_input)

if st.session_state.active_suggestion:
    process_message(prompt=st.session_state.active_suggestion)
    st.session_state.active_suggestion = None
