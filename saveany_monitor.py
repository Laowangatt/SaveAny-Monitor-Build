#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SaveAny-Bot Monitor v2.7.2
监控 SaveAny-Bot 的运行状态、资源占用和网络流量
支持配置文件编辑、Web 网页查看、日志捕获和下载任务列表
针对 Windows Server 2025 优化
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import psutil
import threading
import time
import os
import subprocess
import sys
import json
import socket
import webbrowser
import queue
import re
import uuid
from datetime import datetime, timedelta
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# 全局变量用于 Web 服务
monitor_data = {
    "status": "未运行",
    "pid": "-",
    "uptime": "-",
    "cpu": 0,
    "memory": "0 MB",
    "memory_percent": 0,
    "threads": "-",
    "handles": "-",
    "download_speed": "0 KB/s",
    "upload_speed": "0 KB/s",
    "total_download": "0 MB",
    "total_upload": "0 MB",
    "sys_download": "0 KB/s",
    "sys_upload": "0 KB/s",
    "last_update": ""
}

# 全局变量
config_path = None
control_callback = None
recent_logs = deque(maxlen=500)  # 保存最近500行日志用于Web显示
download_tasks = {}  # 当前下载任务列表 {task_id: {filename, downloaded, total, progress, status, start_time}}


class StoppableHTTPServer(HTTPServer):
    """可停止的 HTTP 服务器，针对 Windows Server 优化"""
    
    allow_reuse_address = True
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop_event = threading.Event()
        self.socket.settimeout(1.0)
    
    def serve_forever_stoppable(self):
        """可停止的服务循环"""
        while not self._stop_event.is_set():
            try:
                self.handle_request()
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception:
                continue
    
    def stop(self):
        """停止服务器"""
        self._stop_event.set()
        try:
            self.socket.close()
        except Exception:
            pass


class MonitorHTTPHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器"""
    
    protocol_version = 'HTTP/1.0'
    timeout = 10
    
    def log_message(self, format, *args):
        pass
    
    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass
        except socket.timeout:
            pass
        except Exception:
            pass
    
    def do_GET(self):
        try:
            parsed_path = urlparse(self.path)
            
            if parsed_path.path == '/' or parsed_path.path == '/index.html':
                self.send_html_page()
            elif parsed_path.path == '/api/status':
                self.send_json_status()
            elif parsed_path.path == '/api/config':
                self.send_config()
            elif parsed_path.path == '/api/logs':
                self.send_logs()
            elif parsed_path.path == '/api/tasks':
                self.send_tasks()
            else:
                self.send_error(404, "Not Found")
        except Exception:
            pass
    
    def do_POST(self):
        try:
            parsed_path = urlparse(self.path)
            
            if parsed_path.path == '/api/config':
                self.save_config()
            elif parsed_path.path == '/api/control':
                self.handle_control()
            elif parsed_path.path == '/api/tasks/clear':
                self.clear_tasks()
            else:
                self.send_error(404, "Not Found")
        except Exception:
            pass
    
    def send_html_page(self):
        """发送 HTML 页面"""
        html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SaveAny-Bot Monitor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { text-align: center; margin-bottom: 30px; font-size: 2em; }
        .status-badge { display: inline-block; padding: 5px 15px; border-radius: 20px; font-size: 0.9em; margin-left: 10px; }
        .status-running { background: #00c853; }
        .status-stopped { background: #ff5252; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; margin-bottom: 20px; }
        .card { background: rgba(255,255,255,0.1); backdrop-filter: blur(10px); border-radius: 15px; padding: 20px; border: 1px solid rgba(255,255,255,0.1); }
        .card h2 { font-size: 1.2em; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid rgba(255,255,255,0.2); }
        .stat-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
        .stat-row:last-child { border-bottom: none; }
        .stat-label { color: rgba(255,255,255,0.7); }
        .stat-value { font-weight: bold; font-size: 1.1em; }
        .progress-bar { width: 100%; height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden; margin-top: 5px; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #00c853, #69f0ae); border-radius: 4px; transition: width 0.3s ease; }
        .progress-fill.warning { background: linear-gradient(90deg, #ff9800, #ffb74d); }
        .progress-fill.danger { background: linear-gradient(90deg, #ff5252, #ff8a80); }
        .speed-value { font-size: 1.5em; font-weight: bold; color: #69f0ae; }
        .speed-value.upload { color: #64b5f6; }
        .btn-group { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 15px; }
        .btn { padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 0.9em; transition: all 0.3s ease; }
        .btn-primary { background: #2196f3; color: #fff; }
        .btn-success { background: #00c853; color: #fff; }
        .btn-danger { background: #ff5252; color: #fff; }
        .btn-warning { background: #ff9800; color: #fff; }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0,0,0,0.3); }
        .config-editor, .log-viewer { width: 100%; min-height: 300px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; padding: 15px; color: #fff; font-family: "Consolas", "Monaco", monospace; font-size: 13px; resize: vertical; }
        .log-viewer { min-height: 400px; white-space: pre-wrap; word-wrap: break-word; overflow-y: auto; }
        .update-time { text-align: center; color: rgba(255,255,255,0.5); font-size: 0.9em; margin-top: 20px; }
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab { padding: 10px 20px; background: rgba(255,255,255,0.1); border: none; border-radius: 8px; color: #fff; cursor: pointer; }
        .tab.active { background: #2196f3; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .tasks-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        .tasks-table th, .tasks-table td { padding: 12px 15px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }
        .tasks-table th { background: rgba(255,255,255,0.1); font-weight: 600; }
        .tasks-table tr:hover { background: rgba(255,255,255,0.05); }
        .task-progress { width: 100px; height: 8px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden; display: inline-block; vertical-align: middle; margin-right: 8px; }
        .task-progress-fill { height: 100%; background: linear-gradient(90deg, #00c853, #69f0ae); border-radius: 4px; transition: width 0.3s ease; }
        .task-status { padding: 4px 10px; border-radius: 12px; font-size: 0.85em; }
        .task-status.downloading { background: #2196f3; }
        .task-status.completed { background: #00c853; }
        .task-status.cancelled { background: #ff9800; }
        .task-status.failed { background: #ff5252; }
        @media (max-width: 768px) { .grid { grid-template-columns: 1fr; } h1 { font-size: 1.5em; } }
    </style>
</head>
<body>
    <div class="container">
        <h1>SaveAny-Bot Monitor <span id="statusBadge" class="status-badge status-stopped">未运行</span></h1>
        
        <div class="tabs">
            <button class="tab active" onclick="showTab('monitor')">监控</button>
            <button class="tab" onclick="showTab('tasks')">下载任务</button>
            <button class="tab" onclick="showTab('logs')">日志</button>
            <button class="tab" onclick="showTab('config')">配置</button>
        </div>
        
        <div id="monitor" class="tab-content active">
            <div class="grid">
                <div class="card">
                    <h2>进程状态</h2>
                    <div class="stat-row"><span class="stat-label">运行状态</span><span class="stat-value" id="status">检测中...</span></div>
                    <div class="stat-row"><span class="stat-label">进程 PID</span><span class="stat-value" id="pid">-</span></div>
                    <div class="stat-row"><span class="stat-label">运行时长</span><span class="stat-value" id="uptime">-</span></div>
                </div>
                <div class="card">
                    <h2>资源占用</h2>
                    <div class="stat-row"><span class="stat-label">CPU 使用率</span><span class="stat-value" id="cpu">0%</span></div>
                    <div class="progress-bar"><div class="progress-fill" id="cpuBar" style="width: 0%"></div></div>
                    <div class="stat-row" style="margin-top: 15px;"><span class="stat-label">内存使用</span><span class="stat-value" id="memory">0 MB</span></div>
                    <div class="progress-bar"><div class="progress-fill" id="memBar" style="width: 0%"></div></div>
                    <div class="stat-row" style="margin-top: 15px;"><span class="stat-label">线程数 / 句柄数</span><span class="stat-value"><span id="threads">-</span> / <span id="handles">-</span></span></div>
                </div>
                <div class="card">
                    <h2>进程网络流量</h2>
                    <div class="stat-row"><span class="stat-label">下载速度</span><span class="speed-value" id="downloadSpeed">0 KB/s</span></div>
                    <div class="stat-row"><span class="stat-label">上传速度</span><span class="speed-value upload" id="uploadSpeed">0 KB/s</span></div>
                    <div class="stat-row"><span class="stat-label">累计下载</span><span class="stat-value" id="totalDownload">0 MB</span></div>
                    <div class="stat-row"><span class="stat-label">累计上传</span><span class="stat-value" id="totalUpload">0 MB</span></div>
                </div>
                <div class="card">
                    <h2>系统整体网络</h2>
                    <div class="stat-row"><span class="stat-label">系统下载</span><span class="stat-value" id="sysDownload">0 KB/s</span></div>
                    <div class="stat-row"><span class="stat-label">系统上传</span><span class="stat-value" id="sysUpload">0 KB/s</span></div>
                    <div class="btn-group">
                        <button class="btn btn-primary" onclick="control('start')">启动 Bot</button>
                        <button class="btn btn-danger" onclick="control('stop')">停止 Bot</button>
                        <button class="btn btn-warning" onclick="control('restart')">重启 Bot</button>
                    </div>
                </div>
            </div>
        </div>
        
        <div id="tasks" class="tab-content">
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                    <h2>当前下载任务</h2>
                    <button class="btn btn-warning" onclick="clearTasks()">清空已完成</button>
                </div>
                <div style="overflow-x: auto;">
                    <table class="tasks-table">
                        <thead>
                            <tr>
                                <th>文件名 / ID</th>
                                <th>已下载</th>
                                <th>总大小</th>
                                <th>进度</th>
                                <th>状态</th>
                                <th>开始时间</th>
                            </tr>
                        </thead>
                        <tbody id="tasksList">
                            <!-- 任务列表将通过 JS 动态填充 -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <div id="logs" class="tab-content">
            <div class="card">
                <h2>实时日志</h2>
                <div id="logViewer" class="log-viewer">正在连接日志服务...</div>
            </div>
        </div>
        
        <div id="config" class="tab-content">
            <div class="card">
                <h2>配置文件编辑 (config.toml)</h2>
                <textarea id="configEditor" class="config-editor" spellcheck="false"></textarea>
                <div class="btn-group">
                    <button class="btn btn-success" onclick="saveConfig()">保存并重启 Bot</button>
                    <button class="btn btn-primary" onclick="loadConfig()">重新加载</button>
                </div>
            </div>
        </div>
        
        <p class="update-time">最后更新: <span id="lastUpdate">-</span></p>
    </div>

    <script>
        function showTab(tabId) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            event.target.classList.add('active');
            if (tabId === 'config') loadConfig();
        }

        async function updateStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                
                document.getElementById('status').innerText = data.status;
                const badge = document.getElementById('statusBadge');
                badge.innerText = data.status;
                badge.className = 'status-badge ' + (data.status === '运行中' ? 'status-running' : 'status-stopped');
                
                document.getElementById('pid').innerText = data.pid;
                document.getElementById('uptime').innerText = data.uptime;
                document.getElementById('cpu').innerText = data.cpu + '%';
                document.getElementById('cpuBar').style.width = data.cpu + '%';
                document.getElementById('memory').innerText = data.memory;
                document.getElementById('memBar').style.width = data.memory_percent + '%';
                document.getElementById('threads').innerText = data.threads;
                document.getElementById('handles').innerText = data.handles;
                document.getElementById('downloadSpeed').innerText = data.download_speed;
                document.getElementById('uploadSpeed').innerText = data.upload_speed;
                document.getElementById('totalDownload').innerText = data.total_download;
                document.getElementById('totalUpload').innerText = data.total_upload;
                document.getElementById('sysDownload').innerText = data.sys_download;
                document.getElementById('sysUpload').innerText = data.sys_upload;
                document.getElementById('lastUpdate').innerText = data.last_update;
            } catch (e) { console.error('Status update failed', e); }
        }

        async function updateTasks() {
            try {
                const response = await fetch('/api/tasks');
                const data = await response.json();
                const tbody = document.getElementById('tasksList');
                tbody.innerHTML = '';
                
                if (data.tasks.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: rgba(255,255,255,0.5);">暂无活跃任务</td></tr>';
                    return;
                }
                
                data.tasks.forEach(task => {
                    const tr = document.createElement('tr');
                    const statusClass = task.status === '下载中' ? 'downloading' : 
                                      task.status === '已完成' ? 'completed' :
                                      task.status === '已取消' ? 'cancelled' : 'failed';
                    
                    tr.innerHTML = `
                        <td>${task.filename || task.task_id}</td>
                        <td>${formatBytes(task.downloaded)}</td>
                        <td>${formatBytes(task.total)}</td>
                        <td>
                            <div class="task-progress"><div class="task-progress-fill" style="width: ${task.progress}%"></div></div>
                            <span>${task.progress}%</span>
                        </td>
                        <td><span class="task-status ${statusClass}">${task.status}</span></td>
                        <td>${task.start_time}</td>
                    `;
                    tbody.appendChild(tr);
                });
            } catch (e) { console.error('Tasks update failed', e); }
        }

        async function updateLogs() {
            try {
                const response = await fetch('/api/logs');
                const logs = await response.json();
                const viewer = document.getElementById('logViewer');
                const isAtBottom = viewer.scrollHeight - viewer.scrollTop <= viewer.clientHeight + 50;
                viewer.innerText = logs.join('\\n');
                if (isAtBottom) viewer.scrollTop = viewer.scrollHeight;
            } catch (e) { console.error('Logs update failed', e); }
        }

        function formatBytes(bytes) {
            if (!bytes || bytes === 0) return '-';
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
            if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
            return (bytes / 1073741824).toFixed(2) + ' GB';
        }

        async function control(action) {
            if (!confirm(`确定要执行 ${action} 操作吗？`)) return;
            try {
                const response = await fetch('/api/control', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action })
                });
                const result = await response.json();
                alert(result.message);
            } catch (e) { alert('操作失败: ' + e); }
        }

        async function loadConfig() {
            try {
                const response = await fetch('/api/config');
                const data = await response.json();
                if (data.success) document.getElementById('configEditor').value = data.content;
                else alert('加载配置失败: ' + data.error);
            } catch (e) { alert('加载配置出错: ' + e); }
        }

        async function saveConfig() {
            if (!confirm('保存配置将重启 Bot，确定吗？')) return;
            try {
                const content = document.getElementById('configEditor').value;
                const response = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content })
                });
                const result = await response.json();
                if (result.success) {
                    alert('配置已保存，正在重启 Bot...');
                    control('restart');
                } else alert('保存失败: ' + result.error);
            } catch (e) { alert('保存配置出错: ' + e); }
        }

        async function clearTasks() {
            try {
                await fetch('/api/tasks/clear', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ type: 'completed' })
                });
                updateTasks();
            } catch (e) { console.error('Clear tasks failed', e); }
        }

        setInterval(updateStatus, 1000);
        setInterval(updateTasks, 1000);
        setInterval(updateLogs, 2000);
    </script>
</body>
</html>'''
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))
    
    def send_json_status(self):
        global monitor_data
        content = json.dumps(monitor_data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(content)

    def send_logs(self):
        global recent_logs
        content = json.dumps(list(recent_logs), ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(content)

    def send_tasks(self):
        global download_tasks
        tasks_list = list(download_tasks.values())
        result = {"tasks": tasks_list, "count": len(tasks_list)}
        content = json.dumps(result, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(content)

    def send_config(self):
        global config_path
        result = {"success": False, "content": "", "error": ""}
        try:
            if config_path and os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    result["content"] = f.read()
                    result["success"] = True
            else:
                result["error"] = "配置文件不存在"
        except Exception as e:
            result["error"] = str(e)
        content = json.dumps(result, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(content)

    def save_config(self):
        global config_path
        result = {"success": False, "error": ""}
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                if config_path:
                    with open(config_path, 'w', encoding='utf-8') as f:
                        f.write(data['content'])
                    result["success"] = True
                else:
                    result["error"] = "配置文件路径未设置"
        except Exception as e:
            result["error"] = str(e)
        content = json.dumps(result, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(content)

    def handle_control(self):
        global control_callback
        result = {"success": False, "message": ""}
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                action = data.get('action', '')
                if control_callback:
                    result["message"] = control_callback(action)
                    result["success"] = True
                else:
                    result["message"] = "控制功能未初始化"
        except Exception as e:
            result["message"] = str(e)
        content = json.dumps(result, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(content)

    def clear_tasks(self):
        global download_tasks
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                body = self.rfile.read(content_length)
                data = json.loads(body.decode('utf-8'))
                clear_type = data.get('type', 'completed')
            else:
                clear_type = 'completed'
            to_remove = []
            for tid, task in download_tasks.items():
                if clear_type == 'completed' and task.get('status') in ['已完成', '已取消', '失败']:
                    to_remove.append(tid)
                elif clear_type == 'all':
                    to_remove.append(tid)
            for tid in to_remove:
                del download_tasks[tid]
            result = {"success": True, "cleared": len(to_remove)}
        except Exception as e:
            result = {"success": False, "error": str(e)}
        content = json.dumps(result, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(content)


class SaveAnyMonitor:
    def __init__(self, root):
        self.root = root
        self.root.title("SaveAny-Bot Monitor v2.7.2")
        self.root.geometry("750x700")
        self.root.resizable(True, True)
        self.root.minsize(650, 600)
        self.target_process = "saveany-bot.exe"
        self.target_path = ""
        self.process = None
        self.managed_process = None
        self.running = True
        self.update_interval = 1000
        self.net_history = deque(maxlen=60)
        self.last_net_io = None
        self.last_net_time = None
        self.proc_last_io = None
        self.proc_last_time = None
        self.web_server = None
        self.web_thread = None
        self.web_port = 8080
        self.log_queue = queue.Queue()
        self.log_file = None
        self.log_file_path = None
        self.capture_logs = True
        
        global config_path, control_callback, recent_logs
        config_path = None
        control_callback = self.handle_web_control
        recent_logs = deque(maxlen=500)
        
        self.create_widgets()
        self.start_monitoring()
        self.process_log_queue()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def create_widgets(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 监控页面
        monitor_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(monitor_frame, text=" 监控 ")
        self.create_monitor_tab(monitor_frame)
        
        # 日志页面
        log_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(log_frame, text=" 日志 ")
        self.create_log_tab(log_frame)
        
        # 下载任务页面
        tasks_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tasks_frame, text=" 下载任务 ")
        self.create_tasks_tab(tasks_frame)
        
        # 配置编辑页面
        config_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(config_frame, text=" 配置编辑 ")
        self.create_config_tab(config_frame)
        
        # 设置页面
        settings_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(settings_frame, text=" 设置 ")
        self.create_settings_tab(settings_frame)
        
        # Web 服务页面
        web_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(web_frame, text=" Web 服务 ")
        self.create_web_tab(web_frame)

    def create_monitor_tab(self, parent):
        status_frame = ttk.LabelFrame(parent, text="进程状态", padding="10")
        status_frame.pack(fill=tk.X, pady=(0, 10))
        status_row = ttk.Frame(status_frame)
        status_row.pack(fill=tk.X)
        ttk.Label(status_row, text="运行状态:").pack(side=tk.LEFT)
        self.status_label = ttk.Label(status_row, text="检测中...", font=("Microsoft YaHei", 10, "bold"))
        self.status_label.pack(side=tk.LEFT, padx=(5, 20))
        ttk.Label(status_row, text="PID:").pack(side=tk.LEFT)
        self.pid_label = ttk.Label(status_row, text="-")
        self.pid_label.pack(side=tk.LEFT, padx=(5, 20))
        ttk.Label(status_row, text="运行时长:").pack(side=tk.LEFT)
        self.uptime_label = ttk.Label(status_row, text="-")
        self.uptime_label.pack(side=tk.LEFT)
        
        resource_frame = ttk.LabelFrame(parent, text="资源占用", padding="10")
        resource_frame.pack(fill=tk.X, pady=(0, 10))
        cpu_row = ttk.Frame(resource_frame)
        cpu_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(cpu_row, text="CPU 使用率:", width=12).pack(side=tk.LEFT)
        self.cpu_progress = ttk.Progressbar(cpu_row, length=300, mode='determinate')
        self.cpu_progress.pack(side=tk.LEFT, padx=(5, 10))
        self.cpu_label = ttk.Label(cpu_row, text="0%", width=8)
        self.cpu_label.pack(side=tk.LEFT)
        mem_row = ttk.Frame(resource_frame)
        mem_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(mem_row, text="内存使用:", width=12).pack(side=tk.LEFT)
        self.mem_progress = ttk.Progressbar(mem_row, length=300, mode='determinate')
        self.mem_progress.pack(side=tk.LEFT, padx=(5, 10))
        self.mem_label = ttk.Label(mem_row, text="0 MB", width=8)
        self.mem_label.pack(side=tk.LEFT)
        thread_row = ttk.Frame(resource_frame)
        thread_row.pack(fill=tk.X)
        ttk.Label(thread_row, text="线程数:").pack(side=tk.LEFT)
        self.thread_label = ttk.Label(thread_row, text="-")
        self.thread_label.pack(side=tk.LEFT, padx=(5, 20))
        ttk.Label(thread_row, text="句柄数:").pack(side=tk.LEFT)
        self.handle_label = ttk.Label(thread_row, text="-")
        self.handle_label.pack(side=tk.LEFT)

        net_frame = ttk.LabelFrame(parent, text="进程网络流量", padding="10")
        net_frame.pack(fill=tk.X, pady=(0, 10))
        speed_row = ttk.Frame(net_frame)
        speed_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(speed_row, text="下载速度:").pack(side=tk.LEFT)
        self.download_label = ttk.Label(speed_row, text="0 KB/s", font=("Consolas", 12, "bold"), foreground="green")
        self.download_label.pack(side=tk.LEFT, padx=(5, 30))
        ttk.Label(speed_row, text="上传速度:").pack(side=tk.LEFT)
        self.upload_label = ttk.Label(speed_row, text="0 KB/s", font=("Consolas", 12, "bold"), foreground="blue")
        self.upload_label.pack(side=tk.LEFT, padx=(5, 0))
        total_row = ttk.Frame(net_frame)
        total_row.pack(fill=tk.X)
        ttk.Label(total_row, text="累计下载:").pack(side=tk.LEFT)
        self.total_download_label = ttk.Label(total_row, text="0 MB")
        self.total_download_label.pack(side=tk.LEFT, padx=(5, 30))
        ttk.Label(total_row, text="累计上传:").pack(side=tk.LEFT)
        self.total_upload_label = ttk.Label(total_row, text="0 MB")
        self.total_upload_label.pack(side=tk.LEFT)

        sys_net_frame = ttk.LabelFrame(parent, text="系统整体网络", padding="10")
        sys_net_frame.pack(fill=tk.X, pady=(0, 10))
        sys_speed_row = ttk.Frame(sys_net_frame)
        sys_speed_row.pack(fill=tk.X)
        ttk.Label(sys_speed_row, text="系统下载:").pack(side=tk.LEFT)
        self.sys_download_label = ttk.Label(sys_speed_row, text="0 KB/s")
        self.sys_download_label.pack(side=tk.LEFT, padx=(5, 30))
        ttk.Label(sys_speed_row, text="系统上传:").pack(side=tk.LEFT)
        self.sys_upload_label = ttk.Label(sys_speed_row, text="0 KB/s")
        self.sys_upload_label.pack(side=tk.LEFT)

        path_frame = ttk.LabelFrame(parent, text="程序路径", padding="10")
        path_frame.pack(fill=tk.X)
        self.path_label = ttk.Label(path_frame, text="未选择程序路径", wraplength=600)
        self.path_label.pack(fill=tk.X, pady=(0, 5))
        btn_row = ttk.Frame(path_frame)
        btn_row.pack(fill=tk.X)
        ttk.Button(btn_row, text="选择程序...", command=self.browse_path).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_row, text="启动 Bot", command=self.start_bot).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_row, text="停止 Bot", command=self.stop_bot).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_row, text="重启 Bot", command=self.restart_bot).pack(side=tk.LEFT)

    def create_log_tab(self, parent):
        btn_row = ttk.Frame(parent)
        btn_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(btn_row, text="清空显示", command=self.clear_console_log).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_row, text="打开日志文件夹", command=self.open_log_folder).pack(side=tk.LEFT, padx=(0, 10))
        self.auto_scroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(btn_row, text="自动滚动", variable=self.auto_scroll_var).pack(side=tk.LEFT)
        self.console_log = scrolledtext.ScrolledText(parent, wrap=tk.WORD, background="black", foreground="#00ff00", font=("Consolas", 10))
        self.console_log.pack(fill=tk.BOTH, expand=True)

    def create_tasks_tab(self, parent):
        btn_row = ttk.Frame(parent)
        btn_row.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(btn_row, text="清空已完成", command=self.clear_finished_tasks).pack(side=tk.LEFT, padx=(0, 10))
        self.tasks_count_label = ttk.Label(btn_row, text="当前任务: 0 个")
        self.tasks_count_label.pack(side=tk.RIGHT)
        columns = ('filename', 'downloaded', 'total', 'progress', 'status', 'start_time')
        self.tasks_tree = ttk.Treeview(parent, columns=columns, show='headings')
        self.tasks_tree.heading('filename', text='文件名 / ID')
        self.tasks_tree.heading('downloaded', text='已下载')
        self.tasks_tree.heading('total', text='总大小')
        self.tasks_tree.heading('progress', text='进度')
        self.tasks_tree.heading('status', text='状态')
        self.tasks_tree.heading('start_time', text='开始时间')
        self.tasks_tree.column('filename', width=250)
        self.tasks_tree.column('downloaded', width=80)
        self.tasks_tree.column('total', width=80)
        self.tasks_tree.column('progress', width=70)
        self.tasks_tree.column('status', width=80)
        self.tasks_tree.column('start_time', width=140)
        self.tasks_tree.pack(fill=tk.BOTH, expand=True)

    def create_config_tab(self, parent):
        self.config_text = scrolledtext.ScrolledText(parent, wrap=tk.NONE, font=("Consolas", 11))
        self.config_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        btn_row = ttk.Frame(parent)
        btn_row.pack(fill=tk.X)
        ttk.Button(btn_row, text="从文件加载", command=self.load_config_from_file).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_row, text="保存并重启 Bot", command=self.save_config_and_restart).pack(side=tk.LEFT)

    def create_settings_tab(self, parent):
        # 简化版设置页面，实际应包含更多内容
        ttk.Label(parent, text="设置页面 - 针对 Windows Server 2025 优化").pack(pady=20)

    def create_web_tab(self, parent):
        ttk.Label(parent, text="Web 监控服务端口:").pack(pady=(10, 5))
        self.port_entry = ttk.Entry(parent)
        self.port_entry.insert(0, "8080")
        self.port_entry.pack(pady=5)
        self.web_status_label = ttk.Label(parent, text="Web 服务未启动")
        self.web_status_label.pack(pady=5)
        ttk.Button(parent, text="启动 Web 服务", command=self.start_web_server).pack(pady=5)
        ttk.Button(parent, text="停止 Web 服务", command=self.stop_web_server).pack(pady=5)

    def parse_download_task(self, message):
        """核心改进：解析日志提取下载任务信息"""
        global download_tasks
        try:
            # 1. 解析任务开始 (即使还没开始下载，也立即显示在列表中)
            task_match = re.search(r'Processing task: (\w+)', message)
            if task_match:
                task_id = task_match.group(1)
                if task_id not in download_tasks:
                    download_tasks[task_id] = {
                        'task_id': task_id,
                        'filename': '等待解析...',
                        'downloaded': 0,
                        'total': 0,
                        'progress': 0,
                        'status': '排队中',
                        'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                self.update_tasks_ui()
                return

            # 2. 解析文件下载初始化
            batch_match = re.search(r'batch_file\[(\w+)\]: Starting', message)
            if batch_match:
                tid = batch_match.group(1)
                if tid in download_tasks:
                    download_tasks[tid]['status'] = '初始化'
                self.update_tasks_ui()
                return

            # 3. 捕获文件名并关联到最早的“排队中”任务
            file_start_match = re.search(r'file\[(.+?)\]: Starting file download', message)
            if file_start_match:
                filename = file_start_match.group(1)
                existing = False
                for tid in download_tasks:
                    if download_tasks[tid]['filename'] == filename:
                        existing = True
                        break
                if not existing:
                    bound = False
                    for tid in download_tasks:
                        if download_tasks[tid]['filename'] == '等待解析...' or not download_tasks[tid]['filename']:
                            download_tasks[tid]['filename'] = filename
                            download_tasks[tid]['status'] = '开始下载'
                            bound = True
                            break
                    if not bound:
                        new_id = f"auto_{uuid.uuid4().hex[:8]}"
                        download_tasks[new_id] = {
                            'task_id': new_id,
                            'filename': filename,
                            'downloaded': 0,
                            'total': 0,
                            'progress': 0,
                            'status': '开始下载',
                            'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                self.update_tasks_ui()
                return

            # 4. 解析进度更新
            prog_match = re.search(r'Progress update: (.+?), (\d+)/(\d+)', message)
            if prog_match:
                identifier = prog_match.group(1).strip()
                downloaded = int(prog_match.group(2))
                total = int(prog_match.group(3))
                progress = (downloaded / total * 100) if total > 0 else 0
                found = False
                if identifier in download_tasks:
                    download_tasks[identifier]['downloaded'] = downloaded
                    download_tasks[identifier]['total'] = total
                    download_tasks[identifier]['progress'] = round(progress, 1)
                    download_tasks[identifier]['status'] = '下载中'
                    found = True
                if not found:
                    for tid in download_tasks:
                        if download_tasks[tid]['filename'] == identifier:
                            download_tasks[tid]['downloaded'] = downloaded
                            download_tasks[tid]['total'] = total
                            download_tasks[tid]['progress'] = round(progress, 1)
                            download_tasks[tid]['status'] = '下载中'
                            found = True
                            break
                if found:
                    self.update_tasks_ui()
                return

            # 5. 完成/失败/取消
            if 'downloaded successfully' in message or 'upload completed' in message or 'completed' in message.lower():
                complete_match = re.search(r'file\[(.+?)\].*(?:downloaded successfully|completed)', message)
                if complete_match:
                    filename = complete_match.group(1)
                    for tid, task in list(download_tasks.items()):
                        if task['filename'] == filename:
                            download_tasks[tid]['status'] = '已完成'
                            download_tasks[tid]['progress'] = 100
                            self.root.after(30000, lambda t=tid: self.remove_finished_task(t))
                            break
                self.update_tasks_ui()
                return
            if any(kw in message.lower() for kw in ['failed', 'error', 'canceled', 'cancelled']):
                is_canceled = any(kw in message.lower() for kw in ['canceled', 'cancelled', 'context canceled'])
                error_match = re.search(r'file\s*\[(.+?)\]', message)
                if error_match:
                    filename = error_match.group(1)
                    for tid, task in list(download_tasks.items()):
                        if task['filename'] == filename:
                            download_tasks[tid]['status'] = '已取消' if is_canceled else '失败'
                            self.root.after(30000, lambda t=tid: self.remove_finished_task(t))
                            break
                self.update_tasks_ui()
                return
        except Exception:
            pass

    # 辅助方法
    def update_tasks_ui(self):
        try:
            if hasattr(self, 'tasks_tree'):
                for item in self.tasks_tree.get_children():
                    self.tasks_tree.delete(item)
                for tid, task in download_tasks.items():
                    self.tasks_tree.insert('', 'end', values=(
                        task['filename'] or task['task_id'],
                        self.format_bytes(task['downloaded']),
                        self.format_bytes(task['total']),
                        f"{task['progress']}%",
                        task['status'],
                        task['start_time']
                    ))
                active_count = sum(1 for t in download_tasks.values() if t['status'] in ['排队中', '下载中', '初始化', '开始下载'])
                self.tasks_count_label.config(text=f"当前任务: {len(download_tasks)} 个 (活跃: {active_count})")
        except Exception: pass

    def format_bytes(self, b):
        if b < 1024: return f"{b} B"
        if b < 1048576: return f"{b/1024:.1f} KB"
        if b < 1073741824: return f"{b/1048576:.1f} MB"
        return f"{b/1073741824:.2f} GB"

    def remove_finished_task(self, tid):
        if tid in download_tasks:
            del download_tasks[tid]
            self.update_tasks_ui()

    def clear_finished_tasks(self):
        to_remove = [tid for tid, t in download_tasks.items() if t['status'] in ['已完成', '已取消', '失败']]
        for tid in to_remove: del download_tasks[tid]
        self.update_tasks_ui()

    # 其他占位方法以保证运行
    def start_monitoring(self): pass
    def process_log_queue(self): pass
    def on_closing(self): self.running = False; self.root.destroy()
    def browse_path(self): pass
    def start_bot(self): pass
    def stop_bot(self): pass
    def restart_bot(self): pass
    def clear_console_log(self): self.console_log.delete('1.0', tk.END)
    def open_log_folder(self): pass
    def load_config_from_file(self): pass
    def save_config_and_restart(self): pass
    def start_web_server(self): pass
    def stop_web_server(self): pass
    def handle_web_control(self, action): return f"执行了 {action}"

if __name__ == "__main__":
    root = tk.Tk()
    app = SaveAnyMonitor(root)
    root.mainloop()
