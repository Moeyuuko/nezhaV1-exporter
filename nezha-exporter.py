import asyncio
import websockets
import json
from aiohttp import web
import os

# 将接收到的数据转换为Prometheus文本格式
def convert_to_prometheus_text(data):
    lines = []
    lines.append(f'nezha_online {data.get("online", 0)}')
    servers = data.get("servers", [])
    for server in servers:
        sid = server.get("id", 0)
        name = server.get("name", "")
        state = server.get("state", {})
        # 在指标中添加name标签，方便Prometheus和Grafana识别
        lines.append(f'nezha_cpu{{id="{sid}",name="{name}"}} {state.get("cpu", 0)}')
        lines.append(f'nezha_mem_used{{id="{sid}",name="{name}"}} {state.get("mem_used", 0)}')
        lines.append(f'nezha_swap_used{{id="{sid}",name="{name}"}} {state.get("swap_used", 0)}')
        lines.append(f'nezha_disk_used{{id="{sid}",name="{name}"}} {state.get("disk_used", 0)}')
        lines.append(f'nezha_net_in_speed{{id="{sid}",name="{name}"}} {state.get("net_in_speed", 0)}')
        lines.append(f'nezha_net_out_speed{{id="{sid}",name="{name}"}} {state.get("net_out_speed", 0)}')
        lines.append(f'nezha_tcp_conn_count{{id="{sid}",name="{name}"}} {state.get("tcp_conn_count", 0)}')
        lines.append(f'nezha_udp_conn_count{{id="{sid}",name="{name}"}} {state.get("udp_conn_count", 0)}')
        lines.append(f'nezha_process_count{{id="{sid}",name="{name}"}} {state.get("process_count", 0)}')
    return "\n".join(lines)

latest_json_data = None
latest_prom_data = None

# 监听WebSocket，接收监控数据
async def listen(url):
    global latest_json_data, latest_prom_data
    while True:
        try:
            async with websockets.connect(url) as websocket:
                print(f"Connected to {url}", flush=True)
                while True:
                    message = await websocket.recv()
                    try:
                        data = json.loads(message)
                        formatted = json.dumps(data, indent=4, ensure_ascii=False)
                        # print("Received message (formatted JSON):")
                        # print(formatted)
                        global latest_json_data, latest_prom_data
                        latest_json_data = formatted
                        latest_prom_data = convert_to_prometheus_text(data)
                    except json.JSONDecodeError:
                        print("Received non-JSON message:", message, flush=True)
        except (websockets.ConnectionClosed, ConnectionRefusedError) as e:
            print(f"Connection closed or failed: {e}. Reconnecting in 5 seconds...", flush=True)
            await asyncio.sleep(5)

# HTTP接口，返回最新的JSON数据
async def handle_latest_json(request):
    if latest_json_data is None:
        return web.Response(text="No data yet", status=503)
    return web.Response(text=latest_json_data, content_type='application/json')

# HTTP接口，返回最新的Prometheus格式数据
async def handle_latest_prom(request):
    if latest_prom_data is None:
        return web.Response(text="No data yet", status=503)
    return web.Response(text=latest_prom_data, content_type='text/plain')

# 启动HTTP服务器，暴露数据接口
async def start_web_server():
    app = web.Application()
    app.router.add_get('/latest_message.json', handle_latest_json)
    app.router.add_get('/latest_message.prom', handle_latest_prom)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()
    print("HTTP server started on port 8080", flush=True)

# 主入口，启动WebSocket监听和HTTP服务
async def main(url):
    await asyncio.gather(
        listen(url),
        start_web_server()
    )

if __name__ == "__main__":
    # 程序入口，获取环境变量并启动主流程
    print("Starting nezha-exporter...", flush=True)
    url = os.getenv("WS_URL")
    print(f"WS_URL={url}", flush=True)
    if not url:
        print("Error: WS_URL environment variable is not set.", flush=True)
        exit(1)
    asyncio.run(main(url))
