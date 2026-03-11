from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/nan")
def get_nan():
    return {"value": float("nan")}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
