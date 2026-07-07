module.exports = {
  transpileDependencies: [
    /[/\\]node_modules[/\\]ant-design-vue[/\\]/,
    /[/\\]node_modules[/\\]vue-[-\w]+[/\\]/,
  ],
  devServer: {
    port: 8081,
    open: false,
    // 关闭 gzip 压缩：webpack-dev-server 默认开启的压缩中间件会缓冲响应体来压缩，
    // 导致 SSE 流被攒住不实时下发（深度模式事件稀疏，表现为"过程 UI 不动、最后才出稿"）。
    // 生产环境由 nginx 处理（nginx.conf 已配 proxy_buffering off），不受此影响。
    compress: false,
    // 将后端 API 路径代理到 AI 后端（8000），模拟生产环境 nginx 同源部署。
    // 配合 .env.development 的 VUE_APP_API_BASE 置空，前端一律使用相对路径，
    // 避免"某个 API 直接用相对地址在本地 404"这类前后端分端口才会踩的坑。
    // SSE 端点（/generate/stream 等）由 http-proxy 透传，保持流式（后端已设 X-Accel-Buffering: no）。
    proxy: {
      '/generate': { target: 'http://localhost:8000', changeOrigin: true },
      '/download': { target: 'http://localhost:8000', changeOrigin: true },
      '/health': { target: 'http://localhost:8000', changeOrigin: true },
      '/stats': { target: 'http://localhost:8000', changeOrigin: true },
      '/oa': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  css: {
    loaderOptions: {
      scss: {
        sassOptions: {
          quietDeps: true,
        },
      },
    },
  },
  productionSourceMap: false,
};
