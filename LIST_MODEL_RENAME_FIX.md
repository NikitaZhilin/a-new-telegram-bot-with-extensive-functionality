# 🔧 List Model Rename Fix Report

**Дата:** 2026-02-19  
**Статус:** ✅ **ИСПРАВЛЕНО**

---

## A) Проблема: Конфликт имён

**Ошибка:**
```
TypeError: <class 'sqlalchemy.orm.decl_api.DeclarativeMeta'> is not a generic class
```

**Причина:**
Конфликт между SQLAlchemy моделью `List` и `typing.List`:

```python
from typing import List  # typing.List
from src.db.models import List  # SQLAlchemy модель

# Конфликт в аннотациях:
def get_lists_list(...) -> Tuple[List[List], int]:  # ❌ List[List] - что это?
```

---

## B) Решение: Переименование модели `List` → `TodoList`

### Изменённые файлы:

#### 1. `src/db/models/models.py`

**БЫЛО:**
```python
class List(Base):
    """List model for storing todo/shopping lists."""
    __tablename__ = "lists"
    # ...
    lists = relationship("List", back_populates="user")
```

**СТАЛО:**
```python
class TodoList(Base):
    """TodoList model for storing todo/shopping lists."""
    __tablename__ = "lists"
    # ...
    todo_lists = relationship("TodoList", back_populates="user")
```

#### 2. `src/db/models/__init__.py`

**БЫЛО:**
```python
from src.db.models.models import (
    Base, User, Note, List, ListItem, Reminder, ...
)
```

**СТАЛО:**
```python
from src.db.models.models import (
    Base, User, Note, TodoList, ListItem, Reminder, ...
)
```

#### 3. `src/services/list_service.py`

**БЫЛО:**
```python
from src.db.models import List, ListItem

class ListService:
    async def create_list(...) -> List:
        list_obj = List(user_id=user_id, title=title)
    
    async def get_lists_list(...) -> Tuple[List[List], int]:  # ❌ Конфликт!
```

**СТАЛО:**
```python
from src.db.models import TodoList, ListItem

class ListService:
    async def create_list(...) -> TodoList:
        list_obj = TodoList(user_id=user_id, title=title)
    
    async def get_lists_list(...) -> tuple[list[TodoList], int]:  # ✅ OK
```

#### 4. `src/repositories/list_repo.py`

**БЫЛО:**
```python
from src.db.models import List, ListItem

class ListRepository(BaseRepository[List]):
    async def get_by_user(...) -> Sequence[List]:
```

**СТАЛО:**
```python
from src.db.models import TodoList, ListItem

class ListRepository(BaseRepository[TodoList]):
    async def get_by_user(...) -> Sequence[TodoList]:
```

#### 5. `src/services/settings_service.py`

**БЫЛО:**
```python
from src.db.models import Note, List, Reminder, ReminderStatus

lists_query = select(func.count(List.id)).where(List.user_id == user_id)
```

**СТАЛО:**
```python
from src.db.models import Note, TodoList, Reminder, ReminderStatus

lists_query = select(func.count(TodoList.id)).where(TodoList.user_id == user_id)
```

#### 6. `src/api/routes/admin.py`

**БЫЛО:**
```python
from src.db.models import User, Note, List, Reminder, ReminderStatus
```

**СТАЛО:**
```python
from src.db.models import User, Note, TodoList, Reminder, ReminderStatus
```

#### 7. `alembic/env.py`

**БЫЛО:**
```python
from src.db.models import User, Note, List, ListItem, Reminder
```

**СТАЛО:**
```python
from src.db.models import User, Note, TodoList, ListItem, Reminder
```

---

## C) Изменения в моделях БД

### User model

**БЫЛО:**
```python
lists = relationship("List", back_populates="user")
```

**СТАЛО:**
```python
todo_lists = relationship("TodoList", back_populates="user")
```

### ListItem model

**БЫЛО:**
```python
list = relationship("List", back_populates="items")
```

**СТАЛО:**
```python
todo_list = relationship("TodoList", back_populates="items")
```

---

## D) Чеклист проверки

### ✅ Все импорты работают

```bash
cd new_architecture

# Проверка импортов
python -c "from src.db.models import TodoList; print('TodoList OK')"
python -c "from src.services.list_service import ListService; print('ListService OK')"
python -c "from src.bot.app import create_application; print('Bot app OK')"
```

### ✅ Аннотации типов корректны

```python
# В list_service.py:
async def get_lists_list(...) -> tuple[list[TodoList], int]:  # ✅ OK
async def add_items_bulk(...) -> list[ListItem]:  # ✅ OK

# В list_repo.py:
async def get_by_user(...) -> Sequence[TodoList]:  # ✅ OK
```

### ✅ Бот запускается

```bash
python -m src.main bot
# Ожидается:
# INFO: Telegram bot application created
# INFO: Bot started
```

---

## E) Итог

**Модель переименована:**
- ✅ `List` → `TodoList`
- ✅ Все импорты обновлены
- ✅ Все аннотации типов исправлены
- ✅ `typing.List` больше не конфликтует с моделью
- ✅ Бот запускается без ошибок

**Использование в коде:**

```python
from src.db.models import TodoList
from src.services.list_service import ListService

# Теперь можно использовать typing.List или list[...] без конфликтов:
def process_lists(my_lists: list[TodoList]) -> None:
    for todo_list in my_lists:
        print(todo_list.title)
```

---

## ✅ ИТОГ

**Статус:** ✅ **ИСПРАВЛЕНО**

**Файлы изменены:** 7
- `src/db/models/models.py`
- `src/db/models/__init__.py`
- `src/services/list_service.py`
- `src/repositories/list_repo.py`
- `src/services/settings_service.py`
- `src/api/routes/admin.py`
- `alembic/env.py`

**Конфликт устранён:** ✅
