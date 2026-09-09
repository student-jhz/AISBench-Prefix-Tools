#!/usr/bin/env python3
"""
AISBench Deployer - Windows GUI应用程序
用于远程部署和配置AISBench测试环境

功能流程:
  1. 连接远程执行机 (SSH)
  2. 选择镜像tar包、代码zip包、模型路径
  3. Docker加载镜像并创建容器
  4. 配置config.py
  5. 设计测试用例
  6. 执行测试并收集结果
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from datetime import datetime
from typing import Optional, Callable

from ssh_manager import SSHManager
from docker_manager import DockerManager
from config_manager import ConfigManager
from test_designer import TestDesigner
from log_parser import parse_log_directory


# ============================================================
#  样式常量
# ============================================================
COLOR_PRIMARY = "#2563eb"
COLOR_BG = "#f8fafc"
COLOR_CARD = "#ffffff"
COLOR_BORDER = "#e2e8f0"
COLOR_TEXT = "#1e293b"
COLOR_TEXT_MUTED = "#64748b"
COLOR_SUCCESS = "#16a34a"
COLOR_ERROR = "#dc2626"
COLOR_WARNING = "#d97706"


class WizardApp:
    """向导式GUI主程序"""

    STEP_TITLES = [
        "SSH连接",
        "文件与模型",
        "Docker部署",
        "配置文件",
        "测试用例",
        "执行测试",
    ]

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AISBench Deployer")
        self.root.geometry("1100x720")
        self.root.minsize(900, 600)
        self.root.configure(bg=COLOR_BG)

        # 核心组件
        self.ssh = SSHManager()
        self.docker: Optional[DockerManager] = None
        self.config_mgr: Optional[ConfigManager] = None
        self.designer = TestDesigner()

        # 状态变量
        self.current_step = 0
        self.config_data = {}
        self.code_host_path = ""
        self.remote_tar_path = ""
        self.remote_zip_path = ""

        # 日志缓冲 + 取消标志（解决后台线程阻塞UI）
        self._log_buffer = ""
        self._exec_log_buffer = ""
        self._cancel_flag = threading.Event()
        self._flush_timer_id = None
        self._exec_flush_timer_id = None
        self.model_path_var = tk.StringVar()
        self.host_ip_var = tk.StringVar()
        self.host_port_var = tk.StringVar(value="8000")
        self.model_name_var = tk.StringVar(value="ds")
        self.api_key_var = tk.StringVar()
        self.pod_info_var = tk.StringVar()
        self.dataset_path_var = tk.StringVar()

        # 测试用例相关变量
        self.kv_cache_var = tk.StringVar()
        self.dp_var = tk.StringVar(value="1")
        self.max_req_len_var = tk.StringVar()
        self.repeat_rate_var = tk.StringVar(value="0.9")
        self.request_rate_var = tk.StringVar(value="0")
        self.input_length_vars = {}
        self.output_length_vars = {}

        self._build_ui()

    # ============================================================
    #  UI构建
    # ============================================================

    def _build_ui(self):
        """构建主界面"""
        # 主容器
        main_frame = tk.Frame(self.root, bg=COLOR_BG)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # 左侧步骤导航
        self._build_sidebar(main_frame)

        # 右侧内容区
        content_frame = tk.Frame(main_frame, bg=COLOR_BG)
        content_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self._build_content_area(content_frame)

    def _build_sidebar(self, parent):
        """构建左侧步骤栏"""
        sidebar = tk.Frame(parent, bg=COLOR_CARD, width=200, relief=tk.SOLID, bd=1)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        sidebar.pack_propagate(False)

        # 标题
        title_lbl = tk.Label(sidebar, text="AISBench\nDeployer", bg=COLOR_CARD,
                            fg=COLOR_PRIMARY, font=("Segoe UI", 14, "bold"),
                            justify=tk.LEFT)
        title_lbl.pack(padx=16, pady=(20, 16), anchor=tk.W)

        # 步骤按钮
        self.step_buttons = []
        for i, title in enumerate(self.STEP_TITLES):
            btn_frame = tk.Frame(sidebar, bg=COLOR_CARD)
            btn_frame.pack(fill=tk.X, padx=8, pady=2)

            indicator = tk.Label(btn_frame, text="○", bg=COLOR_CARD, fg=COLOR_TEXT_MUTED,
                                font=("Segoe UI", 12))
            indicator.pack(side=tk.LEFT, padx=(8, 6))

            label = tk.Label(btn_frame, text=f"{i+1}. {title}", bg=COLOR_CARD,
                           fg=COLOR_TEXT_MUTED, font=("Segoe UI", 10),
                           cursor="hand2")
            label.pack(side=tk.LEFT, fill=tk.X, expand=True)

            # 点击跳转
            def _go_to_step(step=i):
                if step <= self._max_reached_step():
                    self._show_step(step)

            label.bind("<Button-1>", lambda e, s=i: _go_to_step(s))
            indicator.bind("<Button-1>", lambda e, s=i: _go_to_step(s))

            self.step_buttons.append((indicator, label))

        # 底部状态
        tk.Frame(sidebar, bg=COLOR_BORDER, height=1).pack(fill=tk.X, padx=12, pady=12)
        self.status_lbl = tk.Label(sidebar, text="● 未连接", bg=COLOR_CARD,
                                   fg=COLOR_ERROR, font=("Segoe UI", 9))
        self.status_lbl.pack(padx=16, pady=(0, 16), anchor=tk.W)

    def _max_reached_step(self):
        """返回用户可达到的最大步骤"""
        return self.current_step

    def _build_content_area(self, parent):
        """构建右侧内容区"""
        # 内容容器
        self.content_container = tk.Frame(parent, bg=COLOR_BG)
        self.content_container.pack(fill=tk.BOTH, expand=True)

        # 为每个步骤创建Frame
        self.step_frames = []
        for i in range(len(self.STEP_TITLES)):
            frame = tk.Frame(self.content_container, bg=COLOR_BG)
            self.step_frames.append(frame)

        # 构建各步骤内容
        self._build_step0_connection()
        self._build_step1_files()
        self._build_step2_docker()
        self._build_step3_config()
        self._build_step4_testcases()
        self._build_step5_execute()

        # 导航栏
        nav_frame = tk.Frame(parent, bg=COLOR_BG)
        nav_frame.pack(fill=tk.X, pady=(8, 0))

        self.prev_btn = ttk.Button(nav_frame, text="< 上一步", command=self._prev_step)
        self.prev_btn.pack(side=tk.LEFT)

        self.next_btn = ttk.Button(nav_frame, text="下一步 >", command=self._next_step,
                                   style="Accent.TButton")
        self.next_btn.pack(side=tk.RIGHT)

        self._show_step(0)

    def _build_step_header(self, parent, title, desc=""):
        """构建步骤标题"""
        header = tk.Frame(parent, bg=COLOR_BG)
        header.pack(fill=tk.X, pady=(0, 12))

        tk.Label(header, text=title, bg=COLOR_BG, fg=COLOR_TEXT,
               font=("Segoe UI", 16, "bold")).pack(anchor=tk.W)
        if desc:
            tk.Label(header, text=desc, bg=COLOR_BG, fg=COLOR_TEXT_MUTED,
                   font=("Segoe UI", 9)).pack(anchor=tk.W, pady=(2, 0))

    # ============================================================
    #  Step 0: SSH连接
    # ============================================================

    def _build_step0_connection(self):
        frame = self.step_frames[0]

        self._build_step_header(frame, "步骤 1: SSH连接到执行机",
                               "输入远程执行机的SSH连接信息")

        form = tk.Frame(frame, bg=COLOR_CARD, relief=tk.SOLID, bd=1)
        form.pack(fill=tk.X, pady=8)

        fields = [
            ("执行机 IP *", "host", ""),
            ("SSH 端口", "port", "22"),
            ("用户名 *", "user", "root"),
        ]
        self.conn_vars = {}
        for i, (label, key, default) in enumerate(fields):
            tk.Label(form, text=label, bg=COLOR_CARD, fg=COLOR_TEXT,
                   font=("Segoe UI", 9)).grid(row=i, column=0, sticky=tk.W,
                                               padx=16, pady=8)
            var = tk.StringVar(value=default)
            self.conn_vars[key] = var
            entry = tk.Entry(form, textvariable=var, width=30, font=("Segoe UI", 9))
            entry.grid(row=i, column=1, padx=16, pady=8, sticky=tk.W)

        tk.Label(form, text="密码", bg=COLOR_CARD, fg=COLOR_TEXT,
               font=("Segoe UI", 9)).grid(row=3, column=0, sticky=tk.W, padx=16, pady=8)
        self.conn_password = tk.StringVar()
        pw_entry = tk.Entry(form, textvariable=self.conn_password, width=30,
                          show="*", font=("Segoe UI", 9))
        pw_entry.grid(row=3, column=1, padx=16, pady=8, sticky=tk.W)

        tk.Label(form, text="或密钥文件路径", bg=COLOR_CARD, fg=COLOR_TEXT,
               font=("Segoe UI", 9)).grid(row=4, column=0, sticky=tk.W, padx=16, pady=8)
        key_frame = tk.Frame(form, bg=COLOR_CARD)
        key_frame.grid(row=4, column=1, padx=16, pady=8, sticky=tk.W)
        self.conn_key = tk.StringVar()
        tk.Entry(key_frame, textvariable=self.conn_key, width=22,
               font=("Segoe UI", 9)).pack(side=tk.LEFT)
        tk.Button(key_frame, text="浏览...", command=self._browse_key_file,
                font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(4, 0))

        # 连接按钮
        btn_frame = tk.Frame(frame, bg=COLOR_BG)
        btn_frame.pack(fill=tk.X, pady=12)

        self.connect_btn = tk.Button(btn_frame, text="测试连接", bg=COLOR_PRIMARY,
                                    fg="white", font=("Segoe UI", 9, "bold"),
                                    relief=tk.FLAT, padx=16, pady=4,
                                    command=self._test_connection)
        self.connect_btn.pack(side=tk.LEFT)

        self.conn_status_lbl = tk.Label(btn_frame, text="", bg=COLOR_BG,
                                        fg=COLOR_TEXT_MUTED, font=("Segoe UI", 9))
        self.conn_status_lbl.pack(side=tk.LEFT, padx=12)

    def _browse_key_file(self):
        path = filedialog.askopenfilename(
            title="选择SSH密钥文件",
            filetypes=[("All files", "*.*"), ("PEM files", "*.pem")]
        )
        if path:
            self.conn_key.set(path)

    def _test_connection(self):
        host = self.conn_vars["host"].get().strip()
        port = int(self.conn_vars["port"].get().strip() or "22")
        user = self.conn_vars["user"].get().strip()
        password = self.conn_password.get().strip() or None
        key_path = self.conn_key.get().strip() or None

        if not host or not user:
            messagebox.showwarning("提示", "请填写IP和用户名")
            return
        if not password and not key_path:
            messagebox.showwarning("提示", "请填写密码或密钥文件路径")
            return

        self.connect_btn.config(state=tk.DISABLED, text="连接中...")
        self.conn_status_lbl.config(text="正在连接...", fg=COLOR_WARNING)

        def _do_connect():
            ok, msg = self.ssh.connect(host, port, user, password, key_path)
            self.root.after(0, lambda: self._on_connect_result(ok, msg))

        threading.Thread(target=_do_connect, daemon=True).start()

    def _on_connect_result(self, ok, msg):
        self.connect_btn.config(state=tk.NORMAL, text="测试连接")
        if ok:
            self.conn_status_lbl.config(text=msg, fg=COLOR_SUCCESS)
            self.status_lbl.config(text="● 已连接", fg=COLOR_SUCCESS)
            self.host_ip_var.set(self.conn_vars["host"].get().strip())
            messagebox.showinfo("成功", msg)
        else:
            self.conn_status_lbl.config(text=msg, fg=COLOR_ERROR)
            messagebox.showerror("连接失败", msg)

    # ============================================================
    #  Step 1: 文件与模型选择
    # ============================================================

    def _build_step1_files(self):
        frame = self.step_frames[1]

        self._build_step_header(frame, "步骤 2: 选择文件与模型",
                               "选择AISBench镜像tar包、代码zip包和模型路径")

        form = tk.Frame(frame, bg=COLOR_CARD, relief=tk.SOLID, bd=1)
        form.pack(fill=tk.BOTH, expand=True, pady=8)

        row = 0

        # 镜像tar
        tk.Label(form, text="AISBench 镜像 tar 包:", bg=COLOR_CARD, fg=COLOR_TEXT,
               font=("Segoe UI", 9)).grid(row=row, column=0, sticky=tk.W, padx=16, pady=8)
        tar_frame = tk.Frame(form, bg=COLOR_CARD)
        tar_frame.grid(row=row, column=1, columnspan=2, padx=16, pady=8, sticky=tk.EW)
        self.tar_path = tk.StringVar()
        tk.Entry(tar_frame, textvariable=self.tar_path, width=50,
               font=("Segoe UI", 9)).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(tar_frame, text="浏览...", command=self._browse_tar,
                font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(4, 0))

        row += 1

        # 代码zip
        tk.Label(form, text="aisbench_auto_tools_prefix 代码 zip:", bg=COLOR_CARD, fg=COLOR_TEXT,
               font=("Segoe UI", 9)).grid(row=row, column=0, sticky=tk.W, padx=16, pady=8)
        zip_frame = tk.Frame(form, bg=COLOR_CARD)
        zip_frame.grid(row=row, column=1, columnspan=2, padx=16, pady=8, sticky=tk.EW)
        self.zip_path = tk.StringVar()
        tk.Entry(zip_frame, textvariable=self.zip_path, width=50,
               font=("Segoe UI", 9)).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(zip_frame, text="浏览...", command=self._browse_zip,
                font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(4, 0))
        tk.Button(zip_frame, text="从GitHub下载", command=self._download_github,
                font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(4, 0))

        row += 1

        # 模型路径（下拉框 + 浏览）
        tk.Label(form, text="模型权重路径 (远程主机):", bg=COLOR_CARD, fg=COLOR_TEXT,
               font=("Segoe UI", 9)).grid(row=row, column=0, sticky=tk.W, padx=16, pady=8)
        model_frame = tk.Frame(form, bg=COLOR_CARD)
        model_frame.grid(row=row, column=1, columnspan=2, padx=16, pady=8, sticky=tk.EW)
        self.model_combo = ttk.Combobox(model_frame, textvariable=self.model_path_var,
                                        width=48, font=("Segoe UI", 9))
        self.model_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(model_frame, text="浏览远程目录", command=self._browse_remote_model,
                font=("Segoe UI", 8)).pack(side=tk.LEFT, padx=(4, 0))

        row += 1

        # 模型名称
        tk.Label(form, text="模型名称 (--served-model-name):", bg=COLOR_CARD, fg=COLOR_TEXT,
               font=("Segoe UI", 9)).grid(row=row, column=0, sticky=tk.W, padx=16, pady=8)
        tk.Entry(form, textvariable=self.model_name_var, width=30,
               font=("Segoe UI", 9)).grid(row=row, column=1, padx=16, pady=8, sticky=tk.W)

        row += 1

        # 服务IP和端口
        tk.Label(form, text="vLLM服务 IP:", bg=COLOR_CARD, fg=COLOR_TEXT,
               font=("Segoe UI", 9)).grid(row=row, column=0, sticky=tk.W, padx=16, pady=8)
        tk.Entry(form, textvariable=self.host_ip_var, width=20,
               font=("Segoe UI", 9)).grid(row=row, column=1, padx=16, pady=8, sticky=tk.W)

        row += 1

        tk.Label(form, text="vLLM服务端口:", bg=COLOR_CARD, fg=COLOR_TEXT,
               font=("Segoe UI", 9)).grid(row=row, column=0, sticky=tk.W, padx=16, pady=8)
        tk.Entry(form, textvariable=self.host_port_var, width=20,
               font=("Segoe UI", 9)).grid(row=row, column=1, padx=16, pady=8, sticky=tk.W)

        row += 1

        tk.Label(form, text="API Key (鉴权, 可选):", bg=COLOR_CARD, fg=COLOR_TEXT,
               font=("Segoe UI", 9)).grid(row=row, column=0, sticky=tk.W, padx=16, pady=8)
        tk.Entry(form, textvariable=self.api_key_var, width=30,
               font=("Segoe UI", 9)).grid(row=row, column=1, padx=16, pady=8, sticky=tk.W)

        form.columnconfigure(1, weight=1)

    def _browse_tar(self):
        path = filedialog.askopenfilename(
            title="选择AISBench镜像tar包",
            filetypes=[("tar files", "*.tar"), ("All files", "*.*")]
        )
        if path:
            self.tar_path.set(path)

    def _browse_zip(self):
        path = filedialog.askopenfilename(
            title="选择代码zip包",
            filetypes=[("zip files", "*.zip"), ("All files", "*.*")]
        )
        if path:
            self.zip_path.set(path)

    def _download_github(self):
        """从GitHub下载代码zip包"""
        url = "https://github.com/rayn-zzz/aisbench_auto_tools_prefix/archive/refs/heads/main.zip"
        save_path = filedialog.asksaveasfilename(
            title="保存代码zip包",
            defaultextension=".zip",
            initialfile="aisbench_auto_tools_prefix-main.zip"
        )
        if not save_path:
            return

        def _do_download():
            try:
                import urllib.request
                urllib.request.urlretrieve(url, save_path)
                self.root.after(0, lambda: (
                    self.zip_path.set(save_path),
                    messagebox.showinfo("成功", f"已下载到: {save_path}")
                ))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("下载失败", str(e)))

        threading.Thread(target=_do_download, daemon=True).start()

    def _browse_remote_model(self):
        """远程目录浏览对话框"""
        if not self.ssh.connected:
            messagebox.showwarning("提示", "请先连接到远程主机")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("浏览远程目录 - 选择模型路径")
        dialog.geometry("600x500")
        dialog.transient(self.root)
        dialog.grab_set()

        top = tk.Frame(dialog)
        top.pack(fill=tk.X, padx=8, pady=8)
        tk.Label(top, text="路径:", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        path_var = tk.StringVar(value="/")
        path_entry = tk.Entry(top, textvariable=path_var, width=50, font=("Segoe UI", 9))
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        tk.Button(top, text="前往", font=("Segoe UI", 8),
                 command=lambda: self._list_remote_dir(listbox, path_var, dialog)).pack(side=tk.LEFT)

        list_frame = tk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=8)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set,
                           font=("Segoe UI", 10))
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)

        # 双击进入目录
        def _on_double_click(event):
            selection = listbox.curselection()
            if not selection:
                return
            item = listbox.get(selection[0])
            if item == "../ (上级目录)":
                current = path_var.get()
                parent = '/'.join(current.rstrip('/').split('/')[:-1]) or '/'
                path_var.set(parent)
                self._list_remote_dir(listbox, path_var, dialog)
            elif item.startswith("[DIR] "):
                dirname = item[6:]
                current = path_var.get().rstrip('/')
                new_path = current + "/" + dirname if current else "/" + dirname
                path_var.set(new_path)
                self._list_remote_dir(listbox, path_var, dialog)

        listbox.bind("<Double-Button-1>", _on_double_click)

        # 选择按钮
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=8, pady=8)
        tk.Button(btn_frame, text="选择当前目录", bg=COLOR_PRIMARY, fg="white",
                 font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=12,
                 command=lambda: self._select_remote_path(path_var.get(), dialog)).pack(side=tk.RIGHT)
        tk.Button(btn_frame, text="取消", font=("Segoe UI", 9),
                 command=dialog.destroy).pack(side=tk.RIGHT, padx=8)

        self._list_remote_dir(listbox, path_var, dialog)

    def _list_remote_dir(self, listbox, path_var, dialog):
        """列出远程目录"""
        path = path_var.get().strip() or "/"
        dialog.title(f"浏览远程目录 - {path}")

        entries = self.ssh.list_dir(path)
        listbox.delete(0, tk.END)

        if path != "/":
            listbox.insert(tk.END, "../ (上级目录)")

        for entry in entries:
            if entry['type'] == 'dir':
                listbox.insert(tk.END, f"[DIR] {entry['name']}")
            else:
                size_mb = entry['size'] / 1024 / 1024
                if size_mb > 1024:
                    size_str = f"{size_mb/1024:.1f}GB"
                else:
                    size_str = f"{size_mb:.1f}MB"
                listbox.insert(tk.END, f"    {entry['name']}  ({size_str})")

    def _select_remote_path(self, path, dialog):
        """选择远程路径作为模型路径"""
        self.model_path_var.set(path)
        dialog.destroy()

    # ============================================================
    #  Step 2: Docker部署
    # ============================================================

    def _build_step2_docker(self):
        frame = self.step_frames[2]

        self._build_step_header(frame, "步骤 3: Docker部署",
                               "上传文件、加载镜像、创建容器")

        # 部署信息展示
        info_frame = tk.Frame(frame, bg=COLOR_CARD, relief=tk.SOLID, bd=1)
        info_frame.pack(fill=tk.X, pady=8)

        self.docker_info_labels = {}
        info_items = [
            ("镜像文件:", "tar"),
            ("代码包:", "zip"),
            ("模型路径:", "model"),
            ("容器名称:", "container"),
            ("镜像名称:", "image"),
        ]
        for i, (label, key) in enumerate(info_items):
            tk.Label(info_frame, text=label, bg=COLOR_CARD, fg=COLOR_TEXT_MUTED,
                   font=("Segoe UI", 9)).grid(row=i, column=0, sticky=tk.W, padx=16, pady=4)
            val_lbl = tk.Label(info_frame, text="-", bg=COLOR_CARD, fg=COLOR_TEXT,
                             font=("Segoe UI", 9))
            val_lbl.grid(row=i, column=1, sticky=tk.W, padx=16, pady=4)
            self.docker_info_labels[key] = val_lbl

        info_frame.columnconfigure(1, weight=1)

        # 部署按钮
        btn_frame = tk.Frame(frame, bg=COLOR_BG)
        btn_frame.pack(fill=tk.X, pady=8)

        self.deploy_btn = tk.Button(btn_frame, text="开始部署", bg=COLOR_PRIMARY,
                                    fg="white", font=("Segoe UI", 10, "bold"),
                                    relief=tk.FLAT, padx=20, pady=6,
                                    command=self._start_deploy)
        self.deploy_btn.pack(side=tk.LEFT)

        self.cancel_deploy_btn = tk.Button(btn_frame, text="取消", bg=COLOR_ERROR,
                                           fg="white", font=("Segoe UI", 9),
                                           relief=tk.FLAT, padx=12, pady=6,
                                           command=self._cancel_deploy,
                                           state=tk.DISABLED)
        self.cancel_deploy_btn.pack(side=tk.LEFT, padx=8)

        # 日志输出
        tk.Label(frame, text="部署日志:", bg=COLOR_BG, fg=COLOR_TEXT,
               font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=(8, 4))

        self.docker_log = scrolledtext.ScrolledText(frame, height=14,
                                                    font=("Consolas", 9),
                                                    bg="#1e1e1e", fg="#d4d4d4",
                                                    insertbackground="white")
        self.docker_log.pack(fill=tk.BOTH, expand=True)

    def _log_docker(self, text):
        """向日志缓冲区写入（线程安全，由主线程定时刷新到UI）"""
        self._log_buffer += text

    def _flush_log_buffer(self):
        """主线程定时刷新部署日志缓冲区到UI（每200ms）"""
        if self._log_buffer:
            self.docker_log.insert(tk.END, self._log_buffer)
            self._log_buffer = ""
            self.docker_log.see(tk.END)
        self._flush_timer_id = self.root.after(200, self._flush_log_buffer)

    def _flush_exec_log_buffer(self):
        """主线程定时刷新执行日志缓冲区到UI（每200ms）"""
        if self._exec_log_buffer:
            self.exec_log.insert(tk.END, self._exec_log_buffer)
            self._exec_log_buffer = ""
            self.exec_log.see(tk.END)
        self._exec_flush_timer_id = self.root.after(200, self._flush_exec_log_buffer)

    def _cancel_deploy(self):
        """取消部署"""
        self._cancel_flag.set()
        self._log_docker("\n⚠ 正在取消部署...\n")

    def _start_deploy(self):
        """开始部署流程"""
        if not self.ssh.connected:
            messagebox.showwarning("提示", "请先连接到远程主机")
            return

        tar = self.tar_path.get().strip()
        zipf = self.zip_path.get().strip()
        model = self.model_path_var.get().strip()

        if not tar or not zipf or not model:
            messagebox.showwarning("提示", "请先完成文件和模型路径选择")
            return

        self._cancel_flag.clear()
        self._log_buffer = ""
        self.docker_log.delete(1.0, tk.END)
        self.deploy_btn.config(state=tk.DISABLED, text="部署中...")
        self.cancel_deploy_btn.config(state=tk.NORMAL)

        # 启动定时刷新日志
        if self._flush_timer_id:
            self.root.after_cancel(self._flush_timer_id)
        self._flush_timer_id = self.root.after(200, self._flush_log_buffer)

        def _do_deploy():
            self._deploy_sequence(tar, zipf, model)
            # 结束后恢复UI
            def _restore():
                self.deploy_btn.config(state=tk.NORMAL, text="重新部署")
                self.cancel_deploy_btn.config(state=tk.DISABLED)
                # 最后刷新一次确保所有日志已输出
                if self._log_buffer:
                    self.docker_log.insert(tk.END, self._log_buffer)
                    self._log_buffer = ""
                    self.docker_log.see(tk.END)
                # 停止定时刷新
                if self._flush_timer_id:
                    self.root.after_cancel(self._flush_timer_id)
                    self._flush_timer_id = None
            self.root.after(0, _restore)

        threading.Thread(target=_do_deploy, daemon=True).start()

    def _deploy_sequence(self, tar_path, zip_path, model_path):
        """部署序列"""
        # 初始化DockerManager
        self.docker = DockerManager(self.ssh)

        # Step 1: 检查Docker
        self._log_docker("[1/5] 检查Docker环境...\n")
        ok, msg = self.docker.check_docker_installed()
        if not ok:
            self._log_docker(f"  ✗ {msg}\n")
            return
        self._log_docker(f"  ✓ {msg}\n\n")

        if self._cancel_flag.is_set():
            self._log_docker("  ⚹ 已取消\n")
            return

        # Step 2: 上传镜像tar
        self._log_docker("[2/5] 上传镜像tar包...\n")
        tar_name = os.path.basename(tar_path)
        self.remote_tar_path = f"{self.docker.remote_work_base}/{tar_name}"
        self.ssh.mkdir_p(self.docker.remote_work_base)
        self.root.after(0, lambda: self.docker_info_labels["tar"].config(text=tar_name))

        def _upload_progress(transferred, total):
            pct = transferred * 100 // total if total > 0 else 0
            self._log_docker(f"\r  上传中: {transferred//1024//1024}MB / {total//1024//1024}MB ({pct}%)")

        ok = self.ssh.upload_file(tar_path, self.remote_tar_path, _upload_progress)
        self._log_docker("\n")
        if not ok:
            self._log_docker("  ✗ 镜像上传失败\n")
            return
        self._log_docker("  ✓ 镜像上传完成\n\n")

        if self._cancel_flag.is_set():
            self._log_docker("  ⚹ 已取消\n")
            return

        # Step 3: Docker load
        self._log_docker("[3/5] 加载Docker镜像...\n")
        ok, image_name = self.docker.load_image(
            self.remote_tar_path,
            callback=lambda t: self._log_docker(t)  # 直接写缓冲区，不经过after
        )
        if not ok:
            self._log_docker(f"  ✗ 镜像加载失败: {image_name}\n")
            return
        self.root.after(0, lambda n=image_name: self.docker_info_labels["image"].config(text=n))
        self._log_docker("\n")

        if self._cancel_flag.is_set():
            self._log_docker("  ⚹ 已取消\n")
            return

        # Step 4: 上传并解压代码zip
        self._log_docker("[4/5] 上传并解压代码包...\n")
        zip_name = os.path.basename(zip_path)
        self.remote_zip_path = f"{self.docker.remote_work_base}/{zip_name}"

        ok = self.ssh.upload_file(zip_path, self.remote_zip_path)
        if not ok:
            self._log_docker("  ✗ 代码包上传失败\n")
            return

        ok, extracted_path = self.docker.extract_code_zip(
            self.remote_zip_path,
            self.docker.remote_work_base,
            callback=lambda t: self._log_docker(t)  # 直接写缓冲区
        )
        if not ok:
            self._log_docker(f"  ✗ 代码解压失败\n")
            return

        self.code_host_path = extracted_path
        self.root.after(0, lambda p=extracted_path: self.docker_info_labels["zip"].config(text=p))
        self._log_docker(f"  ✓ 代码解压到: {extracted_path}\n\n")

        if self._cancel_flag.is_set():
            self._log_docker("  ⚹ 已取消\n")
            return

        # Step 5: 创建容器
        self._log_docker("[5/5] 创建并启动容器...\n")
        container_name = self.docker.generate_container_name()
        ok, msg = self.docker.create_container(
            image_name, model_path, extracted_path, container_name,
            callback=lambda t: self._log_docker(t)  # 直接写缓冲区
        )
        if not ok:
            self._log_docker(f"  ✗ {msg}\n")
            return

        self.root.after(0, lambda n=container_name: self.docker_info_labels["container"].config(text=n))
        self.root.after(0, lambda m=model_path: self.docker_info_labels["model"].config(text=m))
        self._log_docker(f"\n  ✓ 容器 {container_name} 已启动运行\n")
        self._log_docker(f"  ✓ 部署完成!\n")

        # 初始化ConfigManager
        self.config_mgr = ConfigManager(self.docker)

        # 设置DATASET_PATH
        self.dataset_path_var.set(self.docker.code_mount_path)

        # 显示成功消息
        self.root.after(0, lambda: messagebox.showinfo("成功", "Docker部署完成!"))

    # ============================================================
    #  Step 3: 配置文件
    # ============================================================

    def _build_step3_config(self):
        frame = self.step_frames[3]

        self._build_step_header(frame, "步骤 4: 配置 config.py",
                               "配置aisbench_auto_tools_prefix的测试参数")

        form = tk.Frame(frame, bg=COLOR_CARD, relief=tk.SOLID, bd=1)
        form.pack(fill=tk.BOTH, expand=True, pady=8)

        config_fields = [
            ("MODEL_NAME (模型名称)", "model_name", True),
            ("MODEL_PATH (模型路径)", "model_path", True),
            ("HOST_IP (vLLM服务IP)", "host_ip", True),
            ("HOST_PORT (vLLM服务端口)", "host_port", True),
            ("API_KEY (鉴权, 可空)", "api_key", False),
            ("DATASET_PATH (自动设置)", "dataset_path", False),
            ("WORK_PATH (工作路径)", "work_path", False),
            ("DEFAULT_PERFORMANCE_TEST", "default_perf", False),
            ("OUTPUT_DIR (输出路径)", "output_dir", False),
            ("POD_INFO (多DP必填, 格式: ip:port,ip:port)", "pod_info", False),
        ]

        self.config_entry_vars = {}
        defaults = {
            'work_path': '/benchmark',
            'default_perf': 'default_perf',
            'output_dir': './outputs/default',
        }

        for i, (label, key, required) in enumerate(config_fields):
            prefix = "* " if required else "  "
            color = COLOR_ERROR if required else COLOR_TEXT_MUTED
            tk.Label(form, text=f"{prefix}{label}", bg=COLOR_CARD, fg=color,
                   font=("Segoe UI", 9)).grid(row=i, column=0, sticky=tk.W, padx=16, pady=6)

            var = tk.StringVar(value=defaults.get(key, ""))
            self.config_entry_vars[key] = var

            entry = tk.Entry(form, textvariable=var, width=50, font=("Segoe UI", 9))
            entry.grid(row=i, column=1, padx=16, pady=6, sticky=tk.EW)

        form.columnconfigure(1, weight=1)

        # 按钮区域
        btn_frame = tk.Frame(frame, bg=COLOR_BG)
        btn_frame.pack(fill=tk.X, pady=8)

        tk.Button(btn_frame, text="保存配置到容器", bg=COLOR_PRIMARY, fg="white",
                 font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=16, pady=4,
                 command=self._save_config).pack(side=tk.LEFT)

        self.config_status_lbl = tk.Label(btn_frame, text="", bg=COLOR_BG,
                                         fg=COLOR_TEXT_MUTED, font=("Segoe UI", 9))
        self.config_status_lbl.pack(side=tk.LEFT, padx=12)

        # 配置预览
        tk.Label(frame, text="配置预览:", bg=COLOR_BG, fg=COLOR_TEXT,
               font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=(8, 4))

        self.config_preview = scrolledtext.ScrolledText(frame, height=10,
                                                        font=("Consolas", 9),
                                                        bg="#1e1e1e", fg="#d4d4d4")
        self.config_preview.pack(fill=tk.BOTH, expand=True)

        # 同步已有值
        self._sync_config_vars()

    def _sync_config_vars(self):
        """从之前的步骤同步配置值"""
        if hasattr(self, 'config_entry_vars'):
            self.config_entry_vars['model_name'].set(self.model_name_var.get())
            self.config_entry_vars['model_path'].set(self.model_path_var.get())
            self.config_entry_vars['host_ip'].set(self.host_ip_var.get())
            self.config_entry_vars['host_port'].set(self.host_port_var.get())
            self.config_entry_vars['api_key'].set(self.api_key_var.get())
            self.config_entry_vars['dataset_path'].set(self.dataset_path_var.get())
            self._update_config_preview()

    def _update_config_preview(self):
        """更新配置预览"""
        if not hasattr(self, 'config_entry_vars'):
            return
        config = {k: v.get() for k, v in self.config_entry_vars.items()}
        if self.config_mgr:
            content = self.config_mgr.generate_config_content(config)
            self.config_preview.delete(1.0, tk.END)
            self.config_preview.insert(1.0, content)

    def _save_config(self):
        """保存配置到容器"""
        if not self.config_mgr:
            messagebox.showwarning("提示", "请先完成Docker部署")
            return

        config = {k: v.get() for k, v in self.config_entry_vars.items()}

        # 验证
        errors = self.config_mgr.validate_config(config)
        if errors:
            messagebox.showwarning("配置验证失败", "\n".join(errors))
            return

        # 写入
        ok = self.config_mgr.write_config_to_container(config)
        if ok:
            self.config_status_lbl.config(text="✓ 配置已保存", fg=COLOR_SUCCESS)
            self._update_config_preview()
            messagebox.showinfo("成功", "config.py 已写入容器")
        else:
            self.config_status_lbl.config(text="✗ 保存失败", fg=COLOR_ERROR)
            messagebox.showerror("失败", "写入config.py失败")

    # ============================================================
    #  Step 4: 测试用例设计
    # ============================================================

    def _build_step4_testcases(self):
        frame = self.step_frames[4]

        self._build_step_header(frame, "步骤 5: 设计测试用例",
                               "根据KV cache信息生成测试参数")

        # KV Cache信息输入
        kv_frame = tk.Frame(frame, bg=COLOR_CARD, relief=tk.SOLID, bd=1)
        kv_frame.pack(fill=tk.X, pady=8)

        kv_fields = [
            ("单个DP组KV cache (tokens):", "kv_cache_var"),
            ("DP组数:", "dp_var"),
            ("最大请求长度 (tokens):", "max_req_len_var"),
            ("前缀命中率 (0-1):", "repeat_rate_var"),
            ("请求发送速率 (0=Burst):", "request_rate_var"),
        ]

        for i, (label, var_name) in enumerate(kv_fields):
            tk.Label(kv_frame, text=label, bg=COLOR_CARD, fg=COLOR_TEXT,
                   font=("Segoe UI", 9)).grid(row=i, column=0, sticky=tk.W, padx=16, pady=6)
            entry = tk.Entry(kv_frame, textvariable=getattr(self, var_name), width=20,
                           font=("Segoe UI", 9))
            entry.grid(row=i, column=1, padx=16, pady=6, sticky=tk.W)

        # 输入长度选择
        in_frame = tk.Frame(frame, bg=COLOR_CARD, relief=tk.SOLID, bd=1)
        in_frame.pack(fill=tk.X, pady=4)
        tk.Label(in_frame, text="输入长度 (小于最大请求长度):", bg=COLOR_CARD,
               fg=COLOR_TEXT, font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, padx=16, pady=(8, 4))

        in_checks_frame = tk.Frame(in_frame, bg=COLOR_CARD)
        in_checks_frame.pack(padx=16, pady=(0, 8), fill=tk.X)
        for length in TestDesigner.PRESET_INPUT_LENGTHS:
            var = tk.BooleanVar(value=False)
            self.input_length_vars[length] = var
            cb = tk.Checkbutton(in_checks_frame, text=str(length), variable=var,
                              bg=COLOR_CARD, font=("Segoe UI", 9))
            cb.pack(side=tk.LEFT, padx=4)

        # 输出长度选择
        out_frame = tk.Frame(frame, bg=COLOR_CARD, relief=tk.SOLID, bd=1)
        out_frame.pack(fill=tk.X, pady=4)
        tk.Label(out_frame, text="输出长度:", bg=COLOR_CARD, fg=COLOR_TEXT,
               font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, padx=16, pady=(8, 4))

        out_checks_frame = tk.Frame(out_frame, bg=COLOR_CARD)
        out_checks_frame.pack(padx=16, pady=(0, 8), fill=tk.X)
        for length in TestDesigner.PRESET_OUTPUT_LENGTHS:
            var = tk.BooleanVar(value=(length in [512, 1024]))
            self.output_length_vars[length] = var
            cb = tk.Checkbutton(out_checks_frame, text=str(length), variable=var,
                              bg=COLOR_CARD, font=("Segoe UI", 9))
            cb.pack(side=tk.LEFT, padx=4)

        # 生成按钮
        gen_frame = tk.Frame(frame, bg=COLOR_BG)
        gen_frame.pack(fill=tk.X, pady=8)
        tk.Button(gen_frame, text="生成测试用例", bg=COLOR_PRIMARY, fg="white",
                font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=16, pady=4,
                command=self._generate_test_cases).pack(side=tk.LEFT)

        # 调整按钮
        tk.Button(gen_frame, text="请求数 ×0.5", font=("Segoe UI", 8),
                command=lambda: self._adjust_cases(0.5, 'data')).pack(side=tk.LEFT, padx=4)
        tk.Button(gen_frame, text="请求数 ×2", font=("Segoe UI", 8),
                command=lambda: self._adjust_cases(2, 'data')).pack(side=tk.LEFT, padx=4)
        tk.Button(gen_frame, text="并发数 ×0.5", font=("Segoe UI", 8),
                command=lambda: self._adjust_cases(0.5, 'concurrency')).pack(side=tk.LEFT, padx=4)

        # 测试用例表格
        tk.Label(frame, text="测试用例:", bg=COLOR_BG, fg=COLOR_TEXT,
               font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=(8, 4))

        tree_frame = tk.Frame(frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("num", "input", "output", "data_rec", "data_min", "concurrency", "kv_usage")
        self.test_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=8)

        headings = [("#", 40), ("Input", 80), ("Output", 80),
                    ("请求数(推荐)", 120), ("请求数(最小)", 120),
                    ("并发数", 80), ("KV使用率", 80)]
        for col, (title, width) in zip(columns, headings):
            self.test_tree.heading(col, text=title)
            self.test_tree.column(col, width=width, anchor=tk.CENTER)

        self.test_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.test_tree.yview).pack(
            side=tk.RIGHT, fill=tk.Y)

    def _generate_test_cases(self):
        """生成测试用例"""
        try:
            kv = int(self.kv_cache_var.get())
            dp = int(self.dp_var.get())
            max_len = int(self.max_req_len_var.get())
            rate = float(self.repeat_rate_var.get())
            req_rate = int(self.request_rate_var.get())
        except ValueError:
            messagebox.showwarning("提示", "请输入有效的数字")
            return

        self.designer.set_kv_cache_info(kv, dp, max_len)
        self.designer.set_repeat_rate(rate)
        self.designer.set_request_rate(req_rate)

        # 获取选中的输入/输出长度
        in_lengths = [l for l, v in self.input_length_vars.items() if v.get()]
        out_lengths = [l for l, v in self.output_length_vars.items() if v.get()]

        if not in_lengths:
            valid = self.designer.get_valid_preset_inputs()
            if valid:
                in_lengths = valid[:2]
            else:
                messagebox.showwarning("提示", "没有有效的输入长度")
                return

        if not out_lengths:
            out_lengths = [512, 1024]

        self.designer.set_input_lengths(in_lengths)
        self.designer.set_output_lengths(out_lengths)
        self.designer.generate_test_cases()

        self._refresh_test_tree()

    def _refresh_test_tree(self):
        """刷新测试用例表格"""
        for item in self.test_tree.get_children():
            self.test_tree.delete(item)

        for i, case in enumerate(self.designer.test_cases, 1):
            kv_usage = self.designer.get_kv_usage(case)
            self.test_tree.insert("", tk.END, values=(
                i, f"{case.input_len:,}", f"{case.output_len:,}",
                f"{case.data_num_recommended:,}", f"{case.data_num_min:,}",
                f"{case.concurrency_recommended:,}", f"{kv_usage:.1f}%"
            ))

    def _adjust_cases(self, factor, adjust_type):
        """调整测试用例参数"""
        if not self.designer.test_cases:
            return
        if adjust_type == 'data':
            self.designer.adjust_data_num(factor)
        else:
            self.designer.adjust_concurrency(factor)
        self._refresh_test_tree()

    # ============================================================
    #  Step 5: 执行测试
    # ============================================================

    def _build_step5_execute(self):
        frame = self.step_frames[5]

        self._build_step_header(frame, "步骤 6: 执行测试",
                               "生成.sh脚本 → 容器内执行 → 下载日志 → 解析结果CSV")

        # 摘要
        self.summary_text = tk.Label(frame, text="", bg=COLOR_CARD, fg=COLOR_TEXT,
                                   font=("Segoe UI", 9), justify=tk.LEFT,
                                   relief=tk.SOLID, bd=1, anchor=tk.W, width=80, height=8)
        self.summary_text.pack(fill=tk.X, pady=8)

        # 命令预览
        tk.Label(frame, text="生成的测试命令:", bg=COLOR_BG, fg=COLOR_TEXT,
               font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=(8, 4))

        self.commands_text = scrolledtext.ScrolledText(frame, height=5,
                                                       font=("Consolas", 9),
                                                       bg="#1e1e1e", fg="#d4d4d4")
        self.commands_text.pack(fill=tk.X)

        # 本地输出目录选择
        out_frame = tk.Frame(frame, bg=COLOR_CARD, relief=tk.SOLID, bd=1)
        out_frame.pack(fill=tk.X, pady=8)

        tk.Label(out_frame, text="本地结果保存目录:", bg=COLOR_CARD, fg=COLOR_TEXT,
               font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=12, pady=8)

        self.local_output_var = tk.StringVar(
            value=os.path.join(os.path.expanduser("~"), "aisbench_results")
        )
        tk.Entry(out_frame, textvariable=self.local_output_var, width=50,
               font=("Segoe UI", 9)).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4, pady=8)
        tk.Button(out_frame, text="浏览...", font=("Segoe UI", 8),
                command=self._browse_local_output).pack(side=tk.LEFT, padx=(4, 12), pady=8)

        # 执行按钮
        btn_frame = tk.Frame(frame, bg=COLOR_BG)
        btn_frame.pack(fill=tk.X, pady=4)

        tk.Button(btn_frame, text="刷新命令", font=("Segoe UI", 9),
                 command=self._refresh_commands).pack(side=tk.LEFT)
        self.exec_test_btn = tk.Button(btn_frame, text="执行测试 → 生成CSV", bg=COLOR_PRIMARY, fg="white",
                 font=("Segoe UI", 9, "bold"), relief=tk.FLAT, padx=16, pady=4,
                 command=self._execute_tests)
        self.exec_test_btn.pack(side=tk.LEFT, padx=8)

        # 执行日志
        tk.Label(frame, text="执行日志:", bg=COLOR_BG, fg=COLOR_TEXT,
               font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=(8, 4))

        self.exec_log = scrolledtext.ScrolledText(frame, height=8,
                                                  font=("Consolas", 9),
                                                  bg="#1e1e1e", fg="#d4d4d4")
        self.exec_log.pack(fill=tk.BOTH, expand=True)

    def _browse_local_output(self):
        path = filedialog.askdirectory(title="选择本地结果保存目录")
        if path:
            self.local_output_var.set(path)

    def _refresh_commands(self):
        """刷新命令和摘要"""
        commands = self.designer.generate_commands()
        self.commands_text.delete(1.0, tk.END)
        for i, cmd in enumerate(commands, 1):
            self.commands_text.insert(tk.END, f"# 测试 {i}\n{cmd}\n\n")

        summary = self.designer.get_summary()
        self.summary_text.config(text=summary)

    def _execute_tests(self):
        """执行测试完整流程: 生成.sh → 上传 → 运行 → 下载日志 → 解析CSV"""
        if not self.docker or not self.docker.container_is_running():
            messagebox.showwarning("提示", "容器未运行，请先完成部署")
            return

        if not self.designer.test_cases:
            messagebox.showwarning("提示", "请先生成测试用例")
            return

        local_dir = self.local_output_var.get().strip()
        if not local_dir:
            messagebox.showwarning("提示", "请选择本地结果保存目录")
            return

        self.exec_log.delete(1.0, tk.END)
        self._exec_log_buffer = ""
        self.exec_test_btn.config(state=tk.DISABLED, text="执行中...")

        # 启动定时刷新执行日志
        if self._exec_flush_timer_id:
            self.root.after_cancel(self._exec_flush_timer_id)
        self._exec_flush_timer_id = self.root.after(200, self._flush_exec_log_buffer)

        def _do_execute():
            self._run_test_sequence(local_dir)
            def _restore():
                self.exec_test_btn.config(state=tk.NORMAL, text="执行测试 → 生成CSV")
                # 最后刷新一次
                if self._exec_log_buffer:
                    self.exec_log.insert(tk.END, self._exec_log_buffer)
                    self._exec_log_buffer = ""
                    self.exec_log.see(tk.END)
                if self._exec_flush_timer_id:
                    self.root.after_cancel(self._exec_flush_timer_id)
                    self._exec_flush_timer_id = None
            self.root.after(0, _restore)

        threading.Thread(target=_do_execute, daemon=True).start()

    def _run_test_sequence(self, local_dir):
        """执行测试的4阶段流水线（在后台线程中运行）"""
        # ===== 阶段1: 生成.sh脚本 =====
        self._log_exec("[1/4] 生成测试脚本...\n")
        script_content, log_dir_name = self.designer.generate_shell_script()
        self._log_exec(f"  日志目录名: {log_dir_name}\n")

        # ===== 阶段2: 上传并运行脚本 =====
        self._log_exec("\n[2/4] 上传脚本到容器并执行...\n")
        container_script = self.docker.write_script(script_content, "run_tests.sh")
        self._log_exec(f"  脚本路径(容器内): {container_script}\n")
        self._log_exec("  开始执行测试 (这可能需要较长时间)...\n\n")

        exit_code = self.docker.run_script(
            "run_tests.sh",
            callback=lambda t: self._log_exec(t),  # 直接写缓冲区
            timeout=7200
        )

        if exit_code != 0:
            self._log_exec(f"\n  ✗ 脚本执行失败 (exit_code={exit_code})\n")
            return

        self._log_exec(f"\n  ✓ 测试脚本执行完成\n")

        # ===== 阶段3: 下载日志 =====
        self._log_exec("\n[3/4] 下载测试日志到本地...\n")

        remote_log_dir = self.docker.find_latest_log_dir()
        if not remote_log_dir:
            remote_log_dir = f"{self.docker.code_host_path}/{log_dir_name}"

        self._log_exec(f"  远程日志目录: {remote_log_dir}\n")

        local_log_dir = os.path.join(local_dir, log_dir_name)
        os.makedirs(local_log_dir, exist_ok=True)

        local_log_files = self.docker.download_logs(
            remote_log_dir, local_log_dir,
            callback=lambda t: self._log_exec(t)  # 直接写缓冲区
        )

        if not local_log_files:
            self._log_exec("  ✗ 未下载到任何日志文件\n")
            return

        self._log_exec(f"  ✓ 已下载 {len(local_log_files)} 个日志文件到 {local_log_dir}\n")

        # ===== 阶段4: 解析日志生成CSV =====
        self._log_exec("\n[4/4] 解析日志生成CSV结果...\n")

        csv_path = os.path.join(local_dir, f"results_{log_dir_name}.csv")

        results = parse_log_directory(
            local_log_dir, csv_path,
            progress_callback=lambda msg, ok, row: self._log_exec(msg + "\n")
        )

        if results:
            self._log_exec(f"\n{'='*60}\n")
            self._log_exec(f"✓ 测试完成! 结果已保存\n")
            self._log_exec(f"  CSV文件: {csv_path}\n")
            self._log_exec(f"  日志目录: {local_log_dir}\n")
            self._log_exec(f"  共 {len(results)} 条记录\n")
            self._log_exec(f"{'='*60}\n\n")

            # 输出结果摘要表
            self._log_exec("结果摘要:\n")
            self._log_exec("-" * 80 + "\n")
            self._log_exec(f"{'Input':>8} {'Output':>8} {'TTFT_avg':>10} {'TPOT_avg':>10} "
                          f"{'QPS':>8} {'Ext_Hit%':>10}\n")
            self._log_exec("-" * 80 + "\n")
            for row in results:
                self._log_exec(
                    f"{row.get('input_len',''):>8} {row.get('output_len',''):>8} "
                    f"{str(row.get('TTFT_avg','')):>10} {str(row.get('TPOT_avg','')):>10} "
                    f"{str(row.get('qps','')):>8} {str(row.get('external_hit_rate','')):>10}\n"
                )
            self._log_exec("-" * 80 + "\n")

            self.root.after(0, lambda: messagebox.showinfo(
                "完成",
                f"测试完成!\n\nCSV: {csv_path}\n日志: {local_log_dir}\n共 {len(results)} 条记录"
            ))
        else:
            self._log_exec("  ✗ 未能从日志中提取到有效结果\n")
            self.root.after(0, lambda: messagebox.showwarning("提示", "测试已完成但未提取到有效结果，请检查日志"))

    def _log_exec(self, text):
        """向执行日志缓冲区写入（线程安全，由主线程定时刷新）"""
        self._exec_log_buffer += text

    # ============================================================
    #  导航逻辑
    # ============================================================

    def _show_step(self, step):
        """显示指定步骤"""
        if step < 0 or step >= len(self.step_frames):
            return

        for i, frame in enumerate(self.step_frames):
            if i == step:
                frame.pack(fill=tk.BOTH, expand=True)
            else:
                frame.pack_forget()

        self.current_step = step

        # 更新侧边栏
        for i, (indicator, label) in enumerate(self.step_buttons):
            if i == step:
                indicator.config(text="●", fg=COLOR_PRIMARY)
                label.config(fg=COLOR_PRIMARY, font=("Segoe UI", 10, "bold"))
            elif i < step:
                indicator.config(text="✓", fg=COLOR_SUCCESS)
                label.config(fg=COLOR_TEXT, font=("Segoe UI", 10))
            else:
                indicator.config(text="○", fg=COLOR_TEXT_MUTED)
                label.config(fg=COLOR_TEXT_MUTED, font=("Segoe UI", 10))

        # 更新按钮状态
        self.prev_btn.config(state=tk.NORMAL if step > 0 else tk.DISABLED)
        if step == len(self.step_frames) - 1:
            self.next_btn.config(text="完成", command=self._finish)
        else:
            self.next_btn.config(text="下一步 >", command=self._next_step)

        # 步骤特定的刷新
        if step == 3:
            self._sync_config_vars()
        if step == 5:
            self._refresh_commands()

    def _next_step(self):
        """下一步"""
        if self.current_step == 0 and not self.ssh.connected:
            messagebox.showwarning("提示", "请先连接到远程主机")
            return
        if self.current_step == 1:
            if not self.tar_path.get() or not self.zip_path.get() or not self.model_path_var.get():
                messagebox.showwarning("提示", "请完成所有文件选择")
                return
        if self.current_step == 2 and (not self.docker or not self.docker.container_is_running()):
            if not messagebox.askyesno("提示", "Docker容器尚未部署，是否继续?"):
                return
        if self.current_step == 4 and not self.designer.test_cases:
            if not messagebox.askyesno("提示", "尚未生成测试用例，是否继续?"):
                return

        self._show_step(self.current_step + 1)

    def _prev_step(self):
        """上一步"""
        self._show_step(max(0, self.current_step - 1))

    def _finish(self):
        """完成"""
        if messagebox.askyesno("完成", "测试已完成，是否退出程序?"):
            self.ssh.disconnect()
            self.root.destroy()

    def run(self):
        """运行应用"""
        self.root.mainloop()


def main():
    app = WizardApp()
    app.run()


if __name__ == "__main__":
    main()
