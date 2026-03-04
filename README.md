# 🦊 小狐狸官方网站

这是小狐狸（FoxMate AI）的官方网站，使用 Next.js 14 + TypeScript + Tailwind CSS 构建。

## 🌟 特性

- 📱 响应式设计，支持移动端
- 🎨 可爱温馨的视觉风格
- ⚡ 静态导出，部署简单
- 🔍 SEO优化
- 🎭 流畅的动画效果

## 🚀 快速开始

### 安装依赖

```bash
npm install
```

### 开发模式

```bash
npm run dev
```

访问 [http://localhost:3000](http://localhost:3000) 查看网站。

### 构建生产版本

```bash
npm run build
```

### 导出静态网站

```bash
npm run build
```

静态文件将生成在 `out` 目录中。

## 📁 项目结构

```
foxmate-website/
├── app/                    # Next.js App Router
│   ├── page.tsx           # 首页
│   ├── features/          # 功能页面
│   ├── download/          # 下载页面
│   ├── about/             # 关于页面
│   ├── layout.tsx         # 根布局
│   └── globals.css        # 全局样式
├── components/            # React组件
│   ├── Navbar.tsx        # 导航栏
│   └── Footer.tsx        # 页脚
├── public/               # 静态资源
├── tailwind.config.ts    # Tailwind配置
├── next.config.js        # Next.js配置
└── package.json          # 项目依赖
```

## 🎨 设计系统

### 颜色

- **主色**: #FF6B35 (狐狸橙)
- **辅助色**: #FFA533 (浅橙)
- **背景色**: #FFF5EB (米白)

### 字体

- **标题**: Poppins
- **正文**: Nunito

## 📦 部署

### Vercel（推荐）

1. 将代码推送到 GitHub
2. 在 Vercel 导入项目
3. 自动部署完成

### 其他平台

构建后，将 `out` 目录部署到任何静态网站托管服务：
- Netlify
- GitHub Pages
- 阿里云OSS
- 腾讯云COS

## 🔧 自定义配置

### 修改颜色

编辑 `tailwind.config.ts` 中的颜色配置：

```typescript
colors: {
  primary: {
    500: '#FF6B35', // 主色
    // ...
  }
}
```

### 添加新页面

在 `app` 目录下创建新文件夹和 `page.tsx` 文件：

```
app/
└── new-page/
    └── page.tsx
```

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

**🦊 小狐狸 - 你的专注伙伴**
