"""
API 层（Controller）—— FastAPI 服务
=====================================
分层结构：
  app.py         启动中心（create_app + lifespan，≈ @SpringBootApplication）
  deps.py        依赖装配（Depends providers，≈ @Configuration）
  middleware.py  横切关注点（CORS / 请求追踪 / 限流）
  routes/        HTTP 路由（≈ @RestController）
  schemas.py     请求/响应 DTO（Pydantic v2）

应用实例请从 src.api.app 导入（避免包初始化时产生副作用）：
    from src.api.app import app
"""
