import streamlit as st
import pandas as pd
import os
import time
from datetime import datetime
from pymongo import MongoClient

# -------------------------------------------------------------------------------
# 1) MongoDB Setup
# -------------------------------------------------------------------------------

# Use your MongoDB Atlas connection string
# Make sure the password has no extra angle brackets or spaces around it.
MONGODB_URI = "mongodb+srv://cmillerjr:GyfC0t2s2Y6M64jd@mocklists.x5nczjz.mongodb.net/?retryWrites=true&w=majority&appName=MockLists"
client = MongoClient(MONGODB_URI)

# Choose the database and collection
db = client["MockLists"]         # Database name
collection = db["requests"]      # Collection name (will be created if not existing)

# -------------------------------------------------------------------------------
# 2) Config & Data Schemas
# -------------------------------------------------------------------------------

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
REQUEST_TYPE_CHOICES = ["New", "Update", "Repair", "Others"]

COLUMNS = [
    "Title", "ACCT & SEG#", "POP", "Request Details", "Request Type", "Priority",
    "Status", "Virtual Req#", "Sourcing/Wearable#", "Quote#", "Order#",
    "Sample#", "Request Date", "Assigned To",
]


# -------------------------------------------------------------------------------
# 3) Data Handling Functions
# -------------------------------------------------------------------------------
def load_data() -> pd.DataFrame:
    """
    Load all documents from the 'requests' collection into a DataFrame.
    """
    docs = list(collection.find())
    if not docs:
        return pd.DataFrame(columns=COLUMNS)

    # Convert to DataFrame
    df = pd.DataFrame(docs)
    # The '_id' field is auto-added by MongoDB. Rename or drop it if not needed.
    # We'll drop it here to keep the same columns as your CSV version.
    if "_id" in df.columns:
        df.drop(columns=["_id"], inplace=True)
    return df

def save_data(df: pd.DataFrame):
    """
    Clear the existing collection and re-insert the entire DataFrame.
    For small apps this is fine, but not ideal if multiple users are editing at once.
    """
    # Remove existing documents
    collection.delete_many({})
    # Insert new documents
    data_dicts = df.to_dict(orient="records")
    if data_dicts:
        collection.insert_many(data_dicts)

def force_page_refresh():
    """
    Forces a rerun by setting unique query params using st.experimental_set_query_params.
    This is necessary since your version (1.44.1) doesn't have st.set_query_params.
    """
    st.experimental_set_query_params(_=str(time.time()))
    st.stop()


# -------------------------------------------------------------------------------
# 4) App Initialization & Session State
# -------------------------------------------------------------------------------
if "requests_data" not in st.session_state:
    st.session_state["requests_data"] = load_data()

st.title("Requests Dashboard")

# Create three tabs for navigation
tab1, tab2, tab3 = st.tabs(["Request Form", "Open Requests", "Closed Requests"])


# ----------------------------- TAB 1: Request Form -----------------------------
with tab1:
    st.subheader("Create a New Request")
    with st.form("request_form"):
        title = st.text_input("Title")
        acct_seg = st.text_input("ACCT & SEG#")
        pop_value = st.text_input("POP")
        request_details = st.text_area("Request Details", height=100)

        request_type = st.selectbox("Request Type", REQUEST_TYPE_CHOICES)
        priority = st.radio("Priority", ["Low", "Normal", "High"])
        status = st.selectbox("Status", STATUS_CHOICES)

        virtual_req = st.text_input("Virtual Req#")
        sourcing_wearable = st.text_input("Sourcing/Wearable#")
        quote_num = st.text_input("Quote#")
        order_num = st.text_input("Order#")
        sample_num = st.text_input("Sample#")

        request_date = st.date_input("Request Date", value=datetime.now())
        assigned_to = st.text_input("Assigned To (Name or Email)")

        # Attachments are not stored in DB in this example, but you can adapt as needed
        attachments = st.file_uploader("Attachments", accept_multiple_files=True)

        submitted = st.form_submit_button("Submit")

        if submitted:
            new_record = {
                "Title": title,
                "ACCT & SEG#": acct_seg,
                "POP": pop_value,
                "Request Details": request_details,
                "Request Type": request_type,
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

            new_row_df = pd.DataFrame([new_record])
            # Merge with session state
            st.session_state["requests_data"] = pd.concat(
                [st.session_state["requests_data"], new_row_df],
                ignore_index=True
            )
            # Push to MongoDB
            save_data(st.session_state["requests_data"])
            st.success("New request added and saved successfully!")


# ---------------------------- TAB 2: Open Requests -----------------------------
with tab2:
    st.subheader("Open Requests")

    open_data = st.session_state["requests_data"][
        st.session_state["requests_data"]["Status"] != "CLOSED"
    ]

    column_config_open = {
        "Status": st.column_config.SelectboxColumn(
            label="Status",
            options=STATUS_CHOICES
        )
    }

    edited_open = st.data_editor(
        open_data,
        column_config=column_config_open,
        num_rows="dynamic",
        use_container_width=True,
        key="editor_open"
    )

    if st.button("Save Changes", key="save_open"):
        # Merge changes back into main session DataFrame
        mask = st.session_state["requests_data"]["Status"] != "CLOSED"
        st.session_state["requests_data"].loc[mask] = edited_open

        # Push updated data to MongoDB
        save_data(st.session_state["requests_data"])
        st.success("Open requests updated successfully!")

        # Force a refresh so newly closed items disappear from 'Open Requests'
        force_page_refresh()


# --------------------------- TAB 3: Closed Requests ----------------------------
with tab3:
    st.subheader("Closed Requests")

    closed_data = st.session_state["requests_data"][
        st.session_state["requests_data"]["Status"] == "CLOSED"
    ]

    column_config_closed = {
        "Status": st.column_config.SelectboxColumn(
            label="Status",
            options=STATUS_CHOICES
        )
    }

    edited_closed = st.data_editor(
        closed_data,
        column_config=column_config_closed,
        num_rows="dynamic",
        use_container_width=True,
        key="editor_closed"
    )

    if st.button("Save Changes", key="save_closed"):
        # Merge changes back into main session DataFrame
        mask = st.session_state["requests_data"]["Status"] == "CLOSED"
        st.session_state["requests_data"].loc[mask] = edited_closed

        # Push updated data to MongoDB
        save_data(st.session_state["requests_data"])
        st.success("Closed requests updated successfully!")

        # Force a refresh so newly reopened items disappear from 'Closed Requests'
        force_page_refresh()
