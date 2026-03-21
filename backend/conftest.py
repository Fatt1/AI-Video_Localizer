# conftest.py — Thêm backend/ vào sys.path để pytest tìm thấy các module
import sys
import os

# Đảm bảo pytest chạy từ thư mục backend/ có thể import services, core, api
sys.path.insert(0, os.path.dirname(__file__))
