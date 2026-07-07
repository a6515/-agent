"""
============================================================
测试：公文类型识别 & 输出清洗
============================================================
覆盖 rag_chain.py 中的纯函数：detect_doc_type, _clean_output
"""

import pytest
from src.domain.rag_chain import detect_doc_type


class TestDetectDocType:
    """公文类型自动识别。"""

    def test_qingshi_explicit(self):
        """用户明确说"请示"。"""
        assert detect_doc_type("写一份申请购买3台服务器的请示") == "请示"

    def test_qingshi_by_keyword_approval(self):
        """通过"申请""审批"等关键词推断。"""
        assert detect_doc_type("帮我写个购买打印机的申请") == "请示"
        assert detect_doc_type("立项审批需要一份文件") == "请示"

    def test_tongzhi_meeting(self):
        """会议类 → 通知。"""
        assert detect_doc_type("写一份关于安全生产的会议通知") == "通知"

    def test_tongzhi_holiday(self):
        """放假类 → 通知。"""
        assert detect_doc_type("发一个放假通知") == "通知"

    def test_baogao_summary(self):
        """总结/汇报 → 报告。"""
        assert detect_doc_type("写一份年度工作总结报告") == "报告"
        assert detect_doc_type("写一份项目进展汇报") == "报告"

    def test_han(self):
        """函件类。"""
        assert detect_doc_type("写一份商洽合作事宜的函") == "函"

    def test_jueding(self):
        """表彰/处分 → 决定。"""
        assert detect_doc_type("写一份表彰优秀员工的决定") == "决定"

    def test_default_fallback(self):
        """无法识别时返回'公文'。"""
        assert detect_doc_type("写点东西") == "公文"
        assert detect_doc_type("") == "公文"

    def test_mixed_keywords_picks_best_match(self):
        """多个关键词时选得分最高的。"""
        # "通知"和"会议"都匹配通知，"通知"关键词得1分，"会议"再得1分
        result = detect_doc_type("写一份会议通知")
        assert result == "通知"


class TestCleanOutput:
    """输出清理函数。"""

    @pytest.mark.parametrize("input_text,expected_contains", [
        # AI 套话开头
        ("好的，以下是生成的公文：\n\n关于xxx的请示\n正文内容", "关于xxx"),
        ("好的。为您撰写如下：\n\n通知正文", "通知正文"),
        ("根据您的要求，我为您生成了请示：\n\n请示正文", "请示正文"),
        ("以下是生成的请示：\n\n请示正文", "请示正文"),
        # AI 套话结尾
        ("正文内容\n\n希望以上内容能帮到你", "正文内容"),
        ("正文内容\n如有疑问请联系", "正文内容"),
        ("正文内容\n\n综上所述，本文...", "正文内容"),
        # 多余空白
        ("第一段\n\n\n\n\n第二段", "第一段\n\n第二段"),
    ])
    def test_clean_output(self, input_text, expected_contains):
        """验证 AI 套话被正确清理。"""
        from src.domain.rag_chain import GongwenRAGChain
        result = GongwenRAGChain._clean_output(input_text)
        assert expected_contains in result
        # 不应包含明显 AI 套话
        for bad_word in ["好的", "综上所述", "希望以上内容", "根据您的要求"]:
            assert bad_word not in result
