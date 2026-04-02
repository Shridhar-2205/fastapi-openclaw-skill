"""Simple FastAPI app — runs on your host machine.

Start:
    pip install -r requirements.txt
    python app.py
"""

from fastapi import FastAPI

app = FastAPI(title="My App", version="0.1.0")


@app.get("/hi")
def hi():
    return {"message": "hi there!"}


@app.get("/hello/{name}")
def hello(name: str):
    return {"message": f"hello {name}!"}


@app.get("/foo")
def foo():
    return {"foo": "bar"}


@app.post("/bar")
def bar(data: dict):
    return {"you_sent": data, "status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
