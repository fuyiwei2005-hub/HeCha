#!/usr/bin/env python3
"""PestGuard 单端口双协议代理

对外只开 8000（安全组只放行这一个端口）。同一个端口上：
  - 首字节 0x16（TLS 握手）→ 本地终结 TLS，明文转发给后端 uvicorn
  - 其它                    → 直接明文转发，老的 http:// 链接照常能用
好处是只需一个后端进程，不用为了 HTTPS 再起一份 uvicorn（那会多占一份 YOLO 内存）。
"""
import socket, ssl, threading, sys, os

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 8000
BACKEND = ("127.0.0.1", 8001)
CERT = "/opt/pestguard/tls/cert.pem"
KEY = "/opt/pestguard/tls/key.pem"

ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain(CERT, KEY)
try:
    ctx.set_alpn_protocols(["http/1.1"])
except Exception:
    pass


def pipe(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def handle(conn):
    try:
        first = conn.recv(1, socket.MSG_PEEK)
        if first == b"\x16":
            try:
                conn = ctx.wrap_socket(conn, server_side=True)
            except (ssl.SSLError, OSError):
                conn.close()
                return
        up = socket.create_connection(BACKEND, timeout=10)
    except OSError:
        try:
            conn.close()
        except OSError:
            pass
        return
    threading.Thread(target=pipe, args=(conn, up), daemon=True).start()
    pipe(up, conn)
    try:
        up.close()
    except OSError:
        pass
    try:
        conn.close()
    except OSError:
        pass


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, LISTEN_PORT))
    srv.listen(128)
    print(f"tls-proxy listening on {LISTEN_PORT} -> backend {BACKEND[0]}:{BACKEND[1]}", flush=True)
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
