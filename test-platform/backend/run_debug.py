import sys
import traceback

# 捕获所有异常并打印详细堆栈
original_excepthook = sys.excepthook

def custom_excepthook(exc_type, exc_value, exc_traceback):
    print("\n=== 详细错误信息 ===")
    traceback.print_exception(exc_type, exc_value, exc_traceback)
    print("=== 错误信息结束 ===\n")
    original_excepthook(exc_type, exc_value, exc_traceback)

sys.excepthook = custom_excepthook

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False, log_level="debug")
