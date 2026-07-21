底层逻辑：
Dockerfile 构建 image 镜像
    ↓
compose.yaml 用 image 创建 container 容器
    ↓
容器启动服务

docker compose up --build 会自动完成“构建镜像 + 创建容器 + 启动容器”。

# 启动前准备
## 确认Docker正常
先启动Docker Desktop，然后在命令行执行：
```powershell
docker --version
docker compose version
```
期望输出：各自的版本

## 在项目根目录下创建.env 文件

## 确认运行目录存在
```powershell
Test-Path storage
Test-Path chroma_db
Test-Path privatecredentials
```
主要确认用户自定义目录、隐私数据、数据上传下载、数据库等是否存在，

如果某目录不存在则创建
```powershell
New-Item -ItemType Directory storage -Force
```

# 启动
## step1 检查compose配置
```powershell
docker compose config
```
一般报错是因为没有.env文件，正常输出和compose.yaml一致的内容（可能顺序打乱）

## step2 先启动数据库
1. 建议先单独启动 Postgres，因为后端依赖它：
```powershell
(.venv) PS D:\project\agent-service-toolkit> docker compose up -d postgres
[+] up 20/20
 ✔ Image postgres:16                          Pulled                                                                                                                                                235.4s
 ✔ Network agent-service-toolkit_default      Created                                                                                                                                                 0.1s
 ✔ Volume agent-service-toolkit_postgres_data Created                                                                                                                                                 0.0s
 ✔ Container agent-service-toolkit-postgres-1 Started                                                                                                                                                 0.9s

What's next:
    Filter, search, and stream logs from all your Compose services
    in one place with Docker Desktop's Logs view. docker-desktop://dashboard/logs?appId=agent-service-toolkit
```
2. 检查状态
```powershell
docker compose ps
(.venv) PS D:\project\agent-service-toolkit> docker compose ps
NAME                               IMAGE         COMMAND                   SERVICE    CREATED        STATUS                  PORTS
agent-service-toolkit-postgres-1   postgres:16   "docker-entrypoint.s…"   postgres   18 hours ago   Up 18 hours (healthy)   0.0.0.0:5432->5432/tcp, [::]:5432->5432/tcp
```
常见错误是本机端口被占用，更改compose.yaml配置对应的port即可

3. 构建前后端镜像
```powershell
docker compose build
```
注意网络问题，关闭梯子用国内docker镜像和pypi镜像（改Dockerfile）
成功后显示：
 ✔ Image agent-service-toolkit-agent_service Built                                                    8606.5s
 ✔ Image agent-service-toolkit-streamlit_app Built                                                    8606.5s



4. 启动全部服务
普通启动：docker compose up -d
热启动：docker compose watch


启动后输出：
 ✔ Container agent-service-toolkit-agent_service-1 Started                                               6.7s
 ✔ Container agent-service-toolkit-streamlit_app-1 Started                                               6.5s
 ✔ Container agent-service-toolkit-postgres-1      Healthy                                               5.9s


查看状态：
```powershell
docker compose ps
```

5. 查看日志
```powershell
前端：docker compose logs -f streamlit_app
后端：docker compose logs -f agent_service
Postgres：docker compose logs -f postgres
```
【主要】排查coursepilot：docker logs -f agent_coursepilot-agent_service-1
最近 120 行：docker compose logs --tail 120 


6. 访问服务
后端健康检查：Invoke-RestMethod http://localhost:8080/health
后端信息接口：Invoke-RestMethod http://localhost:8080/info
前端页面：浏览器访问 http://localhost:8501

7. Alembic迁移
检查状态：docker compose exec agent_service python -m alembic current
执行迁移：docker compose exec agent_service python -m alembic upgrade head

迁移特定version，如<alembic\versions\2026_06_21_0002-create_phase1_tables.py>：docker compose exec agent_service python -m alembic upgrade 2026_06_21_0002


8.  停止容器服务
docker compose down
停止并删除数据库数据：docker compose down -v
