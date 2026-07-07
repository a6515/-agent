"""
============================================================
文档仓储（Repository 层）
============================================================
封装公文 .docx 的落盘与下载路径解析，把"文件存在哪、怎么命名、
怎么安全地取回"这类外部资源访问从 Service / Controller 中收拢到一处。

对应 Spring 的 @Repository：上层只说"保存这份公文 / 给我这个文件"，
不关心输出目录、时间戳命名、路径穿越防护等细节。
"""

from pathlib import Path
from typing import Optional

from src.infra.docx_writer import save_gongwen_to_docx
from src.infra.logger import get_logger

logger = get_logger(__name__)


class DocumentRepository:
    """公文 .docx 文件仓储。"""

    def __init__(self, output_dir: Path):
        """
        Args:
            output_dir: 生成文件的输出目录（与 docx_writer 的默认目录保持一致，
                        以保证 /download 能取到 save() 落盘的文件）。
        """
        self._output_dir = Path(output_dir)

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    def save(self, content: str, title: Optional[str] = None) -> str:
        """
        把公文正文渲染并保存为 .docx，返回文件路径字符串。

        失败时抛异常，由调用方（service）决定是否降级——
        与重构前的行为一致（生成成功但落盘失败不影响主结果）。
        """
        path = save_gongwen_to_docx(content, title=title)
        return str(path)

    def safe_path(self, filename: str) -> Path:
        """
        解析下载文件的安全路径。

        Raises:
            PermissionError:   检测到路径穿越（越出 output_dir）。
            FileNotFoundError: 文件不存在。
        """
        file_path = self._output_dir / filename
        # 防止路径穿越攻击
        if not file_path.resolve().is_relative_to(self._output_dir.resolve()):
            raise PermissionError(f"禁止的路径：{filename}")
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在：{filename}")
        return file_path
