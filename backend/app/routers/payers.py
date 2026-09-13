"""Real Stedi Payer Network lookup."""
from fastapi import APIRouter, Query

from .. import cache, config
from ..errors import Unconfigured
from ..integrations import stedi

from .. import schemas as S

router = APIRouter(prefix="/payers", tags=["payers"])


@router.get("", responses={200: {"model": S.PayerSearch}, **S.ERRORS})
async def search_payers(q: str = Query(..., min_length=2), limit: int = 10):
    if not config.STEDI_API_KEY:
        raise Unconfigured("Stedi payer search", "Set STEDI_API_KEY in backend/.env")

    # The payer directory changes on the order of weeks, not seconds.
    results = await cache.get_or_set(
        f"payers:{q.lower()}:{limit}", 3600, lambda: stedi.search_payers(q, limit)
    )
    return {"query": q, "count": len(results), "results": results, "source": "stedi-payer-network"}
