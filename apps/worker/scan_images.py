#!/usr/bin/env python3
import os
import time
import urllib.error
import urllib.request

INTERVAL = int(os.environ.get("SCAN_INTERVAL_SECONDS", "300"))
SCAN_URL = os.environ.get("SYNABOOT_SCAN_URL", "http://synaboot-api:8000/api/scan")
ADMIN_TOKEN = os.environ.get("SYNABOOT_ADMIN_TOKEN", "")


def main() -> None:
    while True:
        if not ADMIN_TOKEN:
            print("SynaBoot worker scan disabled: SYNABOOT_ADMIN_TOKEN is not set.", flush=True)
        else:
            # Worker 只请求内部 API 触发幂等扫描，不执行系统网络或磁盘破坏性操作。
            request = urllib.request.Request(
                SCAN_URL,
                method="POST",
                headers={"X-SynaBoot-Admin-Token": ADMIN_TOKEN},
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    print(f"SynaBoot worker scan triggered: HTTP {response.status}", flush=True)
            except urllib.error.URLError as exc:
                print(f"SynaBoot worker scan skipped: {exc}", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
