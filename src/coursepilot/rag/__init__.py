"""
CoursePilot RAG(retrieval augmented generation) modules.

流程：上传文件
  -> parser 解析文本
  -> chunker 切分文本
  -> embeddings 生成向量
  -> vector_store 写入 Chroma
  -> retriever 检索结果并返回引用信息

"""
