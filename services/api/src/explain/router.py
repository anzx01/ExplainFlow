from fastapi import APIRouter, HTTPException

from .models import GenerateGraphRequest, GenerateGraphResponse
from .service import generate_explain_graph

router = APIRouter(prefix="/explain", tags=["explain"])


@router.post("/graph", response_model=GenerateGraphResponse)
async def create_explain_graph(req: GenerateGraphRequest) -> GenerateGraphResponse:
    try:
        graph = await generate_explain_graph(req)
        return GenerateGraphResponse(graph=graph)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
