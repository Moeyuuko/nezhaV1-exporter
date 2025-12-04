import asyncio
import websockets
import json
from aiohttp import web, ClientSession
import os

group_map = {}  # 服务器ID到分组名映射

def convert_to_prometheus_text(data):
    lines = []
    lines.append(f'nezha_online {data.get("online", 0)}')
    servers = data.get("servers", [])
    for server in servers:
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
latest_json_data = None
latest_prom_data = None

async def fetch_groups(url):
    global group_map
    while True:
        try:
            async with ClientSession() as session:
                async with session.get(url) as resp:
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
    global latest_json_data, latest_prom_data
    while True:
        try:
            async with websockets.connect(url) as websocket:
                print(f"Connected to {url}", flush=True)
                while True:
                    try:
                        message = await websocket.recv()
                        try:
                            data = json.loads(message)
                            formatted = json.dumps(data, indent=4, ensure_ascii=False)
                            global latest_json_data, latest_prom_data
                            latest_json_data = formatted
                            latest_prom_data = convert_to_prometheus_text(data)
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
    if latest_json_data is None:
        return web.Response(text="No data yet", status=503)
    return web.Response(text=latest_json_data, content_type='application/json')

async def handle_latest_prom(request):
    if latest_prom_data is None:
        return web.Response(text="No data yet", status=503)
    return web.Response(text=latest_prom_data, content_type='text/plain')

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
    print("Version：0.0.0", flush=True)
    print("Starting nezha-exporter...", flush=True)
    url = os.getenv("WS_URL")
    group_url = os.getenv("GROUP_URL")
    print(f"WS_URL={url}", flush=True)
    print(f"GROUP_URL={group_url}", flush=True)
    if not url:
        print("Error: WS_URL environment variable is not set.", flush=True)
        exit(1)
    if not group_url:
        print("Error: GROUP_URL environment variable is not set.", flush=True)
        exit(1)
    asyncio.run(main(url, group_url))
