# FoxMate 网站部署教程

## 准备工作

请确保您已准备好：
- GitHub账号（如没有请先注册：https://github.com）
- FoxMate压缩包（最终版）
- 自定义域名（如：foxmate.ai）

预计完成时间：15-20分钟

---

## 第一步：创建GitHub仓库

### 1.1 登录GitHub
访问 https://github.com 并登录您的账号

### 1.2 创建新仓库
1. 点击右上角 **+** 号
2. 选择 **New repository**

### 1.3 填写仓库信息
- **Repository name**: `foxmate`
- **Description**: `FoxMate - Your Cute Focus Companion`
- **Public**（公开，免费部署需要）
- **不要勾选** "Add a README file"
- 点击 **Create repository**

---

## 第二步：上传网站源码

### 2.1 进入仓库页面
创建完成后，您会看到一个空仓库页面

### 2.2 上传文件
1. 点击 **uploading an existing file** 链接
2. 将以下文件夹内的**所有文件**拖拽到上传区域：
   - `foxmate-website/` 目录下的所有内容
   - 包括：`app/`、`components/`、`lib/`、`public/` 文件夹
   - 以及：`package.json`、`next.config.js` 等配置文件

### 2.3 提交代码
- 在 **Commit changes** 下方填写提交信息：`Initial commit`
- 点击 **Commit changes** 按钮

---

## 第三步：上传FoxMate压缩包到Releases

### 3.1 进入Releases页面
1. 在仓库页面右侧，点击 **Releases**
2. 点击 **Create a new release**

### 3.2 填写版本信息
- **Tag version**: `v1.0.0`
- **Release title**: `FoxMate v1.0.0`
- **Describe this release**: `First official release`

### 3.3 上传压缩包
1. 在 **Attach binaries** 区域
2. 将FoxMate压缩包拖拽上传
3. 点击 **Publish release**

### 3.4 获取下载链接
发布后，复制下载链接，格式如下：
```
https://github.com/你的用户名/foxmate/releases/download/v1.0.0/FoxMate-v1.0.0.zip
```

### 3.5 更新下载链接
1. 回到仓库首页
2. 找到 `lib/config.ts` 文件
3. 点击文件 → 点击编辑按钮（铅笔图标）
4. 将 `windows:` 后面的链接替换为您的下载链接
5. 点击 **Commit changes**

---

## 第四步：Vercel部署

### 4.1 注册Vercel
1. 访问 https://vercel.com
2. 点击 **Sign Up**
3. 选择 **Continue with GitHub**
4. 授权Vercel访问您的GitHub

### 4.2 导入项目
1. 登录后点击 **Add New...** → **Project**
2. 在列表中找到 `foxmate` 仓库
3. 点击 **Import**

### 4.3 配置项目
- **Framework Preset**: Next.js（自动识别）
- **Root Directory**: `./`（默认）
- 点击 **Deploy**

### 4.4 等待部署
- 部署过程约1-2分钟
- 看到 **Congratulations!** 表示部署成功

### 4.5 获取临时域名
Vercel会自动分配一个域名，格式如：
```
foxmate-xxx.vercel.app
```

---

## 第五步：绑定自定义域名

### 5.1 进入域名设置
1. 在Vercel项目页面，点击 **Settings**
2. 左侧菜单点击 **Domains**

### 5.2 添加域名
1. 输入您的域名（如：`foxmate.ai`）
2. 点击 **Add**

### 5.3 配置DNS解析
Vercel会显示需要配置的DNS记录，请到您的域名服务商（如阿里云、腾讯云、Cloudflare）配置：

**方式一：A记录（推荐）**
| 类型 | 名称 | 值 |
|------|------|-----|
| A | @ | 76.76.21.21 |
| CNAME | www | cname.vercel-dns.com |

**方式二：CNAME记录**
| 类型 | 名称 | 值 |
|------|------|-----|
| CNAME | @ | cname.vercel-dns.com |
| CNAME | www | cname.vercel-dns.com |

### 5.4 等待生效
- DNS解析生效需要几分钟到几小时
- Vercel会自动为您的域名配置HTTPS证书
- 显示绿色对勾表示配置成功

---

## 第六步：验证部署

### 6.1 访问网站
在浏览器中访问您的域名，确认：
- 网站正常显示
- 图片加载正常
- 点击下载按钮能弹出下载

### 6.2 测试下载
1. 点击网站上的下载按钮
2. 确认能正常下载FoxMate压缩包

---

## 后续更新版本

### 更新软件版本
1. 进入GitHub仓库 → **Releases**
2. 点击 **Draft a new release**
3. 填写新版本号（如 `v1.1.0`）
4. 上传新的压缩包
5. 发布后更新 `lib/config.ts` 中的下载链接

### 更新网站内容
1. 在GitHub仓库中找到对应文件
2. 点击编辑按钮修改
3. 提交后Vercel会自动重新部署（约1分钟）

---

## 常见问题

### Q: 网站显示404？
A: 检查 `app/page.tsx` 文件是否存在

### Q: 图片无法加载？
A: 确认 `public/` 文件夹已完整上传

### Q: 下载按钮无效？
A: 检查 `lib/config.ts` 中的下载链接是否正确

### Q: 域名无法访问？
A: DNS解析需要等待，最长可能24小时

### Q: 如何查看部署日志？
A: Vercel项目页面 → Deployments → 点击对应部署记录

---

## 技术支持

如有问题，请提供以下信息：
- 错误截图
- 操作步骤
- 域名/GitHub仓库链接
