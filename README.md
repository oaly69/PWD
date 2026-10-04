# PWD · 个人 AIGC 创作平台

一个可自托管的个人 AIGC 创作工作台：对话写作、文生图、作品管理、提示词沉淀，统一在一个 Web 界面中完成。
**Docker 一键部署，零必填环境变量**，启动后在浏览器的安装向导中完成全部配置。

## 功能

| 模块 | 说明 |
|---|---|
| 🧙 安装向导 | 首次访问自动进入：设置站点名称、管理员账号，可选配置第一个模型服务并测试连接 |
| 🔌 模型服务 | 任意 **OpenAI 兼容接口**（OpenAI / DeepSeek / 硅基流动 / OpenRouter / Ollama / One API / New API …）与 **ComfyUI**；支持测试连接、一键拉取模型列表 |
| 💬 对话创作 | 多会话、流式输出、Markdown 渲染、角色设定（系统提示词）、重新生成、中途停止 |
| 🎨 图像生成 | 文生图；尺寸预设、数量、种子、反向提示词、自定义额外请求参数；后台异步任务，可复用参数 |
| 🧩 ComfyUI | 导入「API 格式」工作流，使用 `{{prompt}}` `{{seed}}` `{{width}}` 等占位符，工作流名称即模型名称 |
| 🖼️ 作品库 | 生成结果自动入库；收藏、搜索、筛选、大图预览、下载、再次生成；支持上传图片/视频/音频素材 |
| 📝 提示词库 | 图像提示词与对话角色模板，可在生成页 / 对话页直接调用 |
| ⚙️ 系统设置 | 站点名称、默认模型、默认系统提示词、修改密码 |

## 部署

### 方式一：docker compose（推荐）

```bash
mkdir pwd && cd pwd
curl -O https://raw.githubusercontent.com/oaly69/PWD/main/docker-compose.yml
docker compose up -d
```

### 方式二：docker run

```bash
docker run -d --name pwd --restart unless-stopped \
  -p 8080:8080 \
  -v $(pwd)/data:/data \
  --add-host host.docker.internal:host-gateway \
  ghcr.io/oaly69/pwd:latest
```

然后浏览器访问 `http://服务器IP:8080`，按安装向导完成设置即可。

### 环境变量（全部可选）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PWD_INSTALL_TOKEN` | 空 | 设置后，安装页必须输入该令牌才能完成安装。**部署到公网时强烈建议设置**，防止他人抢先安装 |
| `PWD_PORT` | `8080` | 容器内监听端口 |
| `PWD_DATA_DIR` | `/data` | 数据目录（数据库、生成文件、会话密钥） |
| `TZ` | `Asia/Shanghai` | 时区 |

其余参数（管理员账号、模型服务、API Key、默认模型等）全部在 Web 界面中设置，保存在 `/data/pwd.db`。

### 数据与备份

所有数据都在挂载的 `data` 目录中：

```
data/
├── pwd.db        # SQLite 数据库（配置、对话、任务、作品索引）
├── media/        # 生成与上传的文件
└── .secret_key   # 会话签名密钥（首次启动自动生成）
```

备份时停止容器后复制整个 `data` 目录即可。

### 更新

```bash
docker compose pull && docker compose up -d
```

### 连接宿主机上的 Ollama / ComfyUI

compose 文件已配置 `host.docker.internal`，在模型服务中填写：

- Ollama：`http://host.docker.internal:11434/v1`
- ComfyUI：`http://host.docker.internal:8188`（ComfyUI 需以 `--listen` 启动）

### 反向代理

放在 Nginx 等反代之后时，需关闭对话接口的缓冲以保证流式输出（服务端已发送 `X-Accel-Buffering: no`，一般无需额外配置）：

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    client_max_body_size 64m;
}
```

## 镜像构建（GitHub Actions）

- `.github/workflows/docker.yml`：推送到 `main` 构建 `latest`；推送 `v*` 标签构建版本号镜像；也可在 Actions 页面手动触发。构建 `linux/amd64` 与 `linux/arm64` 双架构，推送至 `ghcr.io/<owner>/<repo>`。
- `.github/workflows/ci.yml`：PR 与非 main 分支运行后端测试与前端构建。

> 首次推送后 GHCR 包默认为私有。如需免登录拉取，请在 GitHub 仓库主页右侧 **Packages → pwd → Package settings → Change visibility** 设为 Public。

## 本地开发

```bash
# 后端（Python 3.11+）
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8080   # 数据默认写入 ./data
python -m pytest -q                          # 运行测试

# 前端（Node 22+），另开终端
cd frontend
npm install
npm run dev     # http://localhost:5173，/api 自动代理到 8080
```

API 文档：`http://localhost:8080/api/docs`

## 技术栈与目录

- 后端：FastAPI + SQLAlchemy + SQLite + httpx（`backend/`）
- 前端：Vue 3 + Vite + vue-router（`frontend/`）
- 单镜像：前端构建产物由后端直接托管

```
backend/app/
├── main.py              # 应用入口、SPA 托管
├── config.py            # 环境变量（极少）
├── models.py            # 数据模型
├── routers/             # install / auth / providers / chat / images / assets / prompts / system
└── services/            # openai_compat / comfyui / tasks（后台任务）
frontend/src/
├── views/               # 各功能页面
└── components/          # ProviderForm 等
```

## 路线图

- [ ] 图生图 / 局部重绘（参考图上传）
- [ ] 视频生成（可灵、即梦、Runway 等异步任务接口）
- [ ] 语音合成 / 音乐生成
- [ ] 项目 / 分镜管理（参考 [Slate](https://github.com/coracoo/Slate) 的制作线思路）
- [ ] 多用户与配额

## 参考

- [coracoo/Slate](https://github.com/coracoo/Slate)：面向短片制作的本地 AIGC 工作台
