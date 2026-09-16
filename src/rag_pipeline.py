import hashlib
import json
import os

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_ollama import OllamaEmbeddings

# Anchor the store to the project root so it does not move with the working
# directory (running from src/ vs the repo root used to create two separate DBs).
PERSIST_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chroma_db")

# Records the doc_id of the most recent upload, so a run that does not re-upload
# still retrieves from that document rather than from every document ever loaded.
_LAST_DOC_FILE = os.path.join(PERSIST_DIR, "last_doc.json")


class RAGPipeline:
    def __init__(self):
        self.embeddings = OllamaEmbeddings(model="nomic-embed-text")
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        # Reconnect to whatever was persisted by an earlier run, so a fresh
        # instance can still retrieve without re-uploading the document.
        self.vector_store = Chroma(
            persist_directory=PERSIST_DIR, embedding_function=self.embeddings
        )

    def _loader_for(self, file_path: str):
        # The uploader accepts .pdf, which TextLoader decodes as mojibake rather
        # than failing loudly, so dispatch on extension instead.
        if os.path.splitext(file_path)[1].lower() == ".pdf":
            return PyPDFLoader(file_path)
        return TextLoader(file_path)

    def _remember_last_doc(self, doc_id: str):
        os.makedirs(PERSIST_DIR, exist_ok=True)
        with open(_LAST_DOC_FILE, "w") as f:
            json.dump({"doc_id": doc_id}, f)

    def _last_doc_id(self):
        try:
            with open(_LAST_DOC_FILE) as f:
                return json.load(f).get("doc_id")
        except (OSError, ValueError):
            return None

    def load_document(self, file_path: str):
        loader = self._loader_for(file_path)
        documents = loader.load()
        chunks = self.text_splitter.split_documents(documents)

        # Identify the document by a hash of its bytes: re-uploading the same
        # file reuses the same doc_id (so its chunks are overwritten, not
        # duplicated), while a different file gets its own namespace.
        with open(file_path, "rb") as f:
            doc_id = hashlib.sha256(f.read()).hexdigest()

        for chunk in chunks:
            chunk.metadata["doc_id"] = doc_id

        # Namespace the chunk id by doc_id too, so identical boilerplate in two
        # different documents does not collide on a single row.
        ids = [
            hashlib.sha256((doc_id + chunk.page_content).encode("utf-8")).hexdigest()
            for chunk in chunks
        ]
        self.vector_store.add_documents(documents=chunks, ids=ids)
        self._remember_last_doc(doc_id)

        return doc_id, f"Loaded {len(chunks)} chunks from {os.path.basename(file_path)}"

    def retrieve(self, query: str, doc_id: str = None):
        # The store is cumulative across every document ever uploaded, so an
        # unscoped search blends them. Always scope to one document: the one
        # asked for, else the most recent upload.
        doc_id = doc_id or self._last_doc_id()
        if doc_id is None:
            return "No document is loaded yet"

        results = self.vector_store.similarity_search(query, k=3, filter={"doc_id": doc_id})
        if not results:
            return "No document is loaded yet"
        return "\n".join([doc.page_content for doc in results])
