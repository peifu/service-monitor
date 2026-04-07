# server_monitor.py
# 完整的服务监控系统 - Flask后端 + 前端界面
# 运行方式: python server_monitor.py
# 默认端口: 5000，访问 http://localhost:5000

import os
import socket
import threading
import time
from datetime import datetime, timedelta
from functools import wraps
import json
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production-2024'
CORS(app)

# ==================== 用户数据 ====================
# 默认用户名: admin, 密码: admin123
USERS = {
    'admin': {
        'password': 'admin123',
        'role': 'admin',
        'created_at': datetime.now().isoformat()
    }
}

# ==================== 服务配置 ====================
# 默认监控的服务列表
DEFAULT_SERVICES = [
    {'id': 'svc_1', 'name': 'Nginx Web', 'host': '127.0.0.1', 'port': 80, 'description': 'HTTP 服务器', 'enabled': True},
    {'id': 'svc_2', 'name': '业务服务', 'host': '10.68.11.138', 'port': 8888, 'description': '内部业务服务', 'enabled': True},
    {'id': 'svc_3', 'name': 'API Gateway', 'host': '127.0.0.1', 'port': 8080, 'description': 'REST API 入口', 'enabled': True},
    {'id': 'svc_4', 'name': 'MySQL 数据库', 'host': '127.0.0.1', 'port': 3306, 'description': '关系数据库', 'enabled': True},
    {'id': 'svc_5', 'name': 'Redis 缓存', 'host': '127.0.0.1', 'port': 6379, 'description': 'Key-Value 缓存', 'enabled': True},
]

# 服务配置存储文件
SERVICES_FILE = 'services_config.json'
LOGS_FILE = 'monitor_logs.json'

def load_services():
    """加载服务配置"""
    try:
        if os.path.exists(SERVICES_FILE):
            with open(SERVICES_FILE, 'r', encoding='utf-8') as f:
                services = json.load(f)
                # 确保每个服务都有id
                for svc in services:
                    if 'id' not in svc:
                        svc['id'] = f"svc_{int(time.time())}_{svc.get('port', 0)}"
                return services
    except Exception as e:
        print(f"加载服务配置失败: {e}")
    return DEFAULT_SERVICES.copy()

def save_services(services):
    """保存服务配置"""
    try:
        with open(SERVICES_FILE, 'w', encoding='utf-8') as f:
            json.dump(services, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存服务配置失败: {e}")
        return False

def load_logs():
    """加载日志"""
    try:
        if os.path.exists(LOGS_FILE):
            with open(LOGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"加载日志失败: {e}")
    return []

def save_logs(logs):
    """保存日志"""
    try:
        # 只保留最近1000条日志
        if len(logs) > 1000:
            logs = logs[-1000:]
        with open(LOGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存日志失败: {e}")
        return False

# ==================== 端口检测函数 ====================
def check_tcp_port(host, port, timeout=3):
    """
    真正的TCP端口检测
    通过建立socket连接来判断端口是否开放
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except socket.gaierror:
        return False  # 主机名解析失败
    except Exception as e:
        print(f"检测 {host}:{port} 出错: {e}")
        return False

def check_service_status(service):
    """检测单个服务状态"""
    host = service.get('host', '')
    port = service.get('port', 0)
    
    if not host or not port:
        return {'online': False, 'error': '配置无效: 缺少主机或端口'}
    
    try:
        is_online = check_tcp_port(host, port, timeout=3)
        return {
            'online': is_online,
            'error': None if is_online else f'无法连接到 {host}:{port}'
        }
    except Exception as e:
        return {'online': False, 'error': f'检测异常: {str(e)}'}

def check_all_services(services):
    """批量检测所有服务"""
    results = {}
    for svc in services:
        if svc.get('enabled', True):
            status = check_service_status(svc)
            results[svc['id']] = status
        else:
            results[svc['id']] = {'online': False, 'error': '服务已禁用'}
    return results

# ==================== 日志记录 ====================
def add_log(service_id, service_name, host, port, status, error_msg=None, changed=False):
    """添加检测日志"""
    logs = load_logs()
    log_entry = {
        'id': f"log_{int(time.time() * 1000)}_{service_id}",
        'time': datetime.now().isoformat(),
        'service_id': service_id,
        'service_name': service_name,
        'host': host,
        'port': port,
        'status': status,  # True=在线, False=离线
        'status_text': '在线' if status else '离线',
        'error_msg': error_msg,
        'changed': changed
    }
    logs.append(log_entry)
    save_logs(logs)
    return log_entry

# ==================== 认证装饰器 ====================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': '未登录', 'redirect': '/login'}), 401
        return f(*args, **kwargs)
    return decorated_function

# ==================== HTML 模板 ====================
LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>服务监控系统 - 登录</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-container {
            background: white;
            border-radius: 24px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            padding: 40px;
            width: 100%;
            max-width: 420px;
            margin: 20px;
        }
        .login-header {
            text-align: center;
            margin-bottom: 32px;
        }
        .login-header h1 {
            font-size: 28px;
            color: #1a1a2e;
            margin-bottom: 8px;
        }
        .login-header p {
            color: #666;
            font-size: 14px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 500;
            font-size: 14px;
        }
        input {
            width: 100%;
            padding: 12px 16px;
            border: 1px solid #ddd;
            border-radius: 12px;
            font-size: 14px;
            transition: all 0.3s;
        }
        input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
        }
        .error-msg {
            background: #fee2e2;
            color: #dc2626;
            padding: 12px;
            border-radius: 12px;
            margin-bottom: 20px;
            font-size: 14px;
            text-align: center;
        }
        .demo-info {
            margin-top: 24px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
            font-size: 12px;
            color: #999;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-header">
            <h1>🔐 服务监控系统</h1>
            <p>请输入账号密码登录</p>
        </div>
        {% if error %}
        <div class="error-msg">{{ error }}</div>
        {% endif %}
        <form method="POST">
            <div class="form-group">
                <label>用户名</label>
                <input type="text" name="username" required autofocus>
            </div>
            <div class="form-group">
                <label>密码</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit">登 录</button>
        </form>
        <div class="demo-info">
            🔑 演示账号: admin / admin123
        </div>
    </div>
</body>
</html>
'''

MAIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>服务监控系统 | 管理面板</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        body {
            background: #f5f7fb;
            min-height: 100vh;
        }
        .app-container {
            display: flex;
            min-height: 100vh;
        }
        /* 侧边栏 */
        .sidebar {
            width: 280px;
            background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
            color: #e2e8f0;
            display: flex;
            flex-direction: column;
            position: fixed;
            height: 100vh;
            overflow-y: auto;
        }
        .sidebar-header {
            padding: 28px 24px;
            border-bottom: 1px solid #334155;
        }
        .sidebar-header h2 {
            font-size: 1.4rem;
            font-weight: 600;
            background: linear-gradient(135deg, #a78bfa, #60a5fa);
            background-clip: text;
            -webkit-background-clip: text;
            color: transparent;
        }
        .sidebar-header p {
            font-size: 0.7rem;
            color: #94a3b8;
            margin-top: 6px;
        }
        .nav-menu {
            flex: 1;
            padding: 24px 0;
        }
        .nav-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 24px;
            margin: 4px 12px;
            border-radius: 12px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            color: #cbd5e1;
        }
        .nav-item:hover, .nav-item.active {
            background: #334155;
            color: white;
        }
        .user-info {
            padding: 20px 24px;
            border-top: 1px solid #334155;
            font-size: 0.85rem;
        }
        .logout-btn {
            background: #dc2626;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 8px;
            cursor: pointer;
            margin-top: 12px;
            width: 100%;
            font-size: 0.8rem;
        }
        /* 主内容区 */
        .main-content {
            flex: 1;
            margin-left: 280px;
            padding: 24px 32px;
        }
        .top-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 28px;
            flex-wrap: wrap;
            gap: 16px;
        }
        .page-title {
            font-size: 1.8rem;
            font-weight: 700;
            color: #0f172a;
        }
        .stats-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 28px;
        }
        .stat-card {
            background: white;
            border-radius: 20px;
            padding: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            border: 1px solid #e2e8f0;
        }
        .stat-card h4 {
            font-size: 0.75rem;
            color: #64748b;
            margin-bottom: 8px;
        }
        .stat-number {
            font-size: 2rem;
            font-weight: 800;
            color: #0f172a;
        }
        .services-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
            gap: 20px;
        }
        .service-card {
            background: white;
            border-radius: 20px;
            border: 1px solid #e2e8f0;
            overflow: hidden;
            transition: all 0.2s;
        }
        .service-card:hover {
            box-shadow: 0 8px 20px rgba(0,0,0,0.08);
            transform: translateY(-2px);
        }
        .card-header {
            padding: 16px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #f1f5f9;
        }
        .service-name {
            font-weight: 700;
            font-size: 1.1rem;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .status-badge {
            padding: 4px 12px;
            border-radius: 30px;
            font-size: 0.7rem;
            font-weight: 600;
        }
        .status-online {
            background: #dcfce7;
            color: #166534;
        }
        .status-offline {
            background: #fee2e2;
            color: #991b1b;
        }
        .card-body {
            padding: 16px 20px;
        }
        .info-row {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            font-size: 0.85rem;
        }
        .info-label {
            color: #64748b;
        }
        .info-value {
            font-weight: 600;
            color: #1e293b;
        }
        .error-msg {
            background: #fee2e2;
            padding: 8px 12px;
            border-radius: 12px;
            font-size: 0.7rem;
            color: #991b1b;
            margin-top: 10px;
        }
        .btn-refresh {
            background: white;
            border: 1px solid #cbd5e1;
            padding: 8px 20px;
            border-radius: 40px;
            cursor: pointer;
            font-weight: 500;
            transition: all 0.2s;
        }
        .btn-refresh:hover {
            background: #f1f5f9;
        }
        .auto-refresh {
            display: flex;
            align-items: center;
            gap: 12px;
            background: white;
            padding: 4px 16px;
            border-radius: 40px;
            border: 1px solid #e2e8f0;
        }
        .auto-refresh input {
            width: 55px;
            padding: 6px;
            border-radius: 20px;
            border: 1px solid #cbd5e1;
            text-align: center;
        }
        .config-panel, .log-container {
            background: white;
            border-radius: 20px;
            border: 1px solid #e2e8f0;
            overflow: hidden;
        }
        .config-header, .log-header {
            padding: 20px 24px;
            background: #f8fafc;
            border-bottom: 1px solid #e2e8f0;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
        }
        .services-table {
            width: 100%;
            overflow-x: auto;
        }
        .services-table table {
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
        }
        .services-table th, .services-table td {
            padding: 14px 12px;
            text-align: left;
            border-bottom: 1px solid #f1f5f9;
            vertical-align: middle;
        }
        .services-table th {
            background: #f8fafc;
            font-weight: 600;
            color: #334155;
            font-size: 0.85rem;
        }
        /* 固定列宽，确保对齐 */
        .services-table th:nth-child(1), .services-table td:nth-child(1) { width: 18%; }
        .services-table th:nth-child(2), .services-table td:nth-child(2) { width: 20%; }
        .services-table th:nth-child(3), .services-table td:nth-child(3) { width: 10%; }
        .services-table th:nth-child(4), .services-table td:nth-child(4) { width: 32%; }
        .services-table th:nth-child(5), .services-table td:nth-child(5) { width: 20%; }
        
        .config-input {
            width: 100%;
            padding: 8px 10px;
            border-radius: 8px;
            border: 1px solid #cbd5e1;
            font-size: 0.85rem;
            background: white;
            transition: all 0.2s;
        }
        .config-input:focus {
            outline: none;
            border-color: #3b82f6;
            box-shadow: 0 0 0 2px rgba(59,130,246,0.1);
        }
        .save-btn, .delete-btn {
            padding: 6px 14px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.75rem;
            font-weight: 500;
            border: none;
            margin: 0 4px;
            transition: all 0.2s;
        }
        .save-btn { 
            background: #10b981; 
            color: white; 
        }
        .save-btn:hover { 
            background: #059669; 
            transform: translateY(-1px);
        }
        .delete-btn { 
            background: #ef4444; 
            color: white; 
        }
        .delete-btn:hover { 
            background: #dc2626; 
            transform: translateY(-1px);
        }
        .add-btn { 
            background: #3b82f6; 
            color: white; 
            padding: 8px 20px;
            border-radius: 40px;
            border: none;
            cursor: pointer;
            font-weight: 500;
            transition: all 0.2s;
        }
        .add-btn:hover {
            background: #2563eb;
            transform: translateY(-1px);
        }
        .log-entry {
            padding: 12px 20px;
            border-bottom: 1px solid #f1f5f9;
            display: flex;
            gap: 12px;
            font-size: 0.85rem;
            align-items: center;
            flex-wrap: wrap;
        }
        .log-time { 
            color: #64748b; 
            min-width: 160px;
            font-family: monospace;
            font-size: 0.8rem;
        }
        .log-status-online { 
            color: #16a34a; 
            font-weight: 500;
            min-width: 60px;
        }
        .log-status-offline { 
            color: #dc2626; 
            font-weight: 500;
            min-width: 60px;
        }
        .log-service {
            font-weight: 600;
            color: #1e293b;
            min-width: 120px;
        }
        .log-addr {
            color: #64748b;
            font-family: monospace;
            font-size: 0.75rem;
        }
        .log-change {
            color: #f59e0b;
            font-size: 0.7rem;
            background: #fef3c7;
            padding: 2px 8px;
            border-radius: 20px;
        }
        .empty-logs { 
            text-align: center; 
            padding: 60px; 
            color: #94a3b8; 
        }
        .loading { 
            display: inline-block; 
            width: 16px; 
            height: 16px; 
            border: 2px solid #e2e8f0; 
            border-top-color: #3b82f6; 
            border-radius: 50%; 
            animation: spin 0.6s linear infinite; 
        }
        @keyframes spin { 
            to { transform: rotate(360deg); } 
        }
        @media (max-width: 768px) {
            .sidebar { width: 0; display: none; }
            .main-content { margin-left: 0; padding: 16px; }
            .services-table th:nth-child(4), .services-table td:nth-child(4) { display: none; }
            .services-table th:nth-child(1), .services-table td:nth-child(1) { width: 25%; }
            .services-table th:nth-child(2), .services-table td:nth-child(2) { width: 25%; }
            .services-table th:nth-child(3), .services-table td:nth-child(3) { width: 15%; }
            .services-table th:nth-child(5), .services-table td:nth-child(5) { width: 35%; }
        }
    </style>
</head>
<body>
    <div class="app-container">
        <div class="sidebar">
            <div class="sidebar-header">
                <h2>🖥️ 服务管家</h2>
                <p>TCP端口监控系统</p>
            </div>
            <div class="nav-menu">
                <div class="nav-item active" data-tab="status">📊 服务状态</div>
                <div class="nav-item" data-tab="config">⚙️ 服务配置</div>
                <div class="nav-item" data-tab="logs">📋 检测日志</div>
            </div>
            <div class="user-info">
                <div>👤 {{ username }}</div>
                <button class="logout-btn" onclick="logout()">退出登录</button>
            </div>
        </div>
        <div class="main-content">
            <div id="statusView"></div>
            <div id="configView" style="display:none;"></div>
            <div id="logsView" style="display:none;"></div>
        </div>
    </div>
    <script>
        let currentTab = 'status';
        let autoRefreshInterval = null;
        let refreshSeconds = 10;
        
        function showToast(msg, isError) {
            const toast = document.createElement('div');
            toast.textContent = msg;
            toast.style.cssText = `position:fixed; bottom:20px; right:20px; background:${isError ? '#dc2626' : '#10b981'}; color:white; padding:10px 20px; border-radius:40px; z-index:1000; font-size:0.85rem; box-shadow:0 4px 12px rgba(0,0,0,0.15);`;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 2500);
        }
        
        async function apiCall(url, options = {}) {
            const res = await fetch(url, {
                headers: { 'Content-Type': 'application/json' },
                ...options
            });
            if (res.status === 401) {
                window.location.href = '/login';
                return null;
            }
            return res.json();
        }
        
        async function checkAllServices() {
            const result = await apiCall('/api/check-all', { method: 'POST' });
            if (result && currentTab === 'status') renderStatusView();
            if (result) showToast(`检测完成: ${result.online_count}/${result.total} 服务在线`, false);
        }
        
        async function renderStatusView() {
            const services = await apiCall('/api/services');
            const status = await apiCall('/api/status');
            if (!services || !status) return;
            
            let onlineCount = 0;
            services.forEach(s => { if (status[s.id]?.online) onlineCount++; });
            const total = services.length;
            const percent = total ? (onlineCount/total*100).toFixed(1) : 0;
            
            let cardsHtml = '';
            services.forEach(svc => {
                const st = status[svc.id] || { online: false, error: null };
                const isOnline = st.online;
                cardsHtml += `
                    <div class="service-card">
                        <div class="card-header">
                            <div class="service-name">${escapeHtml(svc.name)}</div>
                            <span class="status-badge ${isOnline ? 'status-online' : 'status-offline'}">${isOnline ? '🟢 在线' : '🔴 离线'}</span>
                        </div>
                        <div class="card-body">
                            <div class="info-row"><span class="info-label">主机</span><span class="info-value">${escapeHtml(svc.host)}:${svc.port}</span></div>
                            <div class="info-row"><span class="info-label">描述</span><span class="info-value">${escapeHtml(svc.description || '-')}</span></div>
                            ${st.error ? `<div class="error-msg">⚠️ ${escapeHtml(st.error)}</div>` : ''}
                            <div class="info-row"><span class="info-label">最后检测</span><span class="info-value">${new Date().toLocaleTimeString()}</span></div>
                        </div>
                    </div>
                `;
            });
            
            document.getElementById('statusView').innerHTML = `
                <div class="top-bar">
                    <div class="page-title">📡 服务状态监控</div>
                    <div style="display:flex; gap:12px;">
                        <div class="auto-refresh">
                            <span>🔄 自动刷新</span>
                            <input type="number" id="refreshInterval" value="${refreshSeconds}" min="3" max="60" step="1">
                            <span>秒</span>
                        </div>
                        <button class="btn-refresh" onclick="checkAllServices()">⟳ 立即检测</button>
                    </div>
                </div>
                <div class="stats-row">
                    <div class="stat-card"><h4>服务总数</h4><div class="stat-number">${total}</div></div>
                    <div class="stat-card"><h4>在线服务</h4><div class="stat-number">${onlineCount}</div></div>
                    <div class="stat-card"><h4>离线服务</h4><div class="stat-number">${total - onlineCount}</div></div>
                    <div class="stat-card"><h4>健康率</h4><div class="stat-number">${percent}%</div></div>
                </div>
                <div class="services-grid">${cardsHtml}</div>
            `;
            
            document.getElementById('refreshInterval').onchange = (e) => {
                refreshSeconds = Math.min(60, Math.max(3, parseInt(e.target.value) || 10));
                startAutoRefresh();
            };
        }
        
        async function renderConfigView() {
            const services = await apiCall('/api/services');
            if (!services) return;
            
            let rows = '';
            services.forEach(svc => {
                rows += `
                    <tr data-id="${svc.id}">
                        <td><input class="config-input" id="name_${svc.id}" value="${escapeHtml(svc.name)}" placeholder="服务名称"></td>
                        <td><input class="config-input" id="host_${svc.id}" value="${escapeHtml(svc.host)}" placeholder="IP地址"></td>
                        <td><input class="config-input" id="port_${svc.id}" value="${svc.port}" placeholder="端口号" type="number"></td>
                        <td><input class="config-input" id="desc_${svc.id}" value="${escapeHtml(svc.description || '')}" placeholder="服务描述"></td>
                        <td>
                            <button class="save-btn" onclick="saveService('${svc.id}')">💾 保存</button>
                            <button class="delete-btn" onclick="deleteService('${svc.id}')">🗑️ 删除</button>
                        </td>
                    </tr>
                `;
            });
            
            document.getElementById('configView').innerHTML = `
                <div class="top-bar">
                    <div class="page-title">⚙️ 服务配置管理</div>
                    <button class="add-btn" onclick="addService()">+ 新增服务</button>
                </div>
                <div class="config-panel">
                    <div class="config-header"><h3>编辑服务信息</h3><span style="font-size:0.7rem; color:#64748b;">修改后自动保存</span></div>
                    <div class="services-table">
                        <table>
                            <thead>
                                <tr>
                                    <th>服务名称</th>
                                    <th>主机地址</th>
                                    <th>端口</th>
                                    <th>描述</th>
                                    <th>操作</th>
                                </tr>
                            </thead>
                            <tbody id="configTableBody">
                                ${rows || '<tr><td colspan="5" style="text-align:center; padding:40px;">暂无服务，点击上方按钮添加</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
        }
        
        async function renderLogsView() {
            const logs = await apiCall('/api/logs');
            if (!logs) return;
            
            let logsHtml = '';
            if (logs.length === 0) {
                logsHtml = '<div class="empty-logs">📭 暂无检测日志<br>点击"立即检测"开始监控服务</div>';
            } else {
                // 倒序显示，最新的在前面
                [...logs].reverse().forEach(log => {
                    const changedHtml = log.changed ? '<span class="log-change">状态变更</span>' : '';
                    logsHtml += `
                        <div class="log-entry">
                            <div class="log-time">${new Date(log.time).toLocaleString()}</div>
                            <div class="${log.status ? 'log-status-online' : 'log-status-offline'}">${log.status ? '✅ 在线' : '❌ 离线'}</div>
                            <div class="log-service">${escapeHtml(log.service_name)}</div>
                            <div class="log-addr">${escapeHtml(log.host)}:${log.port}</div>
                            ${changedHtml}
                        </div>
                    `;
                });
            }
            
            document.getElementById('logsView').innerHTML = `
                <div class="top-bar">
                    <div class="page-title">📋 检测日志</div>
                    <div class="auto-refresh">
                        <span>🔄 自动刷新间隔</span>
                        <input type="number" id="logRefreshInterval" value="${refreshSeconds}" min="3" max="60" step="1">
                        <span>秒</span>
                    </div>
                </div>
                <div class="log-container">
                    <div class="log-header"><h3>📝 检测记录 (${logs.length}条)</h3></div>
                    <div class="log-list">${logsHtml}</div>
                </div>
            `;
            document.getElementById('logRefreshInterval').onchange = (e) => {
                refreshSeconds = Math.min(60, Math.max(3, parseInt(e.target.value) || 10));
                startAutoRefresh();
            };
        }
        
        window.saveService = async (id) => {
            const name = document.getElementById(`name_${id}`).value;
            const host = document.getElementById(`host_${id}`).value;
            const port = parseInt(document.getElementById(`port_${id}`).value);
            const description = document.getElementById(`desc_${id}`).value;
            if (!name || !host || isNaN(port)) { 
                showToast('请填写完整信息（名称、主机、端口）', true); 
                return; 
            }
            const result = await apiCall('/api/services', { 
                method: 'PUT', 
                body: JSON.stringify({ id, name, host, port, description }) 
            });
            if (result) {
                showToast('保存成功', false);
                renderConfigView();
                checkAllServices();
            }
        };
        
        window.deleteService = async (id) => {
            if (!confirm('确定删除此服务吗？')) return;
            const result = await apiCall(`/api/services/${id}`, { method: 'DELETE' });
            if (result) {
                showToast('删除成功', false);
                renderConfigView();
                checkAllServices();
            }
        };
        
        window.addService = async () => {
            const result = await apiCall('/api/services', { 
                method: 'POST', 
                body: JSON.stringify({ 
                    name: '新服务', 
                    host: '127.0.0.1', 
                    port: 3000, 
                    description: '请输入描述' 
                }) 
            });
            if (result) {
                showToast('添加成功', false);
                renderConfigView();
            }
        };
        
        function startAutoRefresh() {
            if (autoRefreshInterval) clearInterval(autoRefreshInterval);
            autoRefreshInterval = setInterval(() => {
                if (currentTab === 'status') checkAllServices();
                else if (currentTab === 'logs') renderLogsView();
            }, refreshSeconds * 1000);
        }
        
        function switchTab(tab) {
            currentTab = tab;
            document.querySelectorAll('.nav-item').forEach(item => {
                if (item.getAttribute('data-tab') === tab) {
                    item.classList.add('active');
                } else {
                    item.classList.remove('active');
                }
            });
            document.getElementById('statusView').style.display = tab === 'status' ? 'block' : 'none';
            document.getElementById('configView').style.display = tab === 'config' ? 'block' : 'none';
            document.getElementById('logsView').style.display = tab === 'logs' ? 'block' : 'none';
            if (tab === 'status') renderStatusView();
            if (tab === 'config') renderConfigView();
            if (tab === 'logs') renderLogsView();
        }
        
        function logout() { 
            window.location.href = '/logout'; 
        }
        
        function escapeHtml(str) { 
            if (!str) return ''; 
            return str.replace(/[&<>]/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[m])); 
        }
        
        // 绑定导航事件
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => switchTab(item.getAttribute('data-tab')));
        });
        
        // 启动
        startAutoRefresh();
        renderStatusView();
    </script>
</body>
</html>
'''

# ==================== Flask 路由 ====================
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template_string(MAIN_TEMPLATE, username=session.get('username', 'User'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username in USERS and USERS[username]['password'] == password:
            session['user_id'] = username
            session['username'] = username
            return redirect(url_for('index'))
        return render_template_string(LOGIN_TEMPLATE, error='用户名或密码错误')
    return render_template_string(LOGIN_TEMPLATE, error=None)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/services', methods=['GET'])
@login_required
def get_services():
    services = load_services()
    return jsonify(services)

@app.route('/api/services', methods=['POST'])
@login_required
def add_service():
    data = request.json
    services = load_services()
    new_id = f"svc_{int(time.time() * 1000)}_{data.get('port', 0)}"
    new_service = {
        'id': new_id,
        'name': data.get('name', '新服务'),
        'host': data.get('host', '127.0.0.1'),
        'port': data.get('port', 3000),
        'description': data.get('description', ''),
        'enabled': True
    }
    services.append(new_service)
    save_services(services)
    return jsonify(new_service)

@app.route('/api/services', methods=['PUT'])
@login_required
def update_service():
    data = request.json
    services = load_services()
    for svc in services:
        if svc['id'] == data.get('id'):
            svc['name'] = data.get('name', svc['name'])
            svc['host'] = data.get('host', svc['host'])
            svc['port'] = data.get('port', svc['port'])
            svc['description'] = data.get('description', svc.get('description', ''))
            save_services(services)
            return jsonify(svc)
    return jsonify({'error': '服务不存在'}), 404

@app.route('/api/services/<service_id>', methods=['DELETE'])
@login_required
def delete_service(service_id):
    services = load_services()
    services = [s for s in services if s['id'] != service_id]
    save_services(services)
    return jsonify({'success': True})

@app.route('/api/status', methods=['GET'])
@login_required
def get_status():
    services = load_services()
    status_map = {}
    for svc in services:
        if svc.get('enabled', True):
            result = check_service_status(svc)
            status_map[svc['id']] = result
        else:
            status_map[svc['id']] = {'online': False, 'error': '服务已禁用'}
    return jsonify(status_map)

@app.route('/api/check-all', methods=['POST'])
@login_required
def check_all():
    services = load_services()
    results = {}
    online_count = 0
    logs_to_add = []
    
    # 获取旧状态用于判断变化
    old_status = {}
    for svc in services:
        if svc.get('enabled', True):
            old_status[svc['id']] = check_service_status(svc).get('online', False)
    
    for svc in services:
        if svc.get('enabled', True):
            result = check_service_status(svc)
            results[svc['id']] = result
            if result['online']:
                online_count += 1
            
            # 记录日志
            changed = old_status.get(svc['id'], False) != result['online']
            add_log(svc['id'], svc['name'], svc['host'], svc['port'], 
                   result['online'], result.get('error'), changed)
    
    return jsonify({
        'results': results,
        'online_count': online_count,
        'total': len([s for s in services if s.get('enabled', True)]),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/logs', methods=['GET'])
@login_required
def get_logs():
    logs = load_logs()
    # 返回最近200条
    return jsonify(logs[-200:])

if __name__ == '__main__':
    print("=" * 50)
    print("服务监控系统启动")
    print(f"访问地址: http://localhost:5000")
    print(f"默认账号: admin")
    print(f"默认密码: admin123")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)
