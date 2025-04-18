import streamlit as st
import pandas as pd
import time
from datetime import datetime
from pymongo import MongoClient
from openai import OpenAI
import json
import re

#--------------------------------------------------------------------------------
# CSS & Page Config
#--------------------------------------------------------------------------------
st.set_page_config(
    page_title="Requests Dashboard",
    layout="wide",
    initial_sidebar_state="auto",
)
st.markdown("""
<style>
/* Center the main title */
h1[data-testid="stTitle"] {
    text-align: center;
    margin-bottom: 0.5rem;
}
/* Distribute tabs evenly and constrain max‑width */
div[data-baseweb="tab-list"][role="tablist"] {
    display: flex !important;
    justify-content: space-evenly !important;
    max-width: 80vw !important;
    margin: 0 auto 1rem auto !important;
}
/* Style each tab button: padding, divider */
div[data-baseweb="tab-list"][role="tablist"] button[data-baseweb="tab"] {
    flex: 1 1 auto !important;
    padding: 0.8rem 0 !important;
    border-right: 1px solid rgba(255,255,255,0.2) !important;
    background: none !important;
}
/* Remove divider on the last tab */
div[data-baseweb="tab-list"][role="tablist"] button[data-baseweb="tab"]:last-child {
    border-right: none !important;
}
/* Increase the tab label text */
div[data-baseweb="tab-list"][role="tablist"] button[data-baseweb="tab"] div[data-testid="stMarkdownContainer"] > p {
    font-size: 1.25rem !important;
    line-height: 1.3 !important;
    margin: 0 !important;
    padding: 0 !important;
}
</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------------------------
# 1) MongoDB Setup
# -------------------------------------------------------------------------------
MONGODB_URI = "mongodb+srv://cmillerjr:GyfC0t2s2Y6M64jd@mocklists.x5nczjz.mongodb.net/?retryWrites=true&w=majority&appName=MockLists"
mongo_client = MongoClient(MONGODB_URI)
collection = mongo_client["MockLists"]["requests"]

# -------------------------------------------------------------------------------
# 2) Config & Data Schemas
# -------------------------------------------------------------------------------
REQUEST_CHOICES = ["New Request", "Update"]
TYPE_CHOICES = [
    "Quote", "Place Order", "Proof", "Sample", "Issue Log",
    "Sourcing", "Wearables", "CC Payment", "Convert",
    "Update Quote", "Follow-Up"
]
STATUS_CHOICES = [
    "NEW REQUEST", "CLOSED", "QUOTE ENTERED", "MISSING INFO",
    "WEARABLES SENT", "SOURCING SENT", "PROOF REQUESTED",
    "SAMPLE ENTERED", "DUPLICATE", "WAITING APPROVAL",
    "PENDING CUSTOMER RESP.", "WORKING ORDER",
]
COLUMNS = [
    "Title", "ACCT & SEG#", "Request", "Type", "Request Details", "Priority",
    "Status", "Virtual Req#", "Sourcing/Wearable#", "Quote#", "Order#",
    "Sample#", "Request Date", "Assigned To",
]

# -------------------------------------------------------------------------------
# 3) Data Handling Functions
# -------------------------------------------------------------------------------
def load_data() -> pd.DataFrame:
    docs = list(collection.find())
    if not docs:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.DataFrame(docs)
    if "_id" in df.columns:
        df.drop(columns=["_id"], inplace=True)
    return df

def save_data(df: pd.DataFrame):
    collection.delete_many({})
    records = df.to_dict(orient="records")
    if records:
        collection.insert_many(records)

def process_and_save_request(request_data: dict):
    new_row = pd.DataFrame([request_data])
    st.session_state["requests_data"] = pd.concat(
        [st.session_state["requests_data"], new_row],
        ignore_index=True
    )
    save_data(st.session_state["requests_data"])

def force_page_refresh():
    """Force a Streamlit rerun via a changing query‑param hack."""
    st.experimental_set_query_params(_=str(time.time()))
    st.stop()

# -------------------------------------------------------------------------------
# 4) AI Helper Function
# -------------------------------------------------------------------------------
def generate_single_request(prompt: str) -> dict:
    system_instructions = (
        "You are an entity‑extraction assistant. From the user’s text, return exactly ONE JSON object "
        "with these keys: "
        "\"Title\", \"ACCT & SEG#\", \"Request\", \"Type\", \"Request Details\", "
        "\"Priority\", \"Status\", \"Virtual Req#\", \"Sourcing/Wearable#\", "
        "\"Quote#\", \"Order#\", \"Sample#\", \"Request Date\" (YYYY-MM-DD), \"Assigned To\".\n\n"
        "**Required**: \"Request\" and \"Type\". Default to \"New Request\" and infer Type if missing.\n\n"
        "**ACCT & SEG#**: 8 digits plus optional space+2 digits.\n\n"
        "**Quote#**: 8 digits starting with 003,004,005…\n\n"
        "**Order#**: 8 digits starting with 3 or 6 (not quote pattern).\n\n"
        "**Type**: multi‑select from the list based on keywords (quote, place order, proof, issue, etc.).\n\n"
        "**Request Date**: parse YYYY-MM-DD, MM/DD/YYYY, or MM/DD → output YYYY-MM-DD.\n\n"
        "**Request Details**: provide a concise summary of the original text; do not repeat extracted values.\n\n"
        "Return only valid JSON, no commentary."
    )
    try:
        resp = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=800,
            temperature=0.3,
        )
        raw = resp.choices[0].message.content.strip()
        parsed = json.loads(raw)
        if isinstance(parsed, list) and parsed:
            parsed = parsed[0]
        # normalize date
        date_str = parsed.get("Request Date", "")
        m = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$", date_str)
        if m:
            y = m.group(3) or str(datetime.now().year)
            if len(y) == 2: y = "20" + y
            mm = m.group(1).zfill(2)
            dd = m.group(2).zfill(2)
            parsed["Request Date"] = f"{y}-{mm}-{dd}"
        return parsed

    except Exception as e:
        st.error(f"Error generating request: {e}")
        return None

# -------------------------------------------------------------------------------
# 5) App Init & Session State
# -------------------------------------------------------------------------------
if "requests_data" not in st.session_state:
    st.session_state["requests_data"] = load_data()
if "ai_generated_form" not in st.session_state:
    st.session_state["ai_generated_form"] = None

# Initialize OpenAI client
openai_client = OpenAI(api_key=st.secrets["openai"]["api_key"])

st.title("Requests Dashboard")
tab_analytics, tab_form, tab_open, tab_closed, tab_ai = st.tabs([
    "Analytics", "Request Form", "Open Requests", "Closed Requests", "AI Assistant"
])

# -------------------------------------------------------------------------------
# Tab 1: Analytics
# -------------------------------------------------------------------------------
with tab_analytics:
    st.header("Analytics Overview")
    df = st.session_state["requests_data"]
    st.metric("Open Requests",  len(df[df["Status"] != "CLOSED"]))
    st.metric("Closed Requests", len(df[df["Status"] == "CLOSED"]))

# -------------------------------------------------------------------------------
# Tab 2: Manual Request Form
# -------------------------------------------------------------------------------
with tab_form:
    st.subheader("Create a New Request")
    with st.form("request_form"):
        title            = st.text_input("Title")
        acct_seg         = st.text_input("ACCT & SEG#")
        request_choice   = st.selectbox("Request", REQUEST_CHOICES)
        type_choices     = st.multiselect("Type", TYPE_CHOICES)
        request_details  = st.text_area("Request Details", height=100)
        priority         = st.radio("Priority", ["Low", "Normal", "High"])
        status           = st.selectbox("Status", STATUS_CHOICES)
        virtual_req      = st.text_input("Virtual Req#")
        sourcing_wear    = st.text_input("Sourcing/Wearable#")
        quote_num        = st.text_input("Quote#")
        order_num        = st.text_input("Order#")
        sample_num       = st.text_input("Sample#")
        request_date     = st.date_input("Request Date", datetime.now())
        assigned_to      = st.text_input("Assigned To (Name or Email)")

        def _save_manual():
            process_and_save_request({
                "Title":               title,
                "ACCT & SEG#":         acct_seg,
                "Request":             request_choice,
                "Type":                ", ".join(type_choices),
                "Request Details":     request_details,
                "Priority":            priority,
                "Status":              status,
                "Virtual Req#":        virtual_req,
                "Sourcing/Wearable#":  sourcing_wear,
                "Quote#":              quote_num,
                "Order#":              order_num,
                "Sample#":             sample_num,
                "Request Date":        request_date.strftime("%Y-%m-%d"),
                "Assigned To":         assigned_to,
            })
            force_page_refresh()

        st.form_submit_button("Submit", on_click=_save_manual)

# -------------------------------------------------------------------------------
# Tab 3: Open Requests
# -------------------------------------------------------------------------------
with tab_open:
    st.subheader("Open Requests")
    mask_open = st.session_state["requests_data"]["Status"] != "CLOSED"
    open_df   = st.session_state["requests_data"].loc[mask_open, COLUMNS]

    edited_open = st.data_editor(
        open_df,
        column_config={"Status": st.column_config.SelectboxColumn("Status", options=STATUS_CHOICES)},
        num_rows="dynamic",
        use_container_width=True,
        key="editor_open",
    )

    def _save_open():
        closed_df = st.session_state["requests_data"].loc[
            st.session_state["requests_data"]["Status"] == "CLOSED", COLUMNS
        ]
        st.session_state["requests_data"] = pd.concat([edited_open, closed_df], ignore_index=True)
        save_data(st.session_state["requests_data"])
        force_page_refresh()

    st.button(
        "Save Changes",
        key="save_open_button",
        on_click=_save_open,
    )


# -------------------------------------------------------------------------------
# Tab 4: Closed Requests
# -------------------------------------------------------------------------------
with tab_closed:
    st.subheader("Closed Requests")
    mask_closed = st.session_state["requests_data"]["Status"] == "CLOSED"
    closed_df   = st.session_state["requests_data"].loc[mask_closed, COLUMNS]

    edited_closed = st.data_editor(
        closed_df,
        column_config={"Status": st.column_config.SelectboxColumn("Status", options=STATUS_CHOICES)},
        num_rows="dynamic",
        use_container_width=True,
        key="editor_closed",
    )

    def _save_closed():
        open_df = st.session_state["requests_data"].loc[
            st.session_state["requests_data"]["Status"] != "CLOSED", COLUMNS
        ]
        st.session_state["requests_data"] = pd.concat([open_df, edited_closed], ignore_index=True)
        save_data(st.session_state["requests_data"])
        force_page_refresh()

    st.button(
        "Save Changes",
        key="save_closed_button",
        on_click=_save_closed,
    )

# -------------------------------------------------------------------------------
# Tab 5: AI Assistant
# -------------------------------------------------------------------------------
with tab_ai:
    st.subheader("AI Assistant to Autofill Request Form")
    st.write(
        "Paste your email text or request details below. The AI will convert it into exactly "
        "one request object. Once generated, the form will persist so you can adjust any fields and then save it."
    )

    ai_prompt = st.text_area(
        "Enter the request details (e.g., an email snippet):",
        height=150,
        key="ai_prompt",
    )

    if st.button("Generate Single Request from AI", key="gen_ai"):
        if ai_prompt:
            parsed = generate_single_request(ai_prompt)
            if not parsed:
                st.error("No data returned or AI returned an empty output.")
            else:
                if not parsed.get("Request Details","").strip():
                    parsed["Request Details"] = ai_prompt
                st.session_state["ai_generated_form"] = parsed
        else:
            st.error("Please enter some details for the AI assistant to process.")

    if st.session_state.get("ai_generated_form"):
        form = st.session_state["ai_generated_form"]
        st.subheader("AI‑Suggested Request Form")
        st.info("Adjust any fields as needed, then click ‘Save Request (AI)’ or ‘Cancel Request (AI)’.")

        def val(k): return form.get(k,"")
        title_ai   = st.text_input("Title", value=val("Title"))
        acct_ai    = st.text_input("ACCT & SEG#", value=val("ACCT & SEG#"))

        # Request
        idx_req = REQUEST_CHOICES.index(val("Request")) if val("Request") in REQUEST_CHOICES else 0
        request_ai = st.selectbox("Request", REQUEST_CHOICES, index=idx_req)

        # Type
        raw_types     = val("Type") or ""
        candidates    = [t.strip() for t in raw_types.split(",")]
        type_defaults = [t for t in candidates if t in TYPE_CHOICES]
        type_ai       = st.multiselect("Type", TYPE_CHOICES, default=type_defaults)

        rqdt_ai = st.text_area("Request Details", value=val("Request Details"), height=100)

        # Priority
        prios   = ["Low","Normal","High"]
        idx_pr  = prios.index(val("Priority")) if val("Priority") in prios else 1
        priority_ai = st.radio("Priority", prios, index=idx_pr)

        # Status
        idx_st  = STATUS_CHOICES.index(val("Status")) if val("Status") in STATUS_CHOICES else 0
        status_ai   = st.selectbox("Status", STATUS_CHOICES, index=idx_st)

        vr_ai    = st.text_input("Virtual Req#",       value=val("Virtual Req#"))
        sw_ai    = st.text_input("Sourcing/Wearable#", value=val("Sourcing/Wearable#"))
        q_ai     = st.text_input("Quote#",             value=val("Quote#"))
        o_ai     = st.text_input("Order#",             value=val("Order#"))
        s_ai     = st.text_input("Sample#",            value=val("Sample#"))

        def _parse_date(d):
            try:    return datetime.strptime(d, "%Y-%m-%d").date()
            except: return datetime.now().date()
        rd_ai   = st.date_input("Request Date", value=_parse_date(val("Request Date")))
        at_ai   = st.text_input("Assigned To (Name or Email)", value=val("Assigned To"))

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Save Request (AI)", key="save_ai"):
                process_and_save_request({
                    "Title":               title_ai,
                    "ACCT & SEG#":         acct_ai,
                    "Request":             request_ai,
                    "Type":                ", ".join(type_ai),
                    "Request Details":     rqdt_ai,
                    "Priority":            priority_ai,
                    "Status":              status_ai,
                    "Virtual Req#":        vr_ai,
                    "Sourcing/Wearable#":  sw_ai,
                    "Quote#":              q_ai,
                    "Order#":              o_ai,
                    "Sample#":             s_ai,
                    "Request Date":        rd_ai.strftime("%Y-%m-%d"),
                    "Assigned To":         at_ai,
                })
                st.session_state["ai_generated_form"] = None
                force_page_refresh()

        with c2:
            if st.button("Cancel Request (AI)", key="cancel_ai"):
                st.session_state["ai_generated_form"] = None
                st.info("AI‑generated form cleared. You can paste a new prompt above.")
