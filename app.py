from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
import sqlite3
import bcrypt
from contextlib import contextmanager
from fastapi.responses import HTMLResponse
import qrcode
from io import BytesIO
import base64

app = FastAPI(title="Léo - Mercadinho Simples")
security = HTTPBasic()

class Produto(BaseModel):
    nome: str
    preco: float
    estoque: int = 0

class User(BaseModel):
    username: str
    password: str

@contextmanager
def get_db():
    conn = sqlite3.connect("leo_mercadinho.db")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                is_admin BOOLEAN NOT NULL DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                preco REAL NOT NULL,
                estoque INTEGER NOT NULL
            )
        """)
        cursor.execute("SELECT * FROM users WHERE username = 'admin'")
        if not cursor.fetchone():
            hashed = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt())
            cursor.execute("INSERT INTO users (username, hashed_password, is_admin) VALUES (?, ?, ?)",
                           ("admin", hashed, True))
        db.commit()

init_db()

def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (credentials.username,))
        user = cursor.fetchone()
        if not user or not bcrypt.checkpw(credentials.password.encode(), user ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
        return {"id": user , "username": user , "is_admin": user }

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <h1>Léo - Mercadinho Simples</h1>
    <p>Use /docs para a interface de teste (Swagger).</p>
    <p>Admin: admin / admin123</p>
    """

@app.post("/produtos", status_code=201)
def criar_produto(produto: Produto, user: dict = Depends(get_current_user)):
    if not user :
        raise HTTPException(status_code=403, detail="Apenas admin")
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute("SELECT COUNT(*) FROM produtos")
        if cursor.fetchone()[0] >= 100:
            raise HTTPException(400, "Limite de 100 produtos atingido")
        cursor.execute("INSERT INTO produtos (nome, preco, estoque) VALUES (?, ?, ?)",
                       (produto.nome, produto.preco, produto.estoque))
        db.commit()
    return {"mensagem": "Produto adicionado"}

@app.get("/produtos")
def listar_produtos():
    with get_db() as db:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM produtos")
        return cursor.fetchall()

@app.get("/pix/{valor}")
def gerar_pix(valor: float):
    chave_pix = "seu@email.com"  # Mude para sua chave real
    payload = f"00020101021226300014BR.GOV.BCB.PIX0114{chave_pix}5204000053039865405{valor:.2f}5802BR5925Nome Do Seu Negocio6009Cidade62070503***6304"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return {"pix_qr": f"data:image/png;base64,{img_str}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
