"""
============================================================
致远 OA 推送服务（Service 层）
============================================================
把生成的公文推送到致远 OA，并将各类 OA 异常映射为对前端友好的响应体
（未配置 / 认证失败 / 接口错误分别给出不同引导）。行为与重构前一致。
"""

from fastapi import HTTPException

from src.api.schemas import OAForwardRequest, OAForwardResponse
from src.repositories.oa_client import (
    SeeyonOAClient,
    SeeyonOANotConfiguredError,
    SeeyonOAApiError,
    SeeyonOAAuthError,
)
from src.infra.logger import get_logger

logger = get_logger(__name__)


class OAService:
    """致远 OA 推送编排。"""

    def __init__(self, client: SeeyonOAClient):
        self._client = client

    def forward(self, req: OAForwardRequest) -> OAForwardResponse:
        logger.info(f"OA 推送请求：title='{req.title}'")
        try:
            result = self._client.create_document(
                title=req.title,
                content=req.content,
                doc_type=req.doc_type.value,
                secret_level=req.secret_level or "普通",
                urgency=req.urgency or "普通",
                creator_id=req.creator_id,
                department=req.department,
                form_data=req.form_data or {},
            )
            return OAForwardResponse(
                success=True,
                oa_doc_id=str(result.get("id", result.get("docId", ""))),
                oa_status=result.get("status", result.get("state", "unknown")),
                message=result.get("message", "公文已成功推送至致远 OA"),
            )

        except SeeyonOANotConfiguredError as e:
            logger.warning(f"OA 未配置：{e}")
            return OAForwardResponse(
                success=False,
                message=(
                    "致远 OA 尚未配置。请在 .env 中设置以下变量：\n"
                    "  SEEYON_OA_BASE_URL=http://your-oa-server.com\n"
                    "  SEEYON_OA_API_TOKEN=your-token\n"
                    "  SEEYON_OA_FORM_ID=your-form-template-id\n\n"
                    "参考前端源码：D:\\vue-projects\\apps-edoc-front\n"
                    "参考后端源码：E:\\Seeyon\\A8"
                ),
            )

        except SeeyonOAAuthError as e:
            logger.error(f"OA 认证失败：{e}")
            return OAForwardResponse(
                success=False,
                message=f"致远 OA 认证失败，请检查 API Token 是否正确：{e}",
            )

        except SeeyonOAApiError as e:
            logger.error(f"OA API 错误：{e}")
            return OAForwardResponse(
                success=False,
                message=f"致远 OA 接口调用失败：{e}",
            )

        except Exception as e:
            logger.error(f"OA 推送未知错误：{e}")
            raise HTTPException(status_code=500, detail=str(e))
