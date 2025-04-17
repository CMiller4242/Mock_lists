import streamlit as st
import pandas as pd
import os
import time
from datetime import datetime
from pymongo import MongoClient
from openai import OpenAI
import json


#--------------------------------------------------------------------------------
# CSS
#--------------------------------------------------------------------------------
st.set_page_config(
    page_title="Requests Dashboard",
    layout="wide",
    initial_sidebar_state="auto",
)

# 2) Custom CSS for header & tabs
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
div[data-baseweb="tab-list"][role="tablist"]
  button[data-baseweb="tab"] {
    flex: 1 1 auto !important;
    padding: 0.8rem 0 !important;
    border-right: 1px solid rgba(255,255,255,0.2) !important;
    background: none !important;
}

/* Remove divider on the last tab */
div[data-baseweb="tab-list"][role="tablist"]
  button[data-baseweb="tab"]:last-child {
    border-right: none !important;
}

/* Increase the tab label text (the <p> inside each tab) */
div[data-baseweb="tab-list"][role="tablist"]
  button[data-baseweb="tab"]
  div[data-testid="stMarkdownContainer"] > p {
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
client = MongoClient(MONGODB_URI)
db = client["MockLists"]         # Database name
collection = db["requests"]      # Collection name

# -------------------------------------------------------------------------------
# 2) Config & Data Schemas
# -------------------------------------------------------------------------------
REQUEST_TYPE_CHOICES = ["New", "Update", "Repair", "Others"]
# Only two options for “Request”
REQUEST_CHOICES = ["New Request", "Update"]

 # New multi‐select “Type” field
TYPE_CHOICES = [
     "Quote", "Place Order", "Proof", "Sample", "Issue Log",
     "Sourcing", "Wearables", "CC Payment", "Convert",
     "Update Quote", "Follow-Up"
 ]

STATUS_CHOICES = [
    "NEW REQUEST",
    "CLOSED",
    "QUOTE ENTERED",
    "MISSING INFO",
    "WEARABLES SENT",
    "SOURCING SENT",
    "PROOF REQUESTED",
    "SAMPLE ENTERED",
    "DUPLICATE",
    "WAITING APPROVAL",
    "PENDING CUSTOMER RESP.",
    "WORKING ORDER",
]

COLUMNS = [
     "Title", "ACCT & SEG#", "POP", "Request Details", "Request Type", "Priority",
     "Status", "Virtual Req#", "Sourcing/Wearable#", "Quote#", "Order#",
     "Sample#", "Request Date", "Assigned To",
 ]
COLUMNS = [
     "Title",
     "ACCT & SEG#",
     "Request",        # was “Request Type”
     "Type",           # new multi‐select
     "Request Details",
     "Priority",
     "Status",
     "Virtual Req#",
     "Sourcing/Wearable#",
     "Quote#",
     "Order#",
     "Sample#",
     "Request Date",
     "Assigned To",
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
    # For simplicity, clear and reinsert all docs.
    collection.delete_many({})
    data_dicts = df.to_dict(orient="records")
    if data_dicts:
        collection.insert_many(data_dicts)

def force_page_refresh():
    st.experimental_set_query_params(_=str(time.time()))
    st.stop()

# Helper function to save a request
def process_and_save_request(request_data: dict):
    new_row_df = pd.DataFrame([request_data])
    st.session_state["requests_data"] = pd.concat(
        [st.session_state["requests_data"], new_row_df],
        ignore_index=True
    )
    save_data(st.session_state["requests_data"])

# -------------------------------------------------------------------------------
# 4) AI Helper Function for Single Request Generation
# -------------------------------------------------------------------------------
def generate_single_request(prompt: str) -> dict:
    system_instructions = (
        "You are a data‐extraction assistant. From the user’s email text, return exactly ONE JSON object "
        "with these keys: \"Title\", \"ACCT & SEG#\", \"Request\", \"Type\", \"Request Details\", "
        "\"Priority\", \"Status\", \"Virtual Req#\", \"Sourcing/Wearable#\", \"Quote#\", \"Order#\", "
        "\"Sample#\", \"Request Date\" (YYYY-MM-DD), and \"Assigned To\".\n\n"

        "**ACCT & SEG#**: look for an 8‑digit number (leading zero allowed), a space, then 2 digits (00–99), "
        "e.g. “00581869 12”. Store in this field when found.\n\n"

        "**Quote#**: look for an 8‑digit number starting with 003 or 004. Store here when found.\n\n"

        "**Order#**: look for an 8‑digit number starting with 6 or 3 (but not 003). Store here when found.\n\n"

        "**Type** (choose exactly one):\n"
        "- If text says “quote” and you have an ACCT & SEG# but no explicit Quote# → “Quote”.\n"
        "- If text says “place order” or similar and you have an ACCT & SEG# → “Place Order”.\n"
        "- If Quote# is present but no ACCT & SEG# and text says “convert” → “Convert”.\n"
        "- If text mentions “proof”, “set up proofs”, or “proofs” → “Proof”.\n"
        "- If text mentions “issue”, “issue log”, or implies a problem → “Sample Issue Log”.\n\n"

        "Use sensible defaults for missing fields: Request = \"New Request\", Status = \"NEW REQUEST\", "
        "today’s date if not provided, and empty strings for other fields. Return ONLY valid JSON."
    )
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": prompt},
            ],
            max_tokens=800,
            temperature=0.3,
        )
        ai_output = response.choices[0].message.content.strip()
        parsed = json.loads(ai_output)
        if isinstance(parsed, list):
            if len(parsed) > 0:
                parsed = parsed[0]
            else:
                return None
        return parsed
    except Exception as e:
        st.error(f"Error generating single request: {e}")
        return None

# -------------------------------------------------------------------------------
# 5) App Initialization & Session State
# -------------------------------------------------------------------------------
if "requests_data" not in st.session_state:
    st.session_state["requests_data"] = load_data()
if "ai_generated_form" not in st.session_state:
    st.session_state["ai_generated_form"] = None  # For AI-generated form data

# Set the OpenAI API key from Streamlit secrets
client = OpenAI(api_key=st.secrets["openai"]["api_key"])

st.title("Requests Dashboard")

# Create five tabs: Analytics, Request Form, Open Requests, Closed Requests, AI Assistant
tab_analytics, tab_form, tab_open, tab_closed, tab_ai = st.tabs([
    "Analytics", "Request Form", "Open Requests", "Closed Requests", "AI Assistant"
])

# -------------------------------------------------------------------------------
# Tab 1: Analytics
# -------------------------------------------------------------------------------
with tab_analytics:
    st.header("Analytics Overview")
    df_data = st.session_state["requests_data"]
    open_count = len(df_data[df_data["Status"] != "CLOSED"])
    closed_count = len(df_data[df_data["Status"] == "CLOSED"])
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Open Requests", open_count)
    with col2:
        st.metric("Closed Requests", closed_count)
    st.write("More analytics to come...")

# -------------------------------------------------------------------------------
# Tab 2: Request Form (Manual Entry)
# -------------------------------------------------------------------------------
with tab_form:
    st.subheader("Create a New Request")
    with st.form("request_form"):
        title = st.text_input("Title")
        acct_seg = st.text_input("ACCT & SEG#")
        request_choice = st.selectbox("Request", REQUEST_CHOICES)
        type_choices = st.multiselect("Type", TYPE_CHOICES)
        request_details = st.text_area("Request Details", height=100)
        priority = st.radio("Priority", ["Low", "Normal", "High"])
        status = st.selectbox("Status", STATUS_CHOICES)
        virtual_req = st.text_input("Virtual Req#")
        sourcing_wearable = st.text_input("Sourcing/Wearable#")
        quote_num = st.text_input("Quote#")
        order_num = st.text_input("Order#")
        sample_num = st.text_input("Sample#")
        request_date = st.date_input("Request Date", value=datetime.now())
        assigned_to = st.text_input("Assigned To (Name or Email)")
        attachments = st.file_uploader("Attachments", accept_multiple_files=True)
        submitted = st.form_submit_button("Submit")
        if submitted:
            new_record = {
                "Title": title,
                "ACCT & SEG#": acct_seg,
                "Request": request_choice,
                "Type": ", ".join(type_choices),
                "Request Details": request_details,
                "Priority": priority,
                "Status": status,
                "Virtual Req#": virtual_req,
                "Sourcing/Wearable#": sourcing_wearable,
                "Quote#": quote_num,
                "Order#": order_num,
                "Sample#": sample_num,
                "Request Date": request_date.strftime("%Y-%m-%d"),
                "Assigned To": assigned_to,
            }
            process_and_save_request(new_record)
            st.success("New request added and saved successfully!")
            force_page_refresh()

# -------------------------------------------------------------------------------
# Tab 3: Open Requests
# -------------------------------------------------------------------------------
with tab_open:
    st.subheader("Open Requests")

    # Pull out the open subset and keep only the columns you care about
    mask_open = st.session_state["requests_data"]["Status"] != "CLOSED"
    open_df = st.session_state["requests_data"].loc[mask_open, COLUMNS]

    column_config_open = {
        "Status": st.column_config.SelectboxColumn(
            label="Status",
            options=STATUS_CHOICES
        )
    }

    # Show an editable, deletable table
    edited_open = st.data_editor(
        open_df,
        column_config=column_config_open,
        num_rows="dynamic",
        use_container_width=True,
        key="editor_open"
    )

    if st.button("Save Changes", key="save_open"):
        # Everything *not* in edited_open (by index) should be treated as deleted
        remaining_open = edited_open

        # Grab the closed requests that we haven't touched
        closed_df = st.session_state["requests_data"].loc[
            st.session_state["requests_data"]["Status"] == "CLOSED",
            COLUMNS
        ]

        # Rebuild the full requests_data from remaining open + untouched closed
        st.session_state["requests_data"] = pd.concat(
            [remaining_open, closed_df],
            ignore_index=True,
        )

        # Persist back to Mongo (hard deletes will occur here)
        save_data(st.session_state["requests_data"])

        st.success("Open requests updated (and deleted) successfully!")
        force_page_refresh()   # to clear out the deleted rows from view
# -------------------------------------------------------------------------------
# Tab 4: Closed Requests
# -------------------------------------------------------------------------------
with tab_closed:
    st.subheader("Closed Requests")

    mask_closed = st.session_state["requests_data"]["Status"] == "CLOSED"
    closed_df = st.session_state["requests_data"].loc[mask_closed, COLUMNS]

    column_config_closed = {
        "Status": st.column_config.SelectboxColumn(
            label="Status",
            options=STATUS_CHOICES
        )
    }

    edited_closed = st.data_editor(
        closed_df,
        column_config=column_config_closed,
        num_rows="dynamic",
        use_container_width=True,
        key="editor_closed"
    )

    if st.button("Save Changes", key="save_closed"):
        remaining_closed = edited_closed

        # Grab all open requests untouched
        open_df = st.session_state["requests_data"].loc[
            st.session_state["requests_data"]["Status"] != "CLOSED",
            COLUMNS
        ]

        # Rebuild the full DataFrame
        st.session_state["requests_data"] = pd.concat(
            [open_df, remaining_closed],
            ignore_index=True,
        )

        save_data(st.session_state["requests_data"])
        st.success("Closed requests updated (and deleted) successfully!")
        force_page_refresh()
#--------------------------------------------------------------------------------
# Tab 5: AI Assistant
# -------------------------------------------------------------------------------
with tab_ai:
    st.subheader("AI Assistant to Autofill Request Form")
    st.write(
        "Paste your email text or request details below. The AI will convert it into exactly "
        "one request object. Once generated, the form will persist so you can adjust any fields and then save it."
    )

    # Prompt input
    ai_prompt = st.text_area(
        "Enter the request details (e.g., an email snippet):",
        height=150
    )

    # Generate the AI form
    if st.button("Generate Single Request from AI"):
        if ai_prompt:
            parsed_data = generate_single_request(ai_prompt)
            if parsed_data:
                st.session_state["ai_generated_form"] = parsed_data
            else:
                st.error("No data returned or AI returned an empty output.")
        else:
            st.error("Please enter some details for the AI assistant to process.")

    # If we have AI data, render editable form
    if st.session_state.get("ai_generated_form"):
        form = st.session_state["ai_generated_form"]

        st.subheader("AI‑Suggested Request Form")
        st.info("Adjust any fields as needed, then click 'Save Request'.")

        def val(key):
            return form.get(key, "")

        title_ai = st.text_input("Title", value=val("Title"))
        acct_seg_ai = st.text_input("ACCT & SEG#", value=val("ACCT & SEG#"))

        # New single‑select "Request"
        default_req = val("Request")
        idx_req = REQUEST_CHOICES.index(default_req) if default_req in REQUEST_CHOICES else 0
        request_ai = st.selectbox("Request", REQUEST_CHOICES, index=idx_req)

        # New multi‑select "Type"
        raw_types = val("Type") or ""  
        default_type = val("Type")
        candidates = [t.strip() for t in raw_types.split(",")]
        type_defaults = [t for t in candidates if t in TYPE_CHOICES]
        type_ai = st.multiselect("Type", TYPE_CHOICES, default=type_defaults)

        request_details_ai = st.text_area(
            "Request Details",
            value=val("Request Details"),
            height=100
        )

        # Priority
        chosen_priority = val("Priority") if val("Priority") in ["Low","Normal","High"] else "Normal"
        priority_ai = st.radio(
            "Priority",
            ["Low","Normal","High"],
            index=["Low","Normal","High"].index(chosen_priority)
        )

        # Status
        chosen_status = val("Status") if val("Status") in STATUS_CHOICES else "NEW REQUEST"
        status_ai = st.selectbox(
            "Status",
            STATUS_CHOICES,
            index=STATUS_CHOICES.index(chosen_status)
        )

        virtual_req_ai       = st.text_input("Virtual Req#",        value=val("Virtual Req#"))
        sourcing_wearable_ai = st.text_input("Sourcing/Wearable#",  value=val("Sourcing/Wearable#"))
        quote_num_ai         = st.text_input("Quote#",              value=val("Quote#"))
        order_num_ai         = st.text_input("Order#",              value=val("Order#"))
        sample_num_ai        = st.text_input("Sample#",             value=val("Sample#"))

        # Parse date
        def parse_date_str(d):
            try:
                return datetime.strptime(d, "%Y-%m-%d").date()
            except:
                return datetime.now().date()
        req_date_ai = st.date_input(
            "Request Date",
            value=parse_date_str(val("Request Date"))
        )

        assigned_to_ai = st.text_input(
            "Assigned To (Name or Email)",
            value=val("Assigned To")
        )

        # Save button
        if st.button("Save Request (AI)"):
            new_record = {
                "Title": title_ai,
                "ACCT & SEG#": acct_seg_ai,
                "Request": request_ai,
                "Type": ", ".join(type_ai),
                "Request Details": request_details_ai,
                "Priority": priority_ai,
                "Status": status_ai,
                "Virtual Req#": virtual_req_ai,
                "Sourcing/Wearable#": sourcing_wearable_ai,
                "Quote#": quote_num_ai,
                "Order#": order_num_ai,
                "Sample#": sample_num_ai,
                "Request Date": req_date_ai.strftime("%Y-%m-%d"),
                "Assigned To": assigned_to_ai,
            }
            process_and_save_request(new_record)
            st.success("AI‑generated request saved successfully!")
            # force_page_refresh()  # uncomment to immediately refresh tabs