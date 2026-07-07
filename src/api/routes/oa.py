"""
致远 OA 推送端点：/oa/forward。Controller 层。
"""

from fastapi import APIRouter, Depends

from src.api.deps import get_oa_service
from src.api.schemas import OAForwardRequest, OAForwardResponse
from src.services.oa_service import OAService

router = APIRouter(tags=["oa"])


@router.post("/oa/forward", response_model=OAForwardResponse)
async def forward_to_oa(
    req: OAForwardRequest,
    svc: OAService = Depends(get_oa_service),
):
    """推送已生成的公文到致远 OA 系统，创建为公文单据。"""
    return svc.forward(req)
