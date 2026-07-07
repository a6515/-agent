"""
============================================================
Pydantic 数据模型
============================================================
定义所有 API 接口的请求体（Request）和响应体（Response）结构。
用于 FastAPI 的自动参数校验、类型转换和 Swagger 文档生成。
"""

from enum import Enum
from typing import Optional, List
from datetime import datetime

from pydantic import BaseModel, Field


# ============================================================
# 枚举类型
# ============================================================

class DocType(str, Enum):
    """公文文种枚举（党政机关公文处理工作条例规定的 15 种）。"""
    QING_SHI = "请示"     # 适用于向上级机关请求指示、批准
    BAO_GAO = "报告"       # 适用于向上级机关汇报工作、反映情况
    TONG_ZHI = "通知"      # 适用于发布、传达要求下级机关执行的事项
    HAN = "函"             # 适用于不相隶属机关之间商洽工作、询问和答复
    JI_YAO = "纪要"        # 适用于记载会议主要情况和议定事项
    JUE_DING = "决定"      # 适用于对重要事项作出决策和部署
    TONG_BAO = "通报"      # 适用于表彰先进、批评错误、传达重要精神
    PI_FU = "批复"         # 适用于答复下级机关请示事项
    GONG_GAO = "公告"      # 适用于向国内外宣布重要事项
    YI_JIAN = "意见"       # 适用于对重要问题提出见解和处理办法


class DocCategory(str, Enum):
    """公文段落分类标记（与 doc_loader 的分类一致）。"""
    HEADER = "header"           # 标题/版头
    RECIPIENT = "recipient"     # 主送机关
    BODY = "body"               # 正文
    ATTACHMENT = "attachment"   # 附件
    SIGNATURE = "signature"     # 落款
    TABLE = "table"             # 表格
    OTHER = "other"             # 其他


# ============================================================
# 请求模型
# ============================================================

class GenerateRequest(BaseModel):
    """
    公文生成请求。

    示例：
        {
            "prompt": "写一份申请购买 3 台服务器的请示",
            "doc_type": "请示",
            "retrieve_k": 4,
            "temperature": 0.3
        }
    """
    prompt: str = Field(
        ...,
        description="用户的简短提示，例如：'写一份关于召开安全生产会议的通知'",
        min_length=2,
        max_length=2000,
        examples=["写一份申请购买 3 台服务器的请示"],
    )
    doc_type: Optional[DocType] = Field(
        default=None,
        description="指定公文文种。留空则自动识别。可选：请示/报告/通知/函/纪要/决定/通报/批复/公告/意见",
    )
    retrieve_k: int = Field(
        default=4,
        ge=1,
        le=10,
        description="检索范文数量（1-10 条）。越多参考越丰富但 prompt 越长。",
    )
    temperature: float = Field(
        default=0.3,
        ge=0.0,
        le=2.0,
        description="LLM 生成温度。0.0=完全确定，2.0=最大随机。公文建议 0.1-0.5。",
    )
    messages: Optional[List[dict]] = Field(
        default=None,
        description="【深度模式】对话历史，用于保持多轮对话记忆。每条消息含 role/content 字段。",
    )
    current_draft: Optional[str] = Field(
        default=None,
        description="【深度模式】当前已生成的草稿正文（左栏内容）。有值时 Agent 会优先定向修改而非重写全文。",
    )


class OAForwardRequest(BaseModel):
    """
    致远 OA 公文推送请求。

    这个请求体会被转换为致远 OA「公文新建接口」所需的 Payload。
    你后续需要根据致远 OA 的实际接口文档调整以下字段。

    示例：
        {
            "title": "关于申请购置办公服务器的请示",
            "content": "为保障公司业务系统稳定运行……",
            "doc_type": "请示",
            "secret_level": "普通",
            "urgency": "普通",
            "creator_id": "zhangsan",
            "department": "信息技术部",
            "form_data": {"经费预算": "480000", "设备数量": "3"}
        }
    """
    title: str = Field(
        ...,
        description="公文标题",
        min_length=2,
        max_length=200,
    )
    content: str = Field(
        ...,
        description="公文正文（纯文本或 HTML）",
        min_length=10,
        max_length=50000,
    )
    doc_type: DocType = Field(
        ...,
        description="公文文种",
    )
    secret_level: Optional[str] = Field(
        default="普通",
        description="密级：普通/秘密/机密/绝密",
    )
    urgency: Optional[str] = Field(
        default="普通",
        description="紧急程度：普通/加急/特急",
    )
    creator_id: Optional[str] = Field(
        default=None,
        description="拟稿人工号或用户名",
    )
    department: Optional[str] = Field(
        default=None,
        description="拟稿部门",
    )
    form_data: Optional[dict] = Field(
        default=None,
        description="表单附加字段（如经费预算、设备数量等），对应 OA 表单模板中的自定义字段",
    )
    attachments: Optional[List[str]] = Field(
        default=None,
        description="附件文件路径列表（需先上传到 OA 文件服务）",
    )


# ============================================================
# 响应模型
# ============================================================

class GenerateResponse(BaseModel):
    """
    公文生成响应。
    """
    success: bool = Field(..., description="是否生成成功")
    title: str = Field(..., description="生成的公文标题（自动提取）")
    content: str = Field(..., description="生成的公文正文")
    doc_type: str = Field(..., description="公文文种")
    char_count: int = Field(..., description="正文字符数")
    retrieved_sources: List[str] = Field(
        default_factory=list,
        description="检索到的范文来源列表",
    )
    docx_path: Optional[str] = Field(
        default=None,
        description="生成的 .docx 文件路径",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="生成时间戳",
    )
    error: Optional[str] = Field(
        default=None,
        description="错误信息（success=false 时填充）",
    )


class OAForwardResponse(BaseModel):
    """
    致远 OA 推送响应。
    """
    success: bool = Field(..., description="是否推送成功")
    oa_doc_id: Optional[str] = Field(
        default=None,
        description="致远 OA 返回的公文 ID",
    )
    oa_status: Optional[str] = Field(
        default=None,
        description="OA 中的公文状态（如 'draft'/'pending'/'approved'）",
    )
    message: str = Field(
        default="",
        description="OA 返回的提示信息",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="推送时间戳",
    )


class HealthResponse(BaseModel):
    """健康检查响应。"""
    status: str = Field(default="ok", description="服务状态")
    version: str = Field(default="1.0.0", description="API 版本")
    llm_model: str = Field(default="", description="当前使用的 LLM 模型")
    vector_db_ready: bool = Field(default=False, description="向量库是否就绪")
    oa_configured: bool = Field(default=False, description="致远 OA 是否已配置")
    llm_ok: Optional[bool] = Field(
        default=None,
        description="LLM API 连通性（仅 ?check_llm=true 时返回；null=未检测）",
    )


class StreamEvent(BaseModel):
    """
    SSE 流式事件模型（用于 /generate/stream 接口）。
    每个事件包含一个文本片段和可选的元数据。
    """
    token: str = Field(..., description="生成的文本片段（token 级别）")
    done: bool = Field(default=False, description="是否已生成完毕")
    doc_type: Optional[str] = Field(default=None, description="公文类型（仅第一个事件包含）")


class AgentAnswerRequest(BaseModel):
    """
    Agent ask_user 回答请求。

    当 Agent 在深度模式中通过 ask_user 工具向用户提问时，
    前端收集用户回答后通过此接口提交，Agent 将继续执行。
    """
    session_id: str = Field(
        ...,
        description="Agent 会话 ID（从 ask_user SSE 事件中获取）",
        min_length=1,
    )
    answer: str = Field(
        ...,
        description="用户对 Agent 提问的回答",
        min_length=1,
        max_length=5000,
    )
