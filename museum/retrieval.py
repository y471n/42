"""Local vector retrieval and deterministic quotation checks."""

import re

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

from museum.models import Source


def retrieve_passages(evidence: list[Source], query: str, embeddings: Embeddings, limit: int) -> list[dict]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=100)
    docs = [Document(page_content=chunk, metadata={"source_id": source["id"]})
            for source in evidence for chunk in splitter.split_text(source["content"])]
    if not docs:
        return []
    store = InMemoryVectorStore.from_documents(docs, embeddings)
    return [{"source_id": doc.metadata["source_id"], "text": doc.page_content}
            for doc in store.similarity_search(query, k=min(limit, len(docs)))]


def validate_citations(citations: list[dict], evidence: list[Source]) -> list[str]:
    sources = {item["id"]: item["content"] for item in evidence}
    issues = []
    for citation in citations:
        source_id = citation["source_id"]
        quote = " ".join(citation["quote"].split())
        text = " ".join(sources.get(source_id, "").split())
        if source_id not in sources or len(quote) < 20 or quote not in text:
            issues.append(f"Unverified quotation for {source_id}.")
    return issues


def validate_letter(letter: dict, evidence: list[Source]) -> list[str]:
    issues = validate_citations(letter["citations"], evidence)
    verified = {" ".join(citation["quote"].split()) for citation in letter["citations"]
                if not validate_citations([citation], evidence)}
    quotes = re.findall(r'["“]([^"”\n]{20,})["”]|(?<!\w)[\'‘]([^\'’\n]{20,})[\'’](?!\w)', letter["text"])
    for parts in quotes:
        quote = next(part for part in parts if part)
        if " ".join(quote.split()) not in verified:
            issues.append("Inline quotation has no verified source citation.")
    return issues
