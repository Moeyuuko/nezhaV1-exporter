import asyncio
import websockets
import json
from aiohttp import web, ClientSession, BasicAuth
import os
import time
import base64

group_map = {}  # 服务器ID到分组名映射
server_last_update = {}  # 服务器ID到最后更新时间的映射
server_data_cache = {}  # 服务器ID到服务器数据的缓存
server_last_uptime = {}  # 服务器ID到上次uptime值的映射，用于检测数据是否真正更新
DATA_EXPIRE_SECONDS = 60  # 数据过期时间（秒）

# Basic Auth 认证信息（可选）
auth_username = None
auth_password = None

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
    
    # 在线服务器数量（只统计未过期的）
    lines.append(f'nezha_online {len(active_servers)}')
    
    for server in active_servers:
        sid = server.get("id", 0)
        name = server.get("name", "")
        host = server.get("host", {})
        state = server.get("state", {})
        group_name = group_map.get(sid, "unknown")
        # 在指标中添加name和group标签，方便Prometheus和Grafana识别

        if "boot_time" in host:
            lines.append(f'nezha_boot_time{{id="{sid}",name="{name}",group="{group_name}"}} {host["boot_time"]}')
        if "mem_total" in host:
            lines.append(f'nezha_mem_total{{id="{sid}",name="{name}",group="{group_name}"}} {host["mem_total"]}')
        if "disk_total" in host:
            lines.append(f'nezha_disk_total{{id="{sid}",name="{name}",group="{group_name}"}} {host["disk_total"]}')
        if "swap_total" in host:
            lines.append(f'nezha_swap_total{{id="{sid}",name="{name}",group="{group_name}"}} {host["swap_total"]}')

        if "cpu" in state:
            lines.append(f'nezha_cpu{{id="{sid}",name="{name}",group="{group_name}"}} {state["cpu"]}')
        if "mem_used" in state:
            lines.append(f'nezha_mem_used{{id="{sid}",name="{name}",group="{group_name}"}} {state["mem_used"]}')
        if "swap_used" in state:
            lines.append(f'nezha_swap_used{{id="{sid}",name="{name}",group="{group_name}"}} {state["swap_used"]}')
        if "disk_used" in state:
            lines.append(f'nezha_disk_used{{id="{sid}",name="{name}",group="{group_name}"}} {state["disk_used"]}')
        if "net_in_speed" in state:
            lines.append(f'nezha_net_in_speed{{id="{sid}",name="{name}",group="{group_name}"}} {state["net_in_speed"]}')
        if "net_out_speed" in state:
            lines.append(f'nezha_net_out_speed{{id="{sid}",name="{name}",group="{group_name}"}} {state["net_out_speed"]}')
        if "net_in_transfer" in state:
            lines.append(f'nezha_net_in_transfer{{id="{sid}",name="{name}",group="{group_name}"}} {state["net_in_transfer"]}')
        if "net_out_transfer" in state:
            lines.append(f'nezha_net_out_transfer{{id="{sid}",name="{name}",group="{group_name}"}} {state["net_out_transfer"]}')
        if "tcp_conn_count" in state:
            lines.append(f'nezha_tcp_conn_count{{id="{sid}",name="{name}",group="{group_name}"}} {state["tcp_conn_count"]}')
        if "udp_conn_count" in state:
            lines.append(f'nezha_udp_conn_count{{id="{sid}",name="{name}",group="{group_name}"}} {state["udp_conn_count"]}')
        if "process_count" in state:
            lines.append(f'nezha_process_count{{id="{sid}",name="{name}",group="{group_name}"}} {state["process_count"]}')
        if "uptime" in state:
            lines.append(f'nezha_uptime{{id="{sid}",name="{name}",group="{group_name}"}} {state["uptime"]}')

        # 处理温度信息
        temperatures = state.get("temperatures", [])
        if temperatures:
            for temp in temperatures:
                temp_name = temp.get("Name", "unknown")
                temp_value = temp.get("Temperature", 0)
                lines.append(f'nezha_temperature{{id="{sid}",name="{name}",group="{group_name}",temp_name="{temp_name}"}} {temp_value}')

    return "\n".join(lines)

def get_filtered_json_data():
    """生成过滤过期服务器后的 JSON 数据"""
    current_time = time.time()
    
    # 过滤出未过期的服务器
    active_servers = []
    for sid, server in server_data_cache.items():
        last_update = server_last_update.get(sid, 0)
        if current_time - last_update <= DATA_EXPIRE_SECONDS:
            active_servers.append(server)
    
    # 构建过滤后的数据结构
    filtered_data = {
        "online": len(active_servers),
        "servers": active_servers
    }
    
    return json.dumps(filtered_data, indent=4, ensure_ascii=False)

latest_json_data = None

async def fetch_groups(url):
    global group_map
    # 创建 BasicAuth 对象（如果有认证信息）
    auth = BasicAuth(auth_username, auth_password) if auth_username and auth_password else None
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
                                    new_map[sid] = group_name
                            group_map = new_map
                            print(f"Fetched and updated group map: {group_map}", flush=True)
                        else:
                            print(f"Failed to fetch groups: success=false", flush=True)
                    else:
                        print(f"Failed to fetch groups: HTTP {resp.status}", flush=True)
        except Exception as e:
            print(f"Error fetching groups: {e}", flush=True)
        await asyncio.sleep(60)  # 每60秒刷新一次分组信息

async def listen(url):
    global latest_json_data, server_data_cache, server_last_update
    # 为 WebSocket 创建认证 headers 的 kwargs（兼容不同版本的 websockets 库）
    ws_kwargs = {}
    if auth_username and auth_password:
        credentials = base64.b64encode(f"{auth_username}:{auth_password}".encode()).decode()
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
                            formatted = json.dumps(data, indent=4, ensure_ascii=False)
                            latest_json_data = formatted
                            
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

async def handle_latest_json(request):
    if not server_data_cache:
        return web.Response(text="No data yet", status=503)
    # 每次请求时动态生成 JSON，自动过滤过期数据
    json_data = get_filtered_json_data()
    return web.Response(text=json_data, content_type='application/json')

async def handle_latest_prom(request):
    if not server_data_cache:
        return web.Response(text="No data yet", status=503)
    # 每次请求时动态生成指标，自动过滤过期数据
    prom_data = convert_to_prometheus_text()
    return web.Response(text=prom_data, content_type='text/plain')

async def start_web_server():
    app = web.Application()
    app.router.add_get('/latest_message.json', handle_latest_json)
    app.router.add_get('/latest_message.prom', handle_latest_prom)
    app.router.add_get('/metrics', handle_latest_prom)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("HTTP server started on port 8080", flush=True)

async def main(url, group_url):
    await asyncio.gather(
        listen(url),
        fetch_groups(group_url),
        start_web_server()
    )

if __name__ == "__main__":
    print("Version：0.0.3", flush=True)
    print("Starting nezha-exporter...", flush=True)
    url = os.getenv("WS_URL")
    group_url = os.getenv("GROUP_URL")
    auth_username = os.getenv("AUTH_USERNAME")
    auth_password = os.getenv("AUTH_PASSWORD")
    print(f"WS_URL={url}", flush=True)
    print(f"GROUP_URL={group_url}", flush=True)
    if auth_username and auth_password:
        print("Basic Auth: enabled", flush=True)
    else:
        print("Basic Auth: disabled (no credentials provided)", flush=True)
    if not url:
        print("Error: WS_URL environment variable is not set.", flush=True)
        exit(1)
    if not group_url:
        print("Error: GROUP_URL environment variable is not set.", flush=True)
        exit(1)
    asyncio.run(main(url, group_url))
