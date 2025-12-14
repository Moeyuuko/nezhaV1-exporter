import asyncio
import websockets
import json
from aiohttp import web, ClientSession, BasicAuth
import os
import time
import base64

# ============================================================================
# 全局变量和配置
# ============================================================================

# 服务器数据缓存
group_map = {}  # 服务器ID到分组名列表映射
server_last_update = {}  # 服务器ID到最后更新时间的映射
server_data_cache = {}  # 服务器ID到服务器数据的缓存
server_last_uptime = {}  # 服务器ID到上次uptime值的映射，用于检测数据是否真正更新
DATA_EXPIRE_SECONDS = 60  # 数据过期时间（秒）
ws_online_count = 0  # WebSocket 返回的在线人数（原始值，不与服务器关联）
ws_timestamp = 0  # WebSocket 返回的时间戳（毫秒级）

# 服务监控数据缓存
service_data_cache = {}  # {server_id: [monitor_data_list]}
service_last_update = {}  # {server_id: timestamp}
SERVICE_DATA_EXPIRE_SECONDS = 120  # 服务数据过期时间（秒），比主数据长一些
SERVICE_DATA_POINTS_COUNT = 3  # 每个监控节点输出的数据点数量

# Basic Auth 认证信息（可选）
auth_username = None
auth_password = None

# 服务监控开关
service_monitor_enabled = False


# ============================================================================
# 工具函数
# ============================================================================

def get_online_servers():
    """
    获取在线服务器列表
    
    Returns:
        list: [(server_id, server_name), ...]
    """
    current_time = time.time()
    online_servers = []
    for sid, server in server_data_cache.items():
        last_update = server_last_update.get(sid, 0)
        if current_time - last_update <= DATA_EXPIRE_SECONDS:
            server_name = server.get("name", "unknown")
            online_servers.append((sid, server_name))
    return online_servers


def get_websocket_headers_param():
    """返回 websockets.connect() 用于传递 headers 的参数名（兼容不同版本）"""
    version = getattr(websockets, '__version__', '0.0.0')
    try:
        major_version = int(version.split('.')[0])
        # websockets 10.x+ 使用 additional_headers，之前版本使用 extra_headers
        if major_version >= 10:
            return 'additional_headers'
        else:
            return 'extra_headers'
    except (ValueError, IndexError):
        # 默认使用新版参数名
        return 'additional_headers'


# ============================================================================
# Prometheus 指标生成 - 服务器基础指标
# ============================================================================

def convert_to_prometheus_text():
    """从缓存中生成 Prometheus 指标，自动过滤过期的服务器数据"""
    current_time = time.time()
    lines = []
    
    # 过滤出未过期的服务器
    active_servers = []
    for sid, server in server_data_cache.items():
        last_update = server_last_update.get(sid, 0)
        if current_time - last_update <= DATA_EXPIRE_SECONDS:
            active_servers.append(server)
    
    # 获取时间戳（毫秒级），用于 Prometheus 指标
    timestamp = ws_timestamp if ws_timestamp > 0 else int(time.time() * 1000)
    
    # WebSocket 返回的在线人数（原始值，不与服务器关联）
    lines.append(f'nezha_online {ws_online_count} {timestamp}')
    # 在线服务器数量（只统计未过期的）
    lines.append(f'nezha_online_server {len(active_servers)} {timestamp}')
    
    for server in active_servers:
        sid = server.get("id", 0)
        name = server.get("name", "")
        host = server.get("host", {})
        state = server.get("state", {})
        group_names = group_map.get(sid, ["unknown"])
        # 在指标中添加name和group标签，支持多分组
        for group_name in group_names:
            if "boot_time" in host:
                lines.append(f'nezha_boot_time{{id="{sid}",name="{name}",group="{group_name}"}} {host["boot_time"]} {timestamp}')
            if "mem_total" in host:
                lines.append(f'nezha_mem_total{{id="{sid}",name="{name}",group="{group_name}"}} {host["mem_total"]} {timestamp}')
            if "disk_total" in host:
                lines.append(f'nezha_disk_total{{id="{sid}",name="{name}",group="{group_name}"}} {host["disk_total"]} {timestamp}')
            if "swap_total" in host:
                lines.append(f'nezha_swap_total{{id="{sid}",name="{name}",group="{group_name}"}} {host["swap_total"]} {timestamp}')

            if "cpu" in state:
                lines.append(f'nezha_cpu{{id="{sid}",name="{name}",group="{group_name}"}} {state["cpu"]} {timestamp}')
            if "mem_used" in state:
                lines.append(f'nezha_mem_used{{id="{sid}",name="{name}",group="{group_name}"}} {state["mem_used"]} {timestamp}')
            if "swap_used" in state:
                lines.append(f'nezha_swap_used{{id="{sid}",name="{name}",group="{group_name}"}} {state["swap_used"]} {timestamp}')
            if "disk_used" in state:
                lines.append(f'nezha_disk_used{{id="{sid}",name="{name}",group="{group_name}"}} {state["disk_used"]} {timestamp}')
            if "net_in_speed" in state:
                lines.append(f'nezha_net_in_speed{{id="{sid}",name="{name}",group="{group_name}"}} {state["net_in_speed"]} {timestamp}')
            if "net_out_speed" in state:
                lines.append(f'nezha_net_out_speed{{id="{sid}",name="{name}",group="{group_name}"}} {state["net_out_speed"]} {timestamp}')
            if "net_in_transfer" in state:
                lines.append(f'nezha_net_in_transfer{{id="{sid}",name="{name}",group="{group_name}"}} {state["net_in_transfer"]} {timestamp}')
            if "net_out_transfer" in state:
                lines.append(f'nezha_net_out_transfer{{id="{sid}",name="{name}",group="{group_name}"}} {state["net_out_transfer"]} {timestamp}')
            if "tcp_conn_count" in state:
                lines.append(f'nezha_tcp_conn_count{{id="{sid}",name="{name}",group="{group_name}"}} {state["tcp_conn_count"]} {timestamp}')
            if "udp_conn_count" in state:
                lines.append(f'nezha_udp_conn_count{{id="{sid}",name="{name}",group="{group_name}"}} {state["udp_conn_count"]} {timestamp}')
            if "process_count" in state:
                lines.append(f'nezha_process_count{{id="{sid}",name="{name}",group="{group_name}"}} {state["process_count"]} {timestamp}')
            if "uptime" in state:
                lines.append(f'nezha_uptime{{id="{sid}",name="{name}",group="{group_name}"}} {state["uptime"]} {timestamp}')

            # 处理温度信息
            temperatures = state.get("temperatures", [])
            if temperatures:
                for temp in temperatures:
                    temp_name = temp.get("Name", "unknown")
                    temp_value = temp.get("Temperature", 0)
                    lines.append(f'nezha_temperature{{id="{sid}",name="{name}",group="{group_name}",temp_name="{temp_name}"}} {temp_value} {timestamp}')

    return "\n".join(lines)


# ============================================================================
# Prometheus 指标生成 - 服务监控指标（网络延迟）
# ============================================================================

def convert_service_to_prometheus():
    """
    将服务监控数据转换为 Prometheus 格式
    
    Returns:
        str: Prometheus 格式的指标文本
    """
    current_time = time.time()
    lines = []
    
    # 添加指标说明
    lines.append("# HELP nezha_service_avg_delay_ms Average network delay in milliseconds")
    lines.append("# TYPE nezha_service_avg_delay_ms gauge")
    
    for server_id, monitors in service_data_cache.items():
        # 检查数据是否过期
        last_update = service_last_update.get(server_id, 0)
        if current_time - last_update > SERVICE_DATA_EXPIRE_SECONDS:
            continue
        
        for monitor in monitors:
            monitor_id = monitor.get("monitor_id", 0)
            monitor_name = monitor.get("monitor_name", "unknown")
            server_name = monitor.get("server_name", "unknown")
            server_groups = monitor.get("server_groups", ["unknown"])
            
            created_at = monitor.get("created_at", [])
            avg_delay = monitor.get("avg_delay", [])
            
            # 取最新的 SERVICE_DATA_POINTS_COUNT 个数据点
            # created_at 和 avg_delay 是平行数组，最新的数据在末尾
            if created_at and avg_delay:
                # 取最后 SERVICE_DATA_POINTS_COUNT 个数据点
                start_idx = max(0, len(created_at) - SERVICE_DATA_POINTS_COUNT)
                
                for i in range(start_idx, len(created_at)):
                    if i < len(avg_delay):
                        # 时间戳保持毫秒格式（Prometheus 需要毫秒级整数）
                        timestamp = int(created_at[i])
                        delay = avg_delay[i]
                        
                        # 转义标签值中的特殊字符
                        safe_monitor_name = monitor_name.replace('"', '\\"')
                        safe_server_name = server_name.replace('"', '\\"')
                        
                        # 为每个分组生成一条指标（与服务器基础指标保持一致）
                        # 标签名使用 id, name, group 与基础指标统一
                        for group_name in server_groups:
                            safe_group_name = group_name.replace('"', '\\"')
                            # Prometheus 格式：时间戳放在数值后面，使用毫秒级整数
                            line = f'nezha_service_avg_delay_ms{{id="{server_id}",name="{safe_server_name}",group="{safe_group_name}",monitor_id="{monitor_id}",monitor_name="{safe_monitor_name}"}} {delay} {timestamp}'
                            lines.append(line)
    
    return "\n".join(lines)


# ============================================================================
# 数据获取 - 分组信息
# ============================================================================

async def fetch_groups(url, username=None, password=None):
    """定期获取服务器分组信息"""
    global group_map
    # 创建 BasicAuth 对象（如果有认证信息）
    auth = BasicAuth(username, password) if username and password else None
    print(f"fetch_groups: auth={'enabled' if auth else 'disabled'}", flush=True)
    while True:
        try:
            async with ClientSession() as session:
                async with session.get(url, auth=auth) as resp:
                    if resp.status == 200:
                        json_data = await resp.json()
                        if json_data.get("success"):
                            new_map = {}
                            for group_entry in json_data.get("data", []):
                                group_name = group_entry.get("group", {}).get("name", "unknown")
                                servers = group_entry.get("servers", [])
                                for sid in servers:
                                    if sid not in new_map:
                                        new_map[sid] = []
                                    new_map[sid].append(group_name)
                            group_map = new_map
                            print(f"Fetched and updated group map: {group_map}", flush=True)
                        else:
                            # 打印完整响应以便调试
                            print(f"Failed to fetch groups: success=false, response: {json_data}", flush=True)
                    else:
                        error_text = await resp.text()
                        print(f"Failed to fetch groups: HTTP {resp.status}, response: {error_text}", flush=True)
        except Exception as e:
            print(f"Error fetching groups: {e}", flush=True)
        await asyncio.sleep(60)  # 每60秒刷新一次分组信息


# ============================================================================
# 数据获取 - WebSocket 服务器数据
# ============================================================================

async def listen(url, username=None, password=None):
    """监听 WebSocket 推送的服务器数据"""
    global server_data_cache, server_last_update, ws_online_count, ws_timestamp
    # 为 WebSocket 创建认证 headers 的 kwargs（兼容不同版本的 websockets 库）
    ws_kwargs = {}
    if username and password:
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers = {"Authorization": f"Basic {credentials}"}
        # 根据 websockets 版本选择正确的参数名
        header_param = get_websocket_headers_param()
        ws_kwargs[header_param] = headers
        print(f"Using websockets parameter: {header_param}", flush=True)
    
    while True:
        try:
            # ping_interval=None 禁用自动 ping，避免 keepalive ping timeout 错误
            # 某些服务器可能不支持或响应较慢
            async with websockets.connect(url, ping_interval=None, **ws_kwargs) as websocket:
                print(f"Connected to {url}", flush=True)
                while True:
                    try:
                        message = await websocket.recv()
                        try:
                            data = json.loads(message)
                            
                            # 更新 WebSocket 返回的在线人数和时间戳
                            ws_online_count = data.get("online", 0)
                            ws_timestamp = data.get("now", 0)
                            
                            # 更新服务器数据缓存和最后更新时间
                            current_time = time.time()
                            servers = data.get("servers", [])
                            for server in servers:
                                sid = server.get("id", 0)
                                state = server.get("state", {})
                                current_uptime = state.get("uptime", 0)
                                
                                # 获取上次的 uptime 值
                                last_uptime = server_last_uptime.get(sid, -1)
                                
                                # 只有当 uptime 发生变化时才更新时间戳
                                # uptime 变化说明服务器真正在线并上报了新数据
                                if current_uptime != last_uptime:
                                    server_last_update[sid] = current_time
                                    server_last_uptime[sid] = current_uptime
                                
                                # 始终更新数据缓存（保留最新收到的数据）
                                server_data_cache[sid] = server
                        except json.JSONDecodeError:
                            print("Received non-JSON message:", message, flush=True)
                    except Exception as e:
                        print(f"Error receiving or processing message: {e}. Reconnecting...", flush=True)
                        # 主动跳出内层循环，触发外层重连逻辑
                        break
        except (websockets.ConnectionClosed, ConnectionRefusedError) as e:
            print(f"Connection closed or failed: {e}. Reconnecting in 5 seconds...", flush=True)
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Unexpected error: {e}. Reconnecting in 5 seconds...", flush=True)
            await asyncio.sleep(5)


# ============================================================================
# 数据获取 - 服务监控数据（网络延迟）
# ============================================================================

async def fetch_service_data(session, base_url, server_id, auth=None):
    """
    获取单个服务器的服务监控数据
    
    Args:
        session: aiohttp ClientSession
        base_url: 服务监控 API 基础 URL (如 https://nezha.example.com/api/v1/service)
        server_id: 服务器 ID
        auth: BasicAuth 对象（可选）
    
    Returns:
        list: 监控数据列表，失败返回空列表
    """
    url = f"{base_url}/{server_id}"
    try:
        async with session.get(url, auth=auth) as resp:
            if resp.status == 200:
                json_data = await resp.json()
                if json_data.get("success"):
                    return json_data.get("data", [])
                else:
                    print(f"Service API failed for server {server_id}: success=false", flush=True)
            else:
                print(f"Service API HTTP error for server {server_id}: {resp.status}", flush=True)
    except Exception as e:
        print(f"Error fetching service data for server {server_id}: {e}", flush=True)
    return []


async def fetch_all_service_data(base_url, online_servers, username=None, password=None):
    """
    并发获取所有在线服务器的服务监控数据
    
    Args:
        base_url: 服务监控 API 基础 URL
        online_servers: 在线服务器列表 [(server_id, server_name), ...]
        username: 认证用户名（可选）
        password: 认证密码（可选）
    """
    global service_data_cache, service_last_update
    
    if not online_servers:
        return
    
    auth = BasicAuth(username, password) if username and password else None
    
    async with ClientSession() as session:
        tasks = []
        for server_id, server_name in online_servers:
            task = fetch_service_data(session, base_url, server_id, auth)
            tasks.append((server_id, server_name, task))
        
        # 并发执行所有请求
        current_time = time.time()
        for server_id, server_name, task in tasks:
            try:
                data = await task
                if data:
                    # 为每个监控数据添加 server_name 和 server_groups
                    server_groups = group_map.get(server_id, ["unknown"])
                    for item in data:
                        item['server_name'] = server_name
                        item['server_groups'] = server_groups
                    service_data_cache[server_id] = data
                    service_last_update[server_id] = current_time
            except Exception as e:
                print(f"Error processing service data for server {server_id}: {e}", flush=True)


async def service_monitor_loop(base_url, username=None, password=None, interval=60):
    """
    服务监控主循环
    
    Args:
        base_url: 服务监控 API 基础 URL
        username: 认证用户名（可选）
        password: 认证密码（可选）
        interval: 刷新间隔（秒）
    """
    print(f"Service monitor started, base_url={base_url}, interval={interval}s", flush=True)
    
    while True:
        try:
            # 获取在线服务器列表
            online_servers = get_online_servers()
            
            if online_servers:
                print(f"Fetching service data for {len(online_servers)} online servers...", flush=True)
                await fetch_all_service_data(base_url, online_servers, username, password)
                print(f"Service data cache updated, {len(service_data_cache)} servers cached", flush=True)
            else:
                print("No online servers found, skipping service data fetch", flush=True)
                
        except Exception as e:
            print(f"Error in service monitor loop: {e}", flush=True)
        
        await asyncio.sleep(interval)


# ============================================================================
# HTTP 服务器
# ============================================================================

async def handle_latest_prom(request):
    """处理 Prometheus 格式数据请求"""
    if not server_data_cache:
        return web.Response(text="No data yet", status=503)
    # 每次请求时动态生成指标，自动过滤过期数据
    prom_data = convert_to_prometheus_text()
    
    # 如果启用了服务监控，追加服务监控指标
    if service_monitor_enabled:
        service_prom_data = convert_service_to_prometheus()
        if service_prom_data:
            prom_data = prom_data + "\n" + service_prom_data
    
    return web.Response(text=prom_data, content_type='text/plain')


async def start_web_server():
    """启动 HTTP 服务器"""
    app = web.Application()
    app.router.add_get('/latest_message.prom', handle_latest_prom)
    app.router.add_get('/metrics', handle_latest_prom)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("HTTP server started on port 8080", flush=True)


# ============================================================================
# 主程序入口
# ============================================================================

async def main(url, group_url, service_url=None, username=None, password=None):
    """主程序入口，启动所有异步任务"""
    tasks = [
        listen(url, username, password),
        fetch_groups(group_url, username, password),
        start_web_server()
    ]
    
    # 如果启用了服务监控，添加服务监控任务
    if service_monitor_enabled and service_url:
        tasks.append(service_monitor_loop(service_url, username, password))
    
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    print("Version：0.1.2", flush=True)
    print("Starting nezha-exporter...", flush=True)
    url = os.getenv("WS_URL")
    group_url = os.getenv("GROUP_URL")
    service_url = os.getenv("SERVICE_URL")
    username = os.getenv("AUTH_USERNAME")
    password = os.getenv("AUTH_PASSWORD")
    
    # 服务监控开关
    service_monitor_env = os.getenv("SERVICE_MONITOR_ENABLED", "false").lower()
    service_monitor_enabled = service_monitor_env in ("true", "1", "yes")
    
    print(f"WS_URL={url}", flush=True)
    print(f"GROUP_URL={group_url}", flush=True)
    print(f"SERVICE_URL={service_url}", flush=True)
    print(f"SERVICE_MONITOR_ENABLED={service_monitor_enabled}", flush=True)
    
    if username and password:
        print("Basic Auth: enabled", flush=True)
    else:
        print("Basic Auth: disabled (no credentials provided)", flush=True)
    if not url:
        print("Error: WS_URL environment variable is not set.", flush=True)
        exit(1)
    if not group_url:
        print("Error: GROUP_URL environment variable is not set.", flush=True)
        exit(1)
    if service_monitor_enabled and not service_url:
        print("Error: SERVICE_URL environment variable is not set but SERVICE_MONITOR_ENABLED is true.", flush=True)
        exit(1)
    asyncio.run(main(url, group_url, service_url, username, password))
