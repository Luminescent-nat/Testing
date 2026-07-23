import uvicorn
import sys

# 确保导入路径正确
sys.path.insert(0, '.')

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False, access_log=False)
