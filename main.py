from fastapi import FastAPI
from pydantic import BaseModel

# Khởi tạo ứng dụng FastAPI (Dựa trên Starlette)
app = FastAPI()

# Định nghĩa cấu trúc dữ liệu bằng Pydantic
class Item(BaseModel):
    name: str
    description: str | None = None
    price: float

# Endpoint mặc định (GET)
@app.get("/")
def read_root():
    return {"message": "Xin chào! Backend FastAPI đã hoạt động."}

# Endpoint nhận dữ liệu (POST)
@app.post("/items/")
def create_item(item: Item):
    # Pydantic sẽ tự động kiểm tra xem dữ liệu gửi lên có đúng kiểu Item hay không
    return {"message": f"Đã tạo thành công món đồ: {item.name}", "price": item.price}