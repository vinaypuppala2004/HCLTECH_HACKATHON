"""One fixed source shared by every stub; no real retrieval or inference."""

from hashlib import sha256

from evidencedesk.contracts.models import Document, Hit, Metadata, Passage

DEMO_QUESTION = "How do I reset my password?"
PASSAGE_TEXT = "Use the account portal to reset your password."


def mock_hit() -> Hit:
    return Hit(
        document=Document(
            document_id="doc_mock_guide",
            filename="mock-support-guide.txt",
            format="txt",
            metadata=Metadata(
                title="Mock Support Guide",
                source_url=None,
                product="Demo",
                version="v1",
                environment="demo",
                family_id="mock-support-guide",
                published_at=None,
                origin="synthetic",
            ),
            sha256=sha256(PASSAGE_TEXT.encode()).hexdigest(),
            passage_count=1,
        ),
        passage=Passage(
            passage_id="passage_mock_reset",
            document_id="doc_mock_guide",
            section_path=["Account access", "Password reset"],
            page=None,
            text=PASSAGE_TEXT,
        ),
        rank=1,
        bm25_score=None,
        cosine_score=None,
        rrf_score=0.0,
        selection="ranked",
        applicable=True,
    )
