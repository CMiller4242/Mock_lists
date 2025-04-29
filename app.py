import streamlit as st
import pandas as pd
import time
from datetime import datetime
from pymongo import MongoClient
from openai import OpenAI
import json
import re
import uuid
from datetime import datetime, timedelta
import smtplib
from email.message import EmailMessage
import uuid



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
db           = mongo_client["MockLists"]
collection   = db["requests"]

tokens_coll = mongo_client["MockLists"]["login_tokens"]

# #--------------------------------------------------------------------------------
# # Login & Auth
# #--------------------------------------------------------------------------------
# def send_magic_link(email: str):
#     # 1) start device-code flow
#     app = msal.PublicClientApplication(
#         client_id  = st.secrets["azure"]["client_id"],
#         authority  = f"https://login.microsoftonline.com/{st.secrets['azure']['tenant_id']}"
#     )
#     flow = app.initiate_device_flow(scopes=st.secrets["azure"]["scopes"])
#     if "user_code" not in flow:
#         st.error("❌ Device‐flow failed to start. Check your Azure config.")
#         return

#     # show instructions
#     st.info(flow["message"])

#     # 2) generate & store our “magic” token
#     token    = str(uuid.uuid4())
#     expire_at = datetime.utcnow() + timedelta(minutes=15)
#     tokens_coll.insert_one({
#         "token":     token,
#         "email":     email,
#         "expire_at": expire_at,
#     })

#     # 3) wait for user to finish browser sign-in
#     result = app.acquire_token_by_device_flow(flow)
#     if "access_token" not in result:
#         st.error("❌ Login failed: " + result.get("error_description",""))
#         return

#     access_token = result["access_token"]

#     # ─── Step 4 ▶ build the magic-link back into your app ───
#     link = f"{st.secrets['magic_link']['app_url']}?token={token}"

#     # 5) send via Microsoft Graph
#     mail_payload = {
#         "message": {
#             "subject":     "🔑 Your magic link for Requests Dashboard",
#             "body": {
#                 "contentType": "Text",
#                 "content":     f"Click here to sign in (expires in 15 min):\n\n{link}"
#             },
#             "toRecipients": [{"emailAddress": {"address": email}}]
#         }
#     }
#     r = requests.post(
#         "https://graph.microsoft.com/v1.0/me/sendMail",
#         headers={
#             "Authorization": f"Bearer {access_token}",
#             "Content-Type":  "application/json",
#         },
#         json=mail_payload,
#     )
#     if r.status_code == 202:
#         st.success(f"✅ Magic link sent to {email}!")
#     else:
#         st.error(f"❌ sendMail failed: {r.status_code} {r.text}")


# # ───────────────────────────
# # Handle incoming magic-link token
# # ───────────────────────────
# params = st.query_params
# if "token" in params:
#     tok = params["token"][0]
#     rec = tokens_coll.find_one({"token": tok})
#     if rec and rec["expire_at"] > datetime.utcnow():
#         # log them in
#         st.session_state["user_email"] = rec["email"]
#         tokens_coll.delete_one({"_id": rec["_id"]})

#         # clear token from URL so we don’t loop
#         st.set_query_params()        # <-- replaces experimental_set_query_params
#         st.experimental_rerun()      # re-run now that session_state has user_email
#     else:
#         st.error("Magic link is invalid or expired.")


# # ───────────────────────────
# # guard: if not signed in, show login form and bail
# # ───────────────────────────
# if "user_email" not in st.session_state:
#     st.markdown("## Please sign in with your work email")
#     email_in = st.text_input("Work email", placeholder="you@positivepromotions.com")
#     if st.button("Send magic link"):
#         if email_in.endswith("@positivepromotions.com"):
#             send_magic_link(email_in)
#         else:
#             st.error("Only @positivepromotions.com addresses are allowed.")
#     st.stop()


# # — Now you’re “logged in” — proceed to your tabs —
# # — Later you can gate admin-only controls via —
# is_admin = st.session_state["user_email"] in st.secrets["admins"]["emails"]



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



# -------------------------------------------------------------------------------
# 4) AI Helper Function
# -------------------------------------------------------------------------------
def generate_single_request(prompt: str) -> dict:
    """
    Extract exactly ONE request from the given prompt
    and return it as a dict with all the required fields.
    """
    system_instructions = (
        "You are an entity-extraction assistant. From the user’s free-form text, "
        "return exactly ONE JSON object with these keys: "
        "\"Title\", \"ACCT & SEG#\", \"Request\", \"Type\", \"Request Details\", "
        "\"Priority\", \"Status\", \"Virtual Req#\", \"Sourcing/Wearable#\", "
        "\"Quote#\", \"Order#\", \"Sample#\", \"Request Date\" (YYYY-MM-DD), \"Assigned To\".\n\n"
        "**Required**: \"Request\" and \"Type\". Default to \"New Request\" and infer Type if missing.\n\n"
        "**ACCT & SEG#**: 8 digits plus optional space+2 digits.\n\n"
        "**Quote#**: 8 digits starting with 003,004,005…\n\n"
        "**Order#**: 8 digits starting with 3 or 6 (not quote pattern).\n\n"
        "**Type**: multi-select based on keywords (quote, place order, proof, issue, etc.).\n\n"
        """**Classification rules**:
- If text mentions an existing order#/quote# plus any “problem” or “delay”
  (e.g. broken, shortage, event date), set Request="Issue Log" & Type="Issue Log".
- If text modifies or adds to an existing order (e.g. “Add more bags”,
  “please review order”), set Request="Update".
- Otherwise default Request="New Request".

**Date handling**:
- Recognize dates like “4/30” → assume current year, format as `YYYY-04-30`.
- If it’s an event or deadline, capture that in your summary, not raw text.

**Summary**:
- One crisp sentence describing the core action or issue.
- Do NOT repeat any raw values (order#/quote#, SKUs, dates).

Use sensible defaults for missing fields (`Request="New Request"`,
`Status="NEW REQUEST"`, empty string others). Return ONLY valid JSON.
"""
    )
    try:
        # 1) ask GPT
        resp = openai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=800,
            temperature=0.3,
        )
        raw    = resp.choices[0].message.content.strip()
        parsed = json.loads(raw)
        if isinstance(parsed, list) and parsed:
            parsed = parsed[0]

        # 2) extract any raw order#s into Order#s array
        orders = re.findall(r"\b[36]\d{7}\b", prompt)
        if orders:
            parsed["Order#s"] = orders

        # 3) normalize Request Date
        date_str = parsed.get("Request Date", "")
        m = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$", date_str)
        if m:
            y  = m.group(3) or str(datetime.now().year)
            if len(y) == 2:
                y = "20" + y
            mm = m.group(1).zfill(2)
            dd = m.group(2).zfill(2)
            parsed["Request Date"] = f"{mm}-{dd}-{y}"

        # 4) auto-fill Title if blank
        if not parsed.get("Title", "").strip():
            fac = re.search(
                r"([A-Z][\w\s]+(?:College|Hospital|School|Bank))",
                prompt
            )
            if fac:
                parsed["Title"] = fac.group(1).strip()
            else:
                summ = parsed.get("Request Details", "")
                parsed["Title"] = " ".join(summ.split()[:5]) or "New Request"

        return parsed

    except Exception as e:
        st.error(f"Error generating request: {e}")
        return None
    
def generate_requests(prompt: str) -> list[dict]:
    """
    Given a block of text containing multiple order#s,
    extract each 8-digit order (3xxxxxxx or 6xxxxxxx),
    run the single-request parser on each, and return a list.
    """
    try:
        orders = re.findall(r"\b[36]\d{7}\b", prompt)
        results = []

        for o in orders:
            # build a focused prompt for each order
            sub_prompt = f"Order# {o}\n\nContext:\n{prompt}"
            parsed = generate_single_request(sub_prompt)

            if parsed:
                # ensure the Order# field is correct
                parsed["Order#"] = o
                results.append(parsed)

        return results

    except Exception as e:
        st.error(f"Error generating multiple requests: {e}")
        return []
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
        title          = st.text_input("Title")
        acct_seg       = st.text_input("ACCT & SEG#")
        request_choice = st.selectbox("Request", REQUEST_CHOICES)
        type_choices   = st.multiselect("Type", TYPE_CHOICES)
        request_details= st.text_area("Request Details", height=100)
        priority       = st.radio("Priority", ["Low", "Normal", "High"])
        status         = st.selectbox("Status", STATUS_CHOICES)
        virtual_req    = st.text_input("Virtual Req#")
        sourcing_wear  = st.text_input("Sourcing/Wearable#")
        quote_num      = st.text_input("Quote#")
        order_num      = st.text_input("Order#")
        sample_num     = st.text_input("Sample#")
        request_date   = st.date_input("Request Date", datetime.now())
        assigned_to    = st.text_input("Assigned To (Name or Email)")

        submitted = st.form_submit_button("Submit")
        if submitted:
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
            st.success("New request added and saved successfully!")


# -------------------------------------------------------------------------------
# Tab 3: Open Requests
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

    if st.button("Save Changes", key="save_open"):
        try:
            # everything in edited_open + untouched closed
            closed_df = st.session_state["requests_data"].loc[
                st.session_state["requests_data"]["Status"] == "CLOSED", COLUMNS
            ]
            st.session_state["requests_data"] = pd.concat(
                [edited_open, closed_df], ignore_index=True
            )
            save_data(st.session_state["requests_data"])
            st.success("Open requests updated successfully!")
        except Exception:
            st.error("Something went wrong while saving Open Requests.")



# -------------------------------------------------------------------------------
# Tab 4: Closed Requests
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

    if st.button("Save Changes", key="save_closed"):
        try:
            open_df = st.session_state["requests_data"].loc[
                st.session_state["requests_data"]["Status"] != "CLOSED", COLUMNS
            ]
            st.session_state["requests_data"] = pd.concat(
                [open_df, edited_closed], ignore_index=True
            )
            save_data(st.session_state["requests_data"])
            st.success("Closed requests updated successfully!")
        except Exception:
            st.error("Something went wrong while saving Closed Requests.")

# -------------------------------------------------------------------------------
# Tab 5: AI Assistant
# -------------------------------------------------------------------------------
with tab_ai:
    st.subheader("AI Assistant to Autofill Request Form")
    st.write("Choose Single or Multi mode, paste your text, then click Generate.")

    # 1) Mode selector
    mode = st.radio(
        "Generation mode:",
        ["Single Request", "Multi Request"],
        horizontal=True,
        index=0
    )

    # 2) Prompt input
    ai_prompt = st.text_area(
        "Enter the request details (e.g., an email snippet):",
        height=150,
        key="ai_prompt"
    )

    # 3) Generate button(s)
    if mode == "Single Request":
        if st.button("Generate Single Request from AI", key="gen_ai_single"):
            if not ai_prompt:
                st.error("Please enter some text.")
            else:
                parsed = generate_single_request(ai_prompt)
                if not parsed:
                    st.error("AI returned no data.")
                else:
                    if not parsed.get("Request Details", "").strip():
                        parsed["Request Details"] = ai_prompt
                    st.session_state["ai_generated_form"] = parsed

    else:  # Multi Request
        if st.button("Generate Multi Request from AI", key="gen_ai_multi"):
            if not ai_prompt:
                st.error("Please enter some text.")
            else:
                batch = generate_requests(ai_prompt)
                if not batch:
                    st.error("No valid order numbers found in your text.")
                else:
                    st.session_state["ai_generated_forms"] = batch

    # ── 4) Render Single Form ───────────────────────────────────────────────────
    form = st.session_state.get("ai_generated_form")
    if form:
        def val(k, default=""):
            return form.get(k, default)

        st.subheader("AI-Suggested Request Form")
        st.info("Adjust fields as needed, then click Save or Cancel.")

        # Title & Account
        title_ai    = st.text_input("Title",      value=val("Title"),      key="ai_title")
        acct_seg_ai = st.text_input("ACCT & SEG#", value=val("ACCT & SEG#"), key="ai_acct")

        # Request
        req_default = val("Request")
        req_index   = REQUEST_CHOICES.index(req_default) if req_default in REQUEST_CHOICES else 0
        request_ai  = st.selectbox("Request", REQUEST_CHOICES, index=req_index, key="ai_request")

        # Type
        raw_types     = val("Type")
        candidates    = [t.strip() for t in (raw_types or "").split(",")]
        type_defaults = [t for t in candidates if t in TYPE_CHOICES]
        type_ai       = st.multiselect("Type", TYPE_CHOICES, default=type_defaults, key="ai_type")

        # Details
        details_ai = st.text_area(
            "Request Details",
            value=val("Request Details"),
            height=100,
            key="ai_details"
        )

        # Priority / Status
        prios       = ["Low", "Normal", "High"]
        def_prio    = val("Priority") if val("Priority") in prios else "Normal"
        priority_ai = st.radio("Priority", prios, index=prios.index(def_prio), key="ai_prio")

        def_stat    = val("Status") if val("Status") in STATUS_CHOICES else "NEW REQUEST"
        status_ai   = st.selectbox("Status", STATUS_CHOICES, index=STATUS_CHOICES.index(def_stat), key="ai_status")

        # The rest
        virtual_req_ai       = st.text_input("Virtual Req#",        value=val("Virtual Req#"),       key="ai_vreq")
        sourcing_wearable_ai = st.text_input("Sourcing/Wearable#",  value=val("Sourcing/Wearable#"), key="ai_sourcing")
        quote_num_ai         = st.text_input("Quote#",              value=val("Quote#"),             key="ai_quote")
        order_num_ai         = st.text_input("Order#",              value=val("Order#"),             key="ai_order")
        sample_num_ai        = st.text_input("Sample#",             value=val("Sample#"),            key="ai_sample")

        # Date helper
        def _parse_date(d):
            try:
                return datetime.strptime(d, "%Y-%m-%d").date()
            except:
                return datetime.now().date()

        req_date_ai = st.date_input(
            "Request Date",
            value=_parse_date(val("Request Date")),
            key="ai_date"
        )

        assigned_to_ai = st.text_input(
            "Assigned To (Name or Email)",
            value=val("Assigned To"),
            key="ai_assigned"
        )

        # Save / Cancel
        def _save_ai():
            new_record = {
                "Title":               title_ai,
                "ACCT & SEG#":         acct_seg_ai,
                "Request":             request_ai,
                "Type":                ", ".join(type_ai),
                "Request Details":     details_ai,
                "Priority":            priority_ai,
                "Status":              status_ai,
                "Virtual Req#":        virtual_req_ai,
                "Sourcing/Wearable#":  sourcing_wearable_ai,
                "Quote#":              quote_num_ai,
                "Order#":              order_num_ai,
                "Sample#":             sample_num_ai,
                "Request Date":        req_date_ai.strftime("%Y-%m-%d"),
                "Assigned To":         assigned_to_ai,
            }
            process_and_save_request(new_record)
            st.session_state["ai_generated_form"] = None

        def _cancel_ai():
            st.session_state["ai_generated_form"] = None

        c1, c2 = st.columns(2)
        with c1:
            st.button("Save Request (AI)",   key="ai_save",   on_click=_save_ai)
        with c2:
            st.button("Cancel Request (AI)", key="ai_cancel", on_click=_cancel_ai)

# ── 5) Render Multiple Forms ─────────────────────────────────────────────────
batch = st.session_state.get("ai_generated_forms", [])
if batch:
    for idx, form in enumerate(batch):
        def val(k, default=""):
            return form.get(k, default)

        with st.expander(f"AI Form #{idx+1} — Order {form['Order#']}"):
            # Title & Account
            title_i    = st.text_input("Title",      value=val("Title"),      key=f"ai_title_{idx}")
            acct_i     = st.text_input("ACCT & SEG#", value=val("ACCT & SEG#"), key=f"ai_acct_{idx}")

            # Request
            req_def    = val("Request")
            req_i      = st.selectbox(
                             "Request",
                             REQUEST_CHOICES,
                             index=REQUEST_CHOICES.index(req_def) if req_def in REQUEST_CHOICES else 0,
                             key=f"ai_req_{idx}"
                         )

            # Type
            type_i     = st.multiselect(
                             "Type",
                             TYPE_CHOICES,
                             default=[t.strip() for t in val("Type", "").split(",")],
                             key=f"ai_type_{idx}"
                         )

            # Details
            det_i      = st.text_area(
                             "Request Details",
                             value=val("Request Details"),
                             height=100,
                             key=f"ai_details_{idx}"
                         )

            # Save this one
            if st.button("Save This Request", key=f"ai_save_{idx}"):
                new_rec = {
                    "Title":           title_i,
                    "ACCT & SEG#":     acct_i,
                    "Request":         req_i,
                    "Type":            ", ".join(type_i),
                    "Request Details": det_i,
                    "Order#":          form["Order#"],
                    "Priority":        form.get("Priority","Low"),
                    "Status":          form.get("Status","NEW REQUEST"),
                    "Request Date":    form.get("Request Date", datetime.now().strftime("%Y-%m-%d")),
                    "Assigned To":     form.get("Assigned To",""),
                }
                process_and_save_request(new_rec)
                st.success(f"Saved order {form['Order#']}!")
                st.session_state["ai_generated_forms"].pop(idx)
                st.experimental_rerun()

    # ── NEW: Save All Requests at Once ────────────────────────────────────────
    if st.button("Save All Requests", key="ai_save_all"):
        for idx, form in enumerate(batch):
            # grab each field back out of session_state by key
            title   = st.session_state[f"ai_title_{idx}"]
            acct    = st.session_state[f"ai_acct_{idx}"]
            request = st.session_state[f"ai_req_{idx}"]
            types   = st.session_state[f"ai_type_{idx}"]
            details = st.session_state[f"ai_details_{idx}"]
            # fall back to original form values for unchanged fields
            prio    = form.get("Priority","Low")
            status  = form.get("Status","NEW REQUEST")
            req_date = form.get("Request Date", datetime.now().strftime("%Y-%m-%d"))
            assigned = form.get("Assigned To","")

            new_record = {
                "Title":               title,
                "ACCT & SEG#":         acct,
                "Request":             request,
                "Type":                ", ".join(types),
                "Request Details":     details,
                "Order#":              form["Order#"],
                "Priority":            prio,
                "Status":              status,
                "Request Date":        req_date,
                "Assigned To":         assigned,
            }
            process_and_save_request(new_record)

        st.success("All requests saved!")
        # clear the batch and rerun so the expanders disappear
        st.session_state["ai_generated_forms"] = []
        st.experimental_rerun()