import streamlit as st
import os
from agent import build_agent
from rag_pipeline import RAGPipeline

st.set_page_config(
    page_title="Agentic AI SDLC Bot",
    page_icon="🤖",
    layout="wide"
)

st.title("🤖 Agentic AI SDLC Bot using RAG")
st.markdown("Upload a requirements document and enter your requirement. The bot will generate code, run tests, and push to GitHub automatically.")

uploaded_file = st.file_uploader(
    "Upload a requirements document (optional)",
    type=["txt", "md", "pdf"]
)

requirement = st.text_area(
    "Enter your requirement:",
    placeholder="e.g. Write a Python function that validates an email address"
)

push_enabled = st.checkbox("Push to GitHub after tests pass?", value=True)

repo_override = ""
if push_enabled:
    repo_override = st.text_input(
        "GitHub repo to push to (optional):",
        placeholder="username/repo-name (leave blank to use .env default)"
    )

if st.button("Run Pipeline"):
    if requirement:
        context = ""

        if uploaded_file is not None:
            with st.spinner("Loading and retrieving context from document..."):
                temp_path = os.path.join("temp_upload_" + uploaded_file.name)
                with open(temp_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                rag = RAGPipeline()
                doc_id, load_message = rag.load_document(temp_path)
                # Scope retrieval to the document just uploaded, otherwise the
                # search also returns chunks from every earlier upload.
                context = rag.retrieve(requirement, doc_id=doc_id)

                os.remove(temp_path)

            st.subheader("Retrieved Context")
            st.caption(load_message)
            st.text(context)

        with st.spinner("Running the agentic pipeline... this may take 1-2 minutes"):
            agent = build_agent()
            result = agent.invoke({
                "requirement": requirement,
                "context": context,
                "code": "",
                "tests": "",
                "test_passed": False,
                "retries": 0,
                "result": "",
                "push_enabled": push_enabled,
                "repo_override": repo_override.strip(),
                "rejected": False,
                "test_output": ""
            })

        st.success("Pipeline complete!")

        rejected = result.get("rejected", False)

        if rejected:
            st.subheader("Safety Check")
            st.error(result["result"])
            st.info("The generated code failed the safety check, so testing and push were skipped.")
        else:
            st.subheader("Generated Code")
            st.code(result["code"], language="python")

            st.subheader("Test Result")
            if result["test_passed"]:
                st.success(f"Tests passed after {result['retries']} attempt(s)")
            else:
                st.error(f"Tests failed after {result['retries']} attempt(s)")

            st.subheader("GitHub Result")
            if not push_enabled:
                st.info("Push to GitHub was skipped (checkbox unchecked).")
            elif not result["test_passed"]:
                st.info("Push to GitHub was skipped (tests did not pass).")
            else:
                st.info(result["result"])
    else:
        st.warning("Please enter a requirement first.")