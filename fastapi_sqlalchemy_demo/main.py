# main.py
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi_sqlalchemy_demo.database import engine, Base, get_db
from fastapi_sqlalchemy_demo.models import TaskModel
from fastapi_sqlalchemy_demo.schemas import TaskCreate, TaskResponse

# Evento de inicio para crear las tablas automáticamente
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

# Punto 1: usuario único con credenciales fijas
security = HTTPBasic()
USERNAME = "admin"
PASSWORD = "1234"

# Verifica que el usuario y la contraseña sean los del único usuario del sistema
def verify_user(credentials: HTTPBasicCredentials = Depends(security)):
    user_ok = secrets.compare_digest(credentials.username, USERNAME)
    pass_ok = secrets.compare_digest(credentials.password, PASSWORD)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

app = FastAPI(
    title="FastAPI con SQLAlchemy 2.0",
    description="Ejemplo práctico de integración asíncrona",
    version="1.0.0",
    lifespan=lifespan,
    # Punto 1: todos los endpoints exigen iniciar sesión con el usuario único
    dependencies=[Depends(verify_user)]
)

# Busca una tarea por ID o devuelve 404 si no existe (evita repetir código)
async def get_task_or_404(task_id: int, db: AsyncSession) -> TaskModel:
    result = await db.execute(select(TaskModel).where(TaskModel.id == task_id))
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarea no encontrada")
    return task

# 1. Crear una Tarea (CREATE) - Punto 2: dar de alta una tarea
@app.post("/tasks/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(task: TaskCreate, db: AsyncSession = Depends(get_db)):
    db_task = TaskModel(
        title=task.title,
        description=task.description,
        completed=task.completed
    )
    db.add(db_task)
    await db.commit()
    await db.refresh(db_task)
    return db_task

# 2. Listar Tareas (READ - List) - Punto 4: por defecto oculta las archivadas
@app.get("/tasks/", response_model=list[TaskResponse])
async def read_tasks(skip: int = 0, limit: int = 10, show_archived: bool = False,
                     db: AsyncSession = Depends(get_db)):
    query = select(TaskModel)
    if not show_archived:
        query = query.where(TaskModel.archived == False)
    result = await db.execute(query.offset(skip).limit(limit))
    tasks = result.scalars().all()
    return list(tasks)

# 3. Obtener una Tarea por ID (READ - Detail)
@app.get("/tasks/{task_id}", response_model=TaskResponse)
async def read_task(task_id: int, db: AsyncSession = Depends(get_db)):
    return await get_task_or_404(task_id, db)

# 4. Actualizar una Tarea (UPDATE)
@app.put("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(task_id: int, task_data: TaskCreate, db: AsyncSession = Depends(get_db)):
    task = await get_task_or_404(task_id, db)

    task.title = task_data.title
    task.description = task_data.description
    task.completed = task_data.completed

    await db.commit()
    await db.refresh(task)
    return task

# 5. Eliminar una Tarea (DELETE)
@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = await get_task_or_404(task_id, db)
    await db.delete(task)
    await db.commit()
    return None

# 6. Marcar una Tarea como terminada - Punto 3
@app.patch("/tasks/{task_id}/complete", response_model=TaskResponse)
async def complete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = await get_task_or_404(task_id, db)
    task.completed = True
    await db.commit()
    await db.refresh(task)
    return task

# 7. Archivar una Tarea finalizada - Punto 4
@app.patch("/tasks/{task_id}/archive", response_model=TaskResponse)
async def archive_task(task_id: int, db: AsyncSession = Depends(get_db)):
    task = await get_task_or_404(task_id, db)
    # Solo se pueden archivar tareas que ya estén terminadas
    if not task.completed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Solo se pueden archivar tareas terminadas")
    task.archived = True
    await db.commit()
    await db.refresh(task)
    return task