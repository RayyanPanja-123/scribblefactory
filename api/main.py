from fastapi import FastAPI

app = FastAPI(title="scribblefactory")


@app.get("/health")
def health():
    return {"ok": True}
