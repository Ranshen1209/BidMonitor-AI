================================================================================
                  BidMonitor 服务器端 - 部署与使用指南
                              版本: v1.7
================================================================================

一、简介
--------------------------------------------------------------------------------
BidMonitor 服务器端是一个基于 FastAPI 的 Web 应用，提供招标信息监控的远程访问能力。
用户可以通过浏览器访问 Web 界面，实现与电脑端相同的监控功能。

主要特性：
  • 响应式Web界面，支持手机/平板/电脑访问
  • 实时日志显示和进度追踪
  • RESTful API 接口
  • 后台定时自动监控
  • 与电脑端共享核心爬虫和通知模块


二、目录结构
--------------------------------------------------------------------------------
server/
├── app.py                  # FastAPI 主应用（API路由、业务逻辑）
├── static/
│   └── index.html          # Web前端界面（单页应用）
├── setup.sh                # 一键部署脚本
├── start.sh                # 启动脚本
├── stop.sh                 # 停止脚本
├── deploy.sh               # 部署脚本
├── requirements.txt        # Python依赖
├── bidmonitor.service      # systemd服务配置
├── chromedriver-linux64.zip # Linux版Chrome驱动
└── README.md               # 本文档


三、快速部署
--------------------------------------------------------------------------------
方式一：一键部署（推荐）
  1. 在Windows上运行 pack.bat，自动打包并上传到服务器
  2. 服务器上执行 ./server/setup.sh 完成部署
  3. 访问 http://服务器IP:8080
  4. 输入用户名密码登录（默认: Admin / 123654）

方式二：手动部署
  1. 上传代码到服务器 /opt/bidmonitor/
  2. 创建虚拟环境: python3 -m venv venv
  3. 安装依赖: pip install -r server/requirements.txt
  4. 启动服务: ./server/start.sh


四、访问认证
--------------------------------------------------------------------------------
服务器端已启用 HTTP Basic 认证保护：

  默认账号: Admin
  默认密码: 123654

如需修改，编辑 server/app.py 中的 AUTH_USERNAME 和 AUTH_PASSWORD 变量。



五、API接口
--------------------------------------------------------------------------------
基础路径: http://服务器IP:8080

GET  /                    # Web界面
GET  /api/status          # 获取监控状态
POST /api/start           # 启动监控
POST /api/stop            # 停止监控
POST /api/run-once        # 立即执行一次检索
GET  /api/config          # 获取配置
POST /api/config          # 更新配置
GET  /api/sites           # 获取网站列表
POST /api/sites           # 更新启用的网站
GET  /api/results         # 获取招标结果
GET  /api/logs            # 获取实时日志
GET  /api/contacts        # 获取联系人列表
POST /api/contacts        # 更新联系人列表


六、配置说明
--------------------------------------------------------------------------------
服务器配置保存在: server/server_config.json（首次运行自动创建）

该文件包含：
  • 关键词配置（关注词、排除词、必须包含词）
  • 监控网站列表
  • 通知配置（邮件、短信、微信、语音）
  • 联系人列表
  • AI配置

注意：server_config.json 包含敏感信息（API密钥等），已在.gitignore中忽略。


七、服务管理
--------------------------------------------------------------------------------
# 启动服务
./server/start.sh

# 停止服务
./server/stop.sh

# 查看日志
tail -f /opt/bidmonitor/server/logs/server.log

# 使用systemd管理（可选）
sudo cp server/bidmonitor.service /etc/systemd/system/
sudo systemctl enable bidmonitor
sudo systemctl start bidmonitor
sudo systemctl status bidmonitor


八、与电脑端的区别
--------------------------------------------------------------------------------
功能              电脑端              服务器端
界面              Tkinter GUI         Web浏览器
运行环境          Windows             Linux服务器
访问方式          本地运行            远程访问
后台运行          需保持窗口          支持后台服务
核心代码          src/                src/（共享）
配置存储          user_config.json    server/server_config.json


九、故障排查
--------------------------------------------------------------------------------
Q: 无法访问8080端口？
A: 检查防火墙设置，确保8080端口已开放
   阿里云/腾讯云需在安全组中添加入站规则

Q: 服务启动失败？
A: 检查Python版本（需3.8+），检查依赖是否安装完整
   查看日志: cat /opt/bidmonitor/server/logs/server.log

Q: 爬虫失败率高？
A: 服务器端默认启用Selenium模式，需确保Chrome和chromedriver已安装


================================================================================
                      © 2025 BidMonitor 开源项目
================================================================================
