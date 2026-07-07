"""
============================================================
测试：docx 段落分类
============================================================
覆盖 docx_writer.py 中的 _classify_line 函数。
"""

import pytest
from src.infra.docx_writer import _classify_line


class TestClassifyLine:
    """段落语义分类。"""

    def test_title_first_line(self):
        """第一条非空行应识别为标题。"""
        assert _classify_line("关于申请购置办公服务器的请示", True) == "title"

    def test_blank_line(self):
        """空行。"""
        assert _classify_line("", True) == "blank"
        assert _classify_line("   ", False) == "blank"

    def test_doc_number(self):
        """发文字号（中文/英文前缀 + 括号 + 年份 + 编号）。"""
        assert _classify_line("国发〔2025〕1号", False) == "subtitle"
        assert _classify_line("X办发〔2024〕15号", False) == "subtitle"
        assert _classify_line("A〔2025〕1号", False) == "subtitle"

    def test_signature_date(self):
        """落款日期（汉字数字）。"""
        assert _classify_line("2025年6月17日", False) == "signature"

    def test_heading1(self):
        """一级标题：一、二、三、..."""
        assert _classify_line("一、项目背景", False) == "heading1"
        assert _classify_line("三、经费预算", False) == "heading1"

    def test_heading2(self):
        """二级标题：（一）（二）..."""
        assert _classify_line("（一）硬件设备", False) == "heading2"
        assert _classify_line("（二）软件系统", False) == "heading2"

    def test_recipient(self):
        """主送机关：冒号结尾的短行。"""
        assert _classify_line("公司领导：", False) == "recipient"
        assert _classify_line("信息技术部：", False) == "recipient"
        # 长文本不应识别为 recipient
        long_text = "这是一个很长的文本不应该被识别为主送机关：而且内容非常多"
        assert _classify_line(long_text, False) == "body"

    def test_attachment(self):
        """附件标记。"""
        assert _classify_line("附件：1. 采购清单", False) == "attachment"
        assert _classify_line("附件：2. 技术参数", False) == "attachment"

    def test_body_default(self):
        """其他情况默认为正文（不以冒号结尾避免误判为主送机关）。"""
        assert _classify_line("为保障公司业务系统稳定运行，现申请购置以下设备", False) == "body"
        assert _classify_line("经研究决定，同意采购申请", False) == "body"

    def test_body_lead_in_with_colon(self):
        """以冒号结尾的正文引导句不应被误判为主送机关。"""
        assert _classify_line("现将有关事项通知如下：", False) == "body"
        assert _classify_line("具体要求如下：", False) == "body"
        assert _classify_line("会议主要内容如下：", False) == "body"
        assert _classify_line("关于设备选型的具体要求如下：", False) == "body"

    def test_recipient_looks_like_org(self):
        """确实像机关/部门名称的行仍应识别为主送机关。"""
        assert _classify_line("公司领导：", False) == "recipient"
        assert _classify_line("信息技术部：", False) == "recipient"
        assert _classify_line("各市、县人民政府：", False) == "recipient"

    def test_not_title_when_not_first(self):
        """非第一条且有'关于'但不在开头位置的不应识别为标题。"""
        # 注意：以全角冒号结尾且长度 < 30 的行会被识别为 recipient
        # 这里测试不以冒号结尾的正文行
        assert _classify_line("关于设备选型的具体要求如下", False) == "body"
