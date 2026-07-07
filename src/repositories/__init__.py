"""
Repository 层 —— 外部资源访问（≈ Spring 的 @Repository / DAO）
=============================================================
把"和外部世界打交道"的代码收拢到这里，上层（service）只声明意图，
不关心文件在哪、OA 接口怎么调、向量库怎么读。

  - document_repository.py  公文 .docx 落盘 / 下载路径解析
  - oa_client.py            致远 OA HTTP 客户端
"""
